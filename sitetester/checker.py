"""
Проверка ссылочной структуры.
  compare_links()       — сравнивает ссылки оригинала и зеркала по спискам из Playwright
  check_broken_links()  — проверяет HTTP-статус внутренних ссылок зеркала
"""
import asyncio
from typing import Any, Dict, List
from urllib.parse import urlparse

import aiohttp

_MAX_STATUS_CHECKS = 60


def compare_links(
    orig_links:    List[Dict[str, Any]],
    mirror_links:  List[Dict[str, Any]],
    orig_domain:   str,
    mirror_domain: str,
    mirror_base:   str,
) -> Dict[str, Any]:
    """
    Для каждой ссылки оригинала проверяет, есть ли эквивалент на зеркале.

    Правила:
      • Внутренняя ссылка orig_domain/path  → на зеркале должна быть mirror_domain/path
      • Внешняя ссылка                      → должна присутствовать без изменений
    """
    # ── Строим lookup зеркала ────────────────────────────────────────────────
    mirror_int_paths: set  = set()   # пути внутренних ссылок
    mirror_ext_hrefs: set  = set()   # абсолютные URL внешних ссылок
    wrong_domain_links: List[Dict] = []

    for lnk in mirror_links:
        parsed = urlparse(lnk["abs_href"])
        if parsed.netloc == mirror_domain:
            mirror_int_paths.add(parsed.path.rstrip("/") or "/")
        elif parsed.netloc == orig_domain:
            # Ссылка на зеркале до сих пор ведёт на старый домен
            wrong_domain_links.append(lnk)
            # Считаем путь «присутствующим», чтобы не дублировать в missing
            mirror_int_paths.add(parsed.path.rstrip("/") or "/")
        elif parsed.scheme in ("http", "https") and parsed.netloc:
            mirror_ext_hrefs.add(lnk["abs_href"])

    # ── Ищем отсутствующие ссылки ────────────────────────────────────────────
    seen_int: set  = set()
    seen_ext: set  = set()
    missing: List[Dict] = []

    for lnk in orig_links:
        href   = lnk["abs_href"]
        parsed = urlparse(href)

        if parsed.netloc == orig_domain:
            path = parsed.path.rstrip("/") or "/"
            if path in seen_int:
                continue
            seen_int.add(path)
            if path not in mirror_int_paths:
                missing.append({
                    **lnk,
                    "link_type":    "internal",
                    "expected_url": mirror_base.rstrip("/") + (parsed.path or "/"),
                })

        elif parsed.scheme in ("http", "https") and parsed.netloc:
            if href in seen_ext:
                continue
            seen_ext.add(href)
            if href not in mirror_ext_hrefs:
                missing.append({
                    **lnk,
                    "link_type":    "external",
                    "expected_url": href,
                })

    return {
        "missing_links":      missing,
        "wrong_domain_links": wrong_domain_links[:25],
        "pass": not missing and not wrong_domain_links,
    }


async def check_broken_links(
    session: aiohttp.ClientSession,
    mirror_links: List[Dict[str, Any]],
    mirror_domain: str,
) -> List[Dict[str, Any]]:
    """Проверяет HTTP-статус внутренних ссылок зеркала (не более 60 уникальных)."""
    seen: set = set()
    urls: List[str] = []
    for lnk in mirror_links:
        href = lnk["abs_href"]
        if urlparse(href).netloc == mirror_domain and href not in seen:
            seen.add(href)
            urls.append(href)
            if len(urls) >= _MAX_STATUS_CHECKS:
                break

    broken: List[Dict] = []
    for url in urls:
        try:
            async with session.head(
                url,
                timeout=aiohttp.ClientTimeout(total=6),
                allow_redirects=True,
            ) as r:
                if r.status == 404 or r.status >= 500:
                    broken.append({"url": url, "status": r.status})
        except Exception:
            pass  # сетевые ошибки игнорируем при проверке статусов
    return broken
