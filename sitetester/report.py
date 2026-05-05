"""HTML report generation."""
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

from jinja2 import Environment, FileSystemLoader


def generate_report(results: List[Dict[str, Any]], config: Any) -> Path:
    templates_dir = Path(__file__).parent / "templates"
    env = Environment(loader=FileSystemLoader(str(templates_dir)), autoescape=True)
    template = env.get_template("report.html")

    passed = sum(1 for r in results if r.get("passed"))
    failed = len(results) - passed
    visual_issues = sum(
        1 for r in results
        if not r.get("visual_desktop", {}).get("pass", True)
        or not r.get("visual_mobile", {}).get("pass", True)
    )
    content_issues = sum(1 for r in results if r.get("content", {}).get("issues"))
    broken_links = sum(
        len(r.get("links", {}).get("broken_links", [])) for r in results
    )

    stats = {
        "total": len(results),
        "passed": passed,
        "failed": failed,
        "visual_issues": visual_issues,
        "content_issues": content_issues,
        "broken_links": broken_links,
    }

    meta = {
        "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "original_url": config.original_url,
        "mirror_url": config.mirror_url,
    }

    html = template.render(
        results=results,
        stats=stats,
        meta=meta,
        threshold=config.diff_threshold,
        check_mobile=config.check_mobile,
    )

    report_path = config.output_dir / "report.html"
    report_path.write_text(html, encoding="utf-8")
    return report_path
