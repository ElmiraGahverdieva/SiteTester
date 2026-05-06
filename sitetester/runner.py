"""Главный оркестратор: объединяет все модули и запускает проверку."""
import asyncio
import re
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

import aiohttp
from playwright.async_api import async_playwright

from .capture import capture_page_with_links
from .checker import check_broken_links, compare_links
from .config import Config
from .content import check_favicon, compare_seo, compare_text
from .crawler import collect_urls
from .report import generate_report
from .visual import annotate_screenshot, compute_visual_diff


def _slug(path: str) -> str:
    slug = path.strip("/").replace("/", "__") or "home"
    slug = re.sub(r"[^a-zA-Z0-9._-]", "_", slug)
    return slug[:80]


async def _fetch_html(
    session: aiohttp.ClientSession, url: str, timeout: int
) -> Optional[str]:
    try:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=timeout)) as resp:
            if resp.status == 200:
                return await resp.text(errors="replace")
    except Exception:
        pass
    return None


async def _check_page(
    session: aiohttp.ClientSession,
    desktop_ctx: Any,
    mobile_ctx: Optional[Any],
    orig_url: str,
    mirror_url: str,
    config: Config,
    screenshots_dir: Path,
) -> Dict[str, Any]:
    path   = urlparse(orig_url).path or "/"
    slug   = _slug(path)
    out    = screenshots_dir / slug
    orig_domain   = urlparse(config.original_url).netloc
    mirror_domain = urlparse(config.mirror_url).netloc

    print(f"  → {path}")

    # ── HTML (для текста и SEO) ───────────────────────────────────────────────
    orig_html, mirror_html = await asyncio.gather(
        _fetch_html(session, orig_url,   config.network_timeout),
        _fetch_html(session, mirror_url, config.network_timeout),
    )
    mirror_reachable = mirror_html is not None

    # ── Сравнение текста ─────────────────────────────────────────────────────
    text_result: Dict[str, Any] = {"pass": True, "missing": [], "extra": []}
    if orig_html and mirror_html:
        text_result = compare_text(orig_html, mirror_html)

    # ── SEO / Мета ───────────────────────────────────────────────────────────
    seo_result: Dict[str, Any] = {"pass": True, "issues": []}
    if orig_html and mirror_html:
        seo_result = compare_seo(orig_html, mirror_html)

    # ── Desktop скриншоты + ссылки ───────────────────────────────────────────
    orig_desk_path   = out / "original_desktop.png"
    mirror_desk_path = out / "mirror_desktop.png"
    diff_desk_path   = out / "diff_desktop.png"
    annot_desk_path  = out / "annotated_desktop.png"

    (orig_desk_ok, orig_links), (mirror_desk_ok, mirror_links) = await asyncio.gather(
        capture_page_with_links(desktop_ctx, orig_url,   orig_desk_path,   config.exclude_selectors, config.page_timeout),
        capture_page_with_links(desktop_ctx, mirror_url, mirror_desk_path, config.exclude_selectors, config.page_timeout),
    )

    # ── Сравнение ссылок (без сети) ──────────────────────────────────────────
    links_result = compare_links(
        orig_links, mirror_links,
        orig_domain, mirror_domain, config.mirror_url,
    )

    # Аннотируем скриншот оригинала — отмечаем где отсутствующие ссылки
    has_annotated = False
    if links_result["missing_links"] and orig_desk_ok:
        has_annotated = annotate_screenshot(
            orig_desk_path, links_result["missing_links"], annot_desk_path
        )

    # Проверка HTTP-статусов ссылок зеркала
    broken: List[Dict] = []
    if mirror_html:
        broken = await check_broken_links(session, mirror_links, mirror_domain)
    links_result["broken_links"]    = broken
    links_result["has_annotated"]   = has_annotated
    if not broken:
        links_result["pass"] = links_result["pass"]  # уже вычислено
    else:
        links_result["pass"] = False

    # ── Визуальный diff (Desktop) ─────────────────────────────────────────────
    visual_desktop: Dict[str, Any] = {}
    if orig_desk_ok and mirror_desk_ok:
        visual_desktop = compute_visual_diff(
            orig_desk_path, mirror_desk_path, diff_desk_path,
            config.diff_threshold, config.blur_radius, config.pixel_sensitivity,
        )

    screenshots: Dict[str, Any] = {
        "original_desktop_ok": orig_desk_ok,
        "mirror_desktop_ok":   mirror_desk_ok,
        "has_annotated":       has_annotated,
    }

    # ── Mobile скриншоты + визуальный diff ───────────────────────────────────
    visual_mobile: Dict[str, Any] = {}
    if config.check_mobile and mobile_ctx:
        orig_mob_path   = out / "original_mobile.png"
        mirror_mob_path = out / "mirror_mobile.png"
        diff_mob_path   = out / "diff_mobile.png"

        (orig_mob_ok, _), (mirror_mob_ok, _) = await asyncio.gather(
            capture_page_with_links(mobile_ctx, orig_url,   orig_mob_path,   config.exclude_selectors, config.page_timeout),
            capture_page_with_links(mobile_ctx, mirror_url, mirror_mob_path, config.exclude_selectors, config.page_timeout),
        )
        screenshots["original_mobile_ok"] = orig_mob_ok
        screenshots["mirror_mobile_ok"]   = mirror_mob_ok

        if orig_mob_ok and mirror_mob_ok:
            visual_mobile = compute_visual_diff(
                orig_mob_path, mirror_mob_path, diff_mob_path,
                config.diff_threshold, config.blur_radius, config.pixel_sensitivity,
            )

    # ── Итоговый статус ───────────────────────────────────────────────────────
    passed = (
        mirror_reachable
        and text_result.get("pass", True)
        and seo_result.get("pass", True)
        and links_result.get("pass", True)
        and visual_desktop.get("pass", True)
        and (not config.check_mobile or visual_mobile.get("pass", True))
    )

    return {
        "path":            path,
        "orig_url":        orig_url,
        "mirror_url":      mirror_url,
        "slug":            slug,
        "passed":          passed,
        "mirror_reachable": mirror_reachable,
        "text":            text_result,
        "seo":             seo_result,
        "links":           links_result,
        "visual_desktop":  visual_desktop,
        "visual_mobile":   visual_mobile,
        "screenshots":     screenshots,
    }


async def run(config: Config) -> None:
    config.output_dir.mkdir(parents=True, exist_ok=True)
    screenshots_dir = config.output_dir / "screenshots"

    # ── Сбор URL ─────────────────────────────────────────────────────────────
    print(f"[1/4] Сбор URL с {config.original_url} …")
    urls = await collect_urls(config)
    if not urls:
        print("  Страницы не найдены — проверьте доступность сайта.")
        return
    print(f"  Найдено {len(urls)} страниц(ы).")

    # ── HTTP-сессия ───────────────────────────────────────────────────────────
    connector = aiohttp.TCPConnector(ssl=False)
    ua = (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )
    async with aiohttp.ClientSession(
        connector=connector, headers={"User-Agent": ua}
    ) as session:

        print("[2/4] Проверка favicon …")
        favicon = await check_favicon(session, config.original_url, config.mirror_url)
        if not favicon["mirror_ok"]:
            print("  ПРЕДУПРЕЖДЕНИЕ: favicon.ico не найден на зеркале.")

        # ── Браузер ───────────────────────────────────────────────────────────
        print("[3/4] Запуск браузера и скриншоты …")
        results: List[Dict[str, Any]] = []

        import glob as _glob, os as _os
        _chrome = next(
            (p for p in _glob.glob("/opt/pw-browsers/chromium-*/chrome-linux/chrome")
             if _os.path.isfile(p)),
            None
        )

        async with async_playwright() as pw:
            _kw = dict(args=["--no-sandbox", "--disable-setuid-sandbox"])
            if _chrome:
                _kw["executable_path"] = _chrome
            browser = await pw.chromium.launch(**_kw)

            desktop_ctx = await browser.new_context(
                viewport={"width": config.desktop_width, "height": config.desktop_height},
                device_scale_factor=1,
                ignore_https_errors=True,
                user_agent=(
                    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                    "Chrome/120 Safari/537.36"
                ),
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
                        "AppleWebKit/605.1.15 Version/16.0 Mobile/15E148 Safari/604.1"
                    ),
                )

            for i, orig_url in enumerate(urls, 1):
                path       = urlparse(orig_url).path or "/"
                mirror_url = config.mirror_url.rstrip("/") + path
                print(f"  [{i}/{len(urls)}]", end="")

                result = await _check_page(
                    session, desktop_ctx, mobile_ctx,
                    orig_url, mirror_url, config, screenshots_dir,
                )
                result["favicon"] = favicon
                results.append(result)

            await browser.close()

        # ── Отчёт ─────────────────────────────────────────────────────────────
        print("[4/4] Генерация отчёта …")
        report_path = generate_report(results, config)

    passed = sum(1 for r in results if r["passed"])
    failed = len(results) - passed
    print(f"\nГотово. {passed}/{len(results)} страниц прошли проверку.")
    print(f"Отчёт → {report_path.resolve()}")
    if failed:
        print(f"  {failed} страниц(ы) с проблемами — откройте отчёт для деталей.")
