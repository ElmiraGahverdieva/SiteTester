"""HTML content and SEO auditing."""
from typing import Any, Dict, List, Optional
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup


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
    result = []
    for tag in soup.find_all(["h1", "h2", "h3", "h4", "h5", "h6"]):
        result.append({"level": tag.name, "text": tag.get_text(separator=" ", strip=True)})
    return result


def _image_audit(soup: BeautifulSoup) -> Dict[str, Any]:
    images = soup.find_all("img")
    missing_alt = [img.get("src", "") for img in images if not img.get("alt")]
    missing_title = [img.get("src", "") for img in images if not img.get("title")]
    return {
        "total": len(images),
        "missing_alt": missing_alt,
        "missing_title": missing_title,
    }


def compare_content(
    orig_html: str,
    mirror_html: str,
) -> Dict[str, Any]:
    """Return structured comparison of content/SEO fields."""
    orig = BeautifulSoup(orig_html, "lxml")
    mirror = BeautifulSoup(mirror_html, "lxml")

    orig_meta = _meta(orig)
    mirror_meta = _meta(mirror)
    orig_headings = _headings(orig)
    mirror_headings = _headings(mirror)
    mirror_images = _image_audit(mirror)

    issues: List[Dict[str, Any]] = []

    for field in ("title", "description", "keywords"):
        if orig_meta[field] != mirror_meta[field]:
            issues.append(
                {
                    "type": "meta",
                    "field": field,
                    "original": orig_meta[field],
                    "mirror": mirror_meta[field],
                }
            )

    if orig_headings != mirror_headings:
        issues.append(
            {
                "type": "headings",
                "original": orig_headings,
                "mirror": mirror_headings,
                "orig_count": len(orig_headings),
                "mirror_count": len(mirror_headings),
            }
        )

    if mirror_images["missing_alt"]:
        issues.append(
            {
                "type": "images_alt",
                "missing": mirror_images["missing_alt"][:10],  # cap for report readability
                "total_missing": len(mirror_images["missing_alt"]),
            }
        )

    return {
        "issues": issues,
        "orig_meta": orig_meta,
        "mirror_meta": mirror_meta,
        "orig_headings": orig_headings,
        "mirror_headings": mirror_headings,
        "mirror_images": mirror_images,
        "pass": len(issues) == 0,
    }


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

    orig_ok = await ok(orig_url.rstrip("/") + "/favicon.ico")
    mirror_ok = await ok(mirror_url.rstrip("/") + "/favicon.ico")
    return {"orig_ok": orig_ok, "mirror_ok": mirror_ok, "pass": mirror_ok}
