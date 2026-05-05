"""Main orchestrator: ties crawler, capture, visual diff, content & link checks together."""
import asyncio
import re
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

import aiohttp
from playwright.async_api import async_playwright

from .capture import capture_page
from .checker import check_links
from .config import Config
from .content import check_favicon, compare_content
from .crawler import collect_urls
from .report import generate_report
from .visual import compute_visual_diff


def _slug(path: str) -> str:
    """Convert a URL path to a filesystem-safe slug."""
    slug = path.strip("/").replace("/", "__") or "home"
    slug = re.sub(r"[^a-zA-Z0-9._-]", "_", slug)
    return slug[:80]


async def _fetch_html(session: aiohttp.ClientSession, url: str, timeout: int) -> Optional[str]:
    try:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=timeout)) as resp:
            if resp.status == 200:
                return await resp.text(errors="replace")
    except Exception:
        pass
    return None


async def _check_page(
    session: aiohttp.ClientSession,
    desktop_context: Any,
    mobile_context: Optional[Any],
    orig_url: str,
    mirror_url: str,
    config: Config,
    screenshots_dir: Path,
) -> Dict[str, Any]:
    path = urlparse(orig_url).path or "/"
    slug = _slug(path)
    out = screenshots_dir / slug

    orig_domain = urlparse(config.original_url).netloc
    mirror_domain = urlparse(config.mirror_url).netloc

    print(f"  → {path}")

    # Fetch HTML
    orig_html, mirror_html = await asyncio.gather(
        _fetch_html(session, orig_url, config.network_timeout),
        _fetch_html(session, mirror_url, config.network_timeout),
    )

    mirror_reachable = mirror_html is not None

    # Content comparison
    content_result: Dict[str, Any] = {}
    if orig_html and mirror_html:
        content_result = compare_content(orig_html, mirror_html)

    # Link checking
    links_result: Dict[str, Any] = {}
    if orig_html and mirror_html:
        links_result = await check_links(
            session,
            orig_html,
            mirror_html,
            orig_url,
            mirror_url,
            orig_domain,
            mirror_domain,
        )

    # ── Desktop screenshots ──────────────────────────────────────────────────
    orig_desk_path = out / "original_desktop.png"
    mirror_desk_path = out / "mirror_desktop.png"
    diff_desk_path = out / "diff_desktop.png"

    orig_desk_ok, mirror_desk_ok = await asyncio.gather(
        capture_page(desktop_context, orig_url, orig_desk_path, config.exclude_selectors, config.page_timeout),
        capture_page(desktop_context, mirror_url, mirror_desk_path, config.exclude_selectors, config.page_timeout),
    )

    visual_desktop: Dict[str, Any] = {}
    if orig_desk_ok and mirror_desk_ok:
        visual_desktop = compute_visual_diff(
            orig_desk_path, mirror_desk_path, diff_desk_path, config.diff_threshold
        )

    screenshots: Dict[str, Any] = {
        "original_desktop_ok": orig_desk_ok,
        "mirror_desktop_ok": mirror_desk_ok,
    }

    # ── Mobile screenshots ───────────────────────────────────────────────────
    visual_mobile: Dict[str, Any] = {}
    if config.check_mobile and mobile_context:
        orig_mob_path = out / "original_mobile.png"
        mirror_mob_path = out / "mirror_mobile.png"
        diff_mob_path = out / "diff_mobile.png"

        orig_mob_ok, mirror_mob_ok = await asyncio.gather(
            capture_page(mobile_context, orig_url, orig_mob_path, config.exclude_selectors, config.page_timeout),
            capture_page(mobile_context, mirror_url, mirror_mob_path, config.exclude_selectors, config.page_timeout),
        )
        screenshots["original_mobile_ok"] = orig_mob_ok
        screenshots["mirror_mobile_ok"] = mirror_mob_ok

        if orig_mob_ok and mirror_mob_ok:
            visual_mobile = compute_visual_diff(
                orig_mob_path, mirror_mob_path, diff_mob_path, config.diff_threshold
            )

    # ── Overall status ───────────────────────────────────────────────────────
    passed = (
        mirror_reachable
        and content_result.get("pass", True)
        and links_result.get("pass", True)
        and visual_desktop.get("pass", True)
        and (not config.check_mobile or visual_mobile.get("pass", True))
    )

    return {
        "path": path,
        "orig_url": orig_url,
        "mirror_url": mirror_url,
        "slug": slug,
        "passed": passed,
        "mirror_reachable": mirror_reachable,
        "content": content_result,
        "links": links_result,
        "visual_desktop": visual_desktop,
        "visual_mobile": visual_mobile,
        "screenshots": screenshots,
    }


async def run(config: Config) -> None:
    config.output_dir.mkdir(parents=True, exist_ok=True)
    screenshots_dir = config.output_dir / "screenshots"

    # ── Collect URLs ─────────────────────────────────────────────────────────
    print(f"[1/4] Collecting URLs from {config.original_url} …")
    urls = await collect_urls(config)
    if not urls:
        print("  No URLs found — check the site is reachable and has a sitemap or crawlable links.")
        return
    print(f"  Found {len(urls)} page(s) to check.")

    # ── Check favicon once ───────────────────────────────────────────────────
    connector = aiohttp.TCPConnector(ssl=False)
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
    }
    async with aiohttp.ClientSession(connector=connector, headers=headers) as session:
        print("[2/4] Checking favicon …")
        favicon = await check_favicon(session, config.original_url, config.mirror_url)
        if not favicon["mirror_ok"]:
            print("  WARNING: favicon.ico not found on mirror site.")

        # ── Browser setup ────────────────────────────────────────────────────
        print("[3/4] Launching browser and capturing screenshots …")
        results: List[Dict[str, Any]] = []

        # Locate Chromium — fall back to any installed build if the default path is missing
        import glob as _glob, os as _os
        _chrome_candidates = (
            _glob.glob("/opt/pw-browsers/chromium-*/chrome-linux/chrome")
            + _glob.glob("/usr/bin/chromium-browser")
            + _glob.glob("/usr/bin/google-chrome")
        )
        _chrome_exe = next((p for p in _chrome_candidates if _os.path.isfile(p)), None)

        async with async_playwright() as pw:
            _launch_kwargs = dict(args=["--no-sandbox", "--disable-setuid-sandbox"])
            if _chrome_exe:
                _launch_kwargs["executable_path"] = _chrome_exe
            browser = await pw.chromium.launch(**_launch_kwargs)

            desktop_ctx = await browser.new_context(
                viewport={"width": config.desktop_width, "height": config.desktop_height},
                device_scale_factor=1,
                ignore_https_errors=True,
                user_agent="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/120 Safari/537.36",
            )

            mobile_ctx = None
            if config.check_mobile:
                mobile_ctx = await browser.new_context(
                    viewport={"width": config.mobile_width, "height": 812},
                    is_mobile=True,
                    has_touch=True,
                    ignore_https_errors=True,
                    user_agent=(
                        "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) "
                        "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 Mobile/15E148 Safari/604.1"
                    ),
                )

            orig_domain = urlparse(config.original_url).netloc

            for i, orig_url in enumerate(urls, 1):
                path = urlparse(orig_url).path or "/"
                mirror_url = config.mirror_url.rstrip("/") + path
                print(f"  [{i}/{len(urls)}]", end="")

                result = await _check_page(
                    session,
                    desktop_ctx,
                    mobile_ctx,
                    orig_url,
                    mirror_url,
                    config,
                    screenshots_dir,
                )
                result["favicon"] = favicon
                results.append(result)

            await browser.close()

        # ── Report ───────────────────────────────────────────────────────────
        print("[4/4] Generating report …")
        report_path = generate_report(results, config)

    passed = sum(1 for r in results if r["passed"])
    failed = len(results) - passed
    print(f"\nDone. {passed}/{len(results)} pages passed.")
    print(f"Report → {report_path.resolve()}")
    if failed:
        print(f"  {failed} page(s) have issues — open the report for details.")
