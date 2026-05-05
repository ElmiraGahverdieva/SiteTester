"""Playwright-based full-page screenshot capture."""
import asyncio
from pathlib import Path
from typing import List

from playwright.async_api import BrowserContext, Page

POPUP_BLOCKER_CSS = """
    [class*="cookie" i], [class*="modal" i], [class*="popup" i],
    [class*="banner" i], [class*="gdpr" i], [class*="overlay" i],
    [id*="cookie" i], [id*="modal" i], [id*="popup" i],
    [id*="intercom" i], [id*="crisp" i], [id*="livechat" i],
    [id*="chat-widget" i], [id*="tawktowrap" i],
    .cc-banner, .cookie-notice, .cookie-bar, .gdpr-banner,
    #onetrust-banner-sdk, #cookielaw-banner {
        display: none !important;
        visibility: hidden !important;
        opacity: 0 !important;
        pointer-events: none !important;
    }
    body { overflow: auto !important; }
"""


async def _pre_scroll(page: Page) -> None:
    """Scroll to bottom and back to trigger lazy-load content."""
    await page.evaluate("""
        async () => {
            await new Promise((resolve) => {
                const distance = 300;
                const intervalMs = 60;
                let pos = 0;
                const total = document.documentElement.scrollHeight;
                const timer = setInterval(() => {
                    window.scrollBy(0, distance);
                    pos += distance;
                    if (pos >= total) {
                        clearInterval(timer);
                        window.scrollTo({ top: 0, behavior: 'smooth' });
                        setTimeout(resolve, 600);
                    }
                }, intervalMs);
            });
        }
    """)
    await asyncio.sleep(0.5)


async def _apply_exclusions(page: Page, selectors: List[str]) -> None:
    if not selectors:
        return
    css = ", ".join(selectors) + " { visibility: hidden !important; background: #888888 !important; }"
    await page.add_style_tag(content=css)


async def capture_page(
    context: BrowserContext,
    url: str,
    output_path: Path,
    exclude_selectors: List[str],
    page_timeout: int,
) -> bool:
    """Open URL in a new page and save a full-page screenshot. Returns success."""
    page = await context.new_page()
    try:
        await page.goto(url, wait_until="networkidle", timeout=page_timeout)
        await asyncio.sleep(0.8)

        await page.add_style_tag(content=POPUP_BLOCKER_CSS)
        await _apply_exclusions(page, exclude_selectors)
        await _pre_scroll(page)
        await asyncio.sleep(0.8)

        output_path.parent.mkdir(parents=True, exist_ok=True)
        await page.screenshot(path=str(output_path), full_page=True)
        return True
    except Exception as exc:
        print(f"    [capture] ERROR {url}: {exc}")
        return False
    finally:
        await page.close()
