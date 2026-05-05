"""URL collection: sitemap parsing + recursive crawling."""
import asyncio
import xml.etree.ElementTree as ET
from collections import deque
from typing import List, Optional, Set
from urllib.parse import urljoin, urlparse

import aiohttp
from bs4 import BeautifulSoup

from .config import Config

_SITEMAP_NS = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}


async def _fetch(session: aiohttp.ClientSession, url: str, timeout: int = 10) -> Optional[str]:
    try:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=timeout)) as resp:
            if resp.status == 200:
                return await resp.text(errors="replace")
    except Exception:
        pass
    return None


async def _parse_sitemap(session: aiohttp.ClientSession, base_url: str) -> List[str]:
    urls: List[str] = []
    sitemap_url = base_url.rstrip("/") + "/sitemap.xml"
    content = await _fetch(session, sitemap_url)
    if not content:
        return urls
    try:
        root = ET.fromstring(content)
        # Sitemap index → recurse into sub-sitemaps
        for loc in root.findall("sm:sitemap/sm:loc", _SITEMAP_NS):
            sub = await _fetch(session, loc.text.strip())
            if sub:
                try:
                    sub_root = ET.fromstring(sub)
                    for u in sub_root.findall("sm:url/sm:loc", _SITEMAP_NS):
                        urls.append(u.text.strip())
                except ET.ParseError:
                    pass
        # Direct URL entries
        for u in root.findall("sm:url/sm:loc", _SITEMAP_NS):
            urls.append(u.text.strip())
    except ET.ParseError:
        pass
    return urls


async def _crawl(session: aiohttp.ClientSession, base_url: str, max_pages: int) -> List[str]:
    base_domain = urlparse(base_url).netloc
    visited: Set[str] = set()
    queue: deque = deque([base_url.rstrip("/") + "/"])

    while queue and len(visited) < max_pages:
        url = queue.popleft()
        norm = url.split("?")[0].split("#")[0]
        if norm in visited:
            continue
        visited.add(norm)

        content = await _fetch(session, url)
        if not content:
            continue

        soup = BeautifulSoup(content, "lxml")
        for a in soup.find_all("a", href=True):
            href = a["href"].strip()
            if not href or href.startswith(("mailto:", "tel:", "javascript:")):
                continue
            abs_url = urljoin(url, href).split("?")[0].split("#")[0]
            if urlparse(abs_url).netloc == base_domain and abs_url not in visited:
                queue.append(abs_url)

    return list(visited)


async def collect_urls(config: Config) -> List[str]:
    """Return deduplicated list of paths to compare (from original site)."""
    connector = aiohttp.TCPConnector(ssl=False)
    headers = {"User-Agent": "SiteTester/1.0 (regression-checker)"}
    async with aiohttp.ClientSession(connector=connector, headers=headers) as session:
        urls: List[str] = []

        if config.mode in ("sitemap", "both"):
            sitemap_urls = await _parse_sitemap(session, config.original_url)
            urls.extend(sitemap_urls)

        existing_paths = {urlparse(u).path for u in urls}

        if config.mode in ("crawl", "both") or not urls:
            crawled = await _crawl(session, config.original_url, config.max_pages)
            for u in crawled:
                if urlparse(u).path not in existing_paths:
                    urls.append(u)
                    existing_paths.add(urlparse(u).path)

    # Deduplicate by path, preserve order, cap at max_pages
    seen: Set[str] = set()
    result: List[str] = []
    for u in urls:
        path = urlparse(u).path or "/"
        if path not in seen:
            seen.add(path)
            result.append(u)
            if len(result) >= config.max_pages:
                break

    return result
