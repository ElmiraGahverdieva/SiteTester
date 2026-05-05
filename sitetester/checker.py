"""Link structure verification."""
import asyncio
from typing import Any, Dict, List
from urllib.parse import urljoin, urlparse

import aiohttp
from bs4 import BeautifulSoup

_IGNORE_SCHEMES = {"mailto:", "tel:", "javascript:", "data:"}
_MAX_LINKS_TO_CHECK = 60


def _extract_links(html: str, page_url: str, domain: str):
    """Return (internal_links, external_links) as absolute URL sets."""
    soup = BeautifulSoup(html, "lxml")
    internal, external = set(), set()
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if not href or any(href.startswith(s) for s in _IGNORE_SCHEMES):
            continue
        abs_url = urljoin(page_url, href).split("#")[0]
        if not abs_url.startswith("http"):
            continue
        if urlparse(abs_url).netloc == domain:
            internal.add(abs_url)
        else:
            external.add(abs_url)
    return internal, external


async def _check_status(session: aiohttp.ClientSession, url: str) -> int:
    try:
        async with session.head(
            url,
            timeout=aiohttp.ClientTimeout(total=6),
            allow_redirects=True,
        ) as r:
            return r.status
    except Exception:
        return 0


async def check_links(
    session: aiohttp.ClientSession,
    orig_html: str,
    mirror_html: str,
    orig_page_url: str,
    mirror_page_url: str,
    orig_domain: str,
    mirror_domain: str,
) -> Dict[str, Any]:
    """Verify link structure on the mirror page."""
    mirror_internal, mirror_external = _extract_links(mirror_html, mirror_page_url, mirror_domain)
    orig_internal, orig_external = _extract_links(orig_html, orig_page_url, orig_domain)

    # Links on mirror that still point to original domain
    wrong_domain: List[str] = []
    soup = BeautifulSoup(mirror_html, "lxml")
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if not href or any(href.startswith(s) for s in _IGNORE_SCHEMES):
            continue
        abs_url = urljoin(mirror_page_url, href).split("#")[0]
        if urlparse(abs_url).netloc == orig_domain:
            wrong_domain.append(abs_url)

    # External links that exist on original but are missing/changed on mirror
    orig_ext_paths = {urlparse(u).path for u in orig_external}
    mirror_ext_paths = {urlparse(u).path for u in mirror_external}
    missing_external = list(orig_ext_paths - mirror_ext_paths)

    # Check HTTP status for mirror internal links (sample to avoid hammering)
    links_to_check = list(mirror_internal)[:_MAX_LINKS_TO_CHECK]
    statuses = await asyncio.gather(*[_check_status(session, u) for u in links_to_check])
    broken = [
        {"url": u, "status": s}
        for u, s in zip(links_to_check, statuses)
        if s in (0, 404, 410) or s >= 500
    ]

    issues = bool(broken or wrong_domain)
    return {
        "broken_links": broken,
        "wrong_domain_links": wrong_domain[:20],
        "missing_external": missing_external[:20],
        "mirror_internal_count": len(mirror_internal),
        "mirror_external_count": len(mirror_external),
        "pass": not issues,
    }
