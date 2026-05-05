#!/usr/bin/env python3
"""SiteTester CLI — automated visual & content comparison of two websites."""
import asyncio
from pathlib import Path

import click

from sitetester.config import Config
from sitetester import runner


@click.command(context_settings={"help_option_names": ["-h", "--help"]})
@click.argument("original_url")
@click.argument("mirror_url")
@click.option("-o", "--output", default="output", show_default=True, help="Output directory for report and screenshots.")
@click.option(
    "--mode",
    type=click.Choice(["sitemap", "crawl", "both"], case_sensitive=False),
    default="both",
    show_default=True,
    help="URL collection strategy.",
)
@click.option("--max-pages", default=50, show_default=True, help="Maximum number of pages to check.")
@click.option(
    "--exclude", "-e",
    multiple=True,
    metavar="SELECTOR",
    help="CSS selector to hide before screenshot (repeatable). E.g. -e '.chat-widget' -e '#cookie-bar'",
)
@click.option("--threshold", default=2.0, show_default=True, help="Pixel diff % above which differences are highlighted red (below = yellow).")
@click.option("--no-mobile", is_flag=True, default=False, help="Skip mobile (375 px) screenshot checks.")
def main(original_url, mirror_url, output, mode, max_pages, exclude, threshold, no_mobile):
    """
    Compare ORIGINAL_URL and MIRROR_URL page-by-page.

    Produces an interactive HTML report with side-by-side screenshots,
    visual diff overlays, SEO/content checks, and link verification.

    \b
    Examples:
      python main.py https://example.com https://staging.example.com
      python main.py https://old.co https://new.co --mode crawl --max-pages 100
      python main.py https://a.com https://b.com -e ".live-chat" -e "#cookie-notice"
    """
    config = Config(
        original_url=original_url.rstrip("/"),
        mirror_url=mirror_url.rstrip("/"),
        output_dir=Path(output),
        mode=mode.lower(),
        max_pages=max_pages,
        exclude_selectors=list(exclude),
        diff_threshold=threshold,
        check_mobile=not no_mobile,
    )
    asyncio.run(runner.run(config))


if __name__ == "__main__":
    main()
