"""
SEO-аудит и сравнение видимого текста страниц.
Разделено на два независимых модуля:
  compare_text()    — сравнение видимого текста
  compare_seo()     — мета-теги, заголовки H1-H6, alt-атрибуты картинок
"""
import difflib
from typing import Any, Dict, List

from bs4 import BeautifulSoup, Comment


# ─── Утилиты ────────────────────────────────────────────────────────────────

def _extract_text_blocks(soup: BeautifulSoup) -> List[str]:
    """Извлечь все видимые текстовые блоки, исключая скрипты/стили/комментарии."""
    for tag in soup(["script", "style", "noscript", "iframe", "head"]):
        tag.decompose()
    for comment in soup.find_all(string=lambda t: isinstance(t, Comment)):
        comment.extract()

    blocks = []
    for text in soup.find_all(string=True):
        t = " ".join(text.split())
        if t and len(t) > 1:
            blocks.append(t)
    return blocks


def _meta(soup: BeautifulSoup) -> Dict[str, str]:
    title = soup.title.get_text(strip=True) if soup.title else ""
    desc = keywords = ""
    for tag in soup.find_all("meta"):
        name = (tag.get("name") or tag.get("property") or "").lower()
        if name in ("description", "og:description"):
            desc = tag.get("content", "").strip()
        elif name == "keywords":
            keywords = tag.get("content", "").strip()
    return {"title": title, "description": desc, "keywords": keywords}


def _headings(soup: BeautifulSoup) -> List[Dict[str, str]]:
    return [
        {"level": tag.name, "text": tag.get_text(separator=" ", strip=True)}
        for tag in soup.find_all(["h1", "h2", "h3", "h4", "h5", "h6"])
    ]


# ─── Сравнение текста ────────────────────────────────────────────────────────

def compare_text(orig_html: str, mirror_html: str) -> Dict[str, Any]:
    """Сравнивает видимый текст двух страниц."""
    orig_blocks   = _extract_text_blocks(BeautifulSoup(orig_html,   "lxml"))
    mirror_blocks = _extract_text_blocks(BeautifulSoup(mirror_html, "lxml"))

    matcher = difflib.SequenceMatcher(None, orig_blocks, mirror_blocks, autojunk=False)

    missing: List[str] = []   # есть в оригинале, нет на зеркале
    extra:   List[str] = []   # есть на зеркале, нет в оригинале

    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag in ("delete", "replace"):
            missing.extend(orig_blocks[i1:i2])
        if tag in ("insert", "replace"):
            extra.extend(mirror_blocks[j1:j2])

    # Обрезаем для отчёта
    return {
        "missing": missing[:40],
        "extra":   extra[:40],
        "missing_total": len(missing),
        "extra_total":   len(extra),
        "pass": not missing and not extra,
    }


# ─── SEO / Мета ──────────────────────────────────────────────────────────────

def compare_seo(orig_html: str, mirror_html: str) -> Dict[str, Any]:
    """Сравнивает мета-теги, заголовки и атрибуты изображений."""
    orig_soup   = BeautifulSoup(orig_html,   "lxml")
    mirror_soup = BeautifulSoup(mirror_html, "lxml")

    orig_meta   = _meta(orig_soup)
    mirror_meta = _meta(mirror_soup)
    orig_h      = _headings(orig_soup)
    mirror_h    = _headings(mirror_soup)

    images       = mirror_soup.find_all("img")
    missing_alt  = [img.get("src", "") for img in images if not img.get("alt")]

    issues: List[Dict[str, Any]] = []

    for field in ("title", "description", "keywords"):
        if orig_meta[field] != mirror_meta[field]:
            issues.append({
                "type": "meta", "field": field,
                "original": orig_meta[field],
                "mirror":   mirror_meta[field],
            })

    if orig_h != mirror_h:
        issues.append({
            "type": "headings",
            "orig_count":   len(orig_h),
            "mirror_count": len(mirror_h),
            "original": orig_h,
            "mirror":   mirror_h,
        })

    if missing_alt:
        issues.append({
            "type": "images_alt",
            "missing": missing_alt[:10],
            "total_missing": len(missing_alt),
        })

    return {
        "issues":       issues,
        "orig_meta":    orig_meta,
        "mirror_meta":  mirror_meta,
        "orig_headings": orig_h,
        "mirror_headings": mirror_h,
        "pass": not issues,
    }


# ─── Favicon ─────────────────────────────────────────────────────────────────

async def check_favicon(session: Any, orig_url: str, mirror_url: str) -> Dict[str, Any]:
    import aiohttp

    async def ok(url: str) -> bool:
        try:
            async with session.head(
                url, timeout=aiohttp.ClientTimeout(total=5), allow_redirects=True
            ) as r:
                return r.status == 200
        except Exception:
            return False

    orig_ok   = await ok(orig_url.rstrip("/")   + "/favicon.ico")
    mirror_ok = await ok(mirror_url.rstrip("/") + "/favicon.ico")
    return {"orig_ok": orig_ok, "mirror_ok": mirror_ok, "pass": mirror_ok}
