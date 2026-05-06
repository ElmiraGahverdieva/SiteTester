"""Playwright-based full-page screenshot capture + сбор ссылок с позициями."""
import asyncio
from pathlib import Path
from typing import Any, Dict, List, Tuple

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

_LINKS_JS = """
() => {
    const H = Math.max(document.documentElement.scrollHeight, 1);
    return Array.from(document.querySelectorAll('a[href]')).map(el => {
        const r  = el.getBoundingClientRect();
        const sy = window.pageYOffset;
        const absY = r.top + sy;
        return {
            href:     el.getAttribute('href') || '',
            abs_href: el.href || '',
            text:     (el.innerText || el.textContent || '').trim()
                        .replace(/\\s+/g, ' ').slice(0, 130),
            x:     Math.round(r.left),
            y:     Math.round(absY),
            w:     Math.round(r.width),
            h:     Math.round(r.height),
            y_pct: Math.round(absY / H * 100),
        };
    }).filter(l => l.href && !l.href.startsWith('#'));
}
"""


async def _pre_scroll(page: Page) -> None:
    """Плавный скролл до конца и обратно — активирует lazy-load контент."""
    await page.evaluate("""
        async () => {
            await new Promise(resolve => {
                let pos = 0;
                const step = 300, delay = 60;
                const total = document.documentElement.scrollHeight;
                const t = setInterval(() => {
                    window.scrollBy(0, step);
                    pos += step;
                    if (pos >= total) {
                        clearInterval(t);
                        window.scrollTo({ top: 0, behavior: 'smooth' });
                        setTimeout(resolve, 600);
                    }
                }, delay);
            });
        }
    """)
    await asyncio.sleep(0.5)


async def _apply_exclusions(page: Page, selectors: List[str]) -> None:
    if not selectors:
        return
    css = ", ".join(selectors) + " { visibility: hidden !important; background: #888 !important; }"
    await page.add_style_tag(content=css)


async def capture_page_with_links(
    context: BrowserContext,
    url: str,
    output_path: Path,
    exclude_selectors: List[str],
    page_timeout: int,
) -> Tuple[bool, List[Dict[str, Any]]]:
    """
    Открывает страницу, делает скриншот и возвращает список ссылок с позициями.
    Возвращает: (успех, список_ссылок)
    """
    page = await context.new_page()
    try:
        await page.goto(url, wait_until="networkidle", timeout=page_timeout)
        await asyncio.sleep(0.8)

        await page.add_style_tag(content=POPUP_BLOCKER_CSS)
        await _apply_exclusions(page, exclude_selectors)
        await _pre_scroll(page)
        await asyncio.sleep(0.8)

        links = await page.evaluate(_LINKS_JS)

        output_path.parent.mkdir(parents=True, exist_ok=True)
        await page.screenshot(path=str(output_path), full_page=True)

        return True, links
    except Exception as exc:
        print(f"    [capture] ОШИБКА {url}: {exc}")
        return False, []
    finally:
        await page.close()
