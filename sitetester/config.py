from dataclasses import dataclass, field
from pathlib import Path
from typing import List


@dataclass
class Config:
    original_url: str
    mirror_url: str
    output_dir: Path
    mode: str = "both"           # 'sitemap' | 'crawl' | 'both'
    max_pages: int = 50
    exclude_selectors: List[str] = field(default_factory=list)
    diff_threshold: float = 8.0  # % diff → красный (выше), жёлтый (ниже)
    blur_radius: int = 4         # размытие перед сравнением (гасит пиксельные смещения)
    pixel_sensitivity: int = 25  # порог разницы пикселя (0-255)
    check_mobile: bool = True
    desktop_width: int = 1920
    desktop_height: int = 1080
    mobile_width: int = 375
    page_timeout: int = 30000    # ms
    network_timeout: int = 10    # секунд для aiohttp
