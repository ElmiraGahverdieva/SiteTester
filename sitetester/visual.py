"""Pixel-level image comparison with blur (ignores small shifts) + screenshot annotation."""
from pathlib import Path
from typing import Any, Dict, List

import numpy as np
from PIL import Image, ImageDraw, ImageFilter


def compute_visual_diff(
    orig_path: Path,
    mirror_path: Path,
    diff_path: Path,
    threshold_pct: float,
    blur_radius: int = 4,
    pixel_sensitivity: int = 25,
) -> Dict[str, Any]:
    """
    Compare two screenshots.

    Перед сравнением оба изображения размываются (GaussianBlur), чтобы
    игнорировать смещения в несколько пикселей. Пиксели, которые отличаются
    даже после размытия, считаются реальными различиями.

    Цвет подсветки:
      КРАСНЫЙ  — если % различий > threshold_pct  (серьёзные отличия)
      ЖЁЛТЫЙ   — если % различий ≤ threshold_pct  (незначительные)
    """
    try:
        img1 = Image.open(orig_path).convert("RGB")
        img2 = Image.open(mirror_path).convert("RGB")

        w = max(img1.width, img2.width)
        h = max(img1.height, img2.height)

        def pad(img: Image.Image) -> Image.Image:
            if img.size == (w, h):
                return img
            canvas = Image.new("RGB", (w, h), (255, 255, 255))
            canvas.paste(img, (0, 0))
            return canvas

        img1 = pad(img1)
        img2 = pad(img2)

        # Размытие гасит пиксельные смещения (1-5 px)
        blur1 = img1.filter(ImageFilter.GaussianBlur(radius=blur_radius))
        blur2 = img2.filter(ImageFilter.GaussianBlur(radius=blur_radius))

        arr1_b = np.array(blur1, dtype=np.int32)
        arr2_b = np.array(blur2, dtype=np.int32)
        arr1   = np.array(img1,  dtype=np.uint8)

        channel_diff = np.abs(arr1_b - arr2_b)
        pixel_diff   = channel_diff.max(axis=2)
        diff_mask    = pixel_diff > pixel_sensitivity

        total_pixels = diff_mask.size
        diff_pixels  = int(diff_mask.sum())
        diff_pct     = diff_pixels / total_pixels * 100

        # Оверлей: затемнённый оригинал + цветные зоны различий
        base    = (arr1 * 0.22).astype(np.uint8)
        overlay = base.copy()
        color   = [210, 30, 30] if diff_pct > threshold_pct else [255, 210, 0]
        overlay[diff_mask] = color

        diff_path.parent.mkdir(parents=True, exist_ok=True)
        Image.fromarray(overlay).save(str(diff_path))

        return {
            "diff_pct":     round(diff_pct, 2),
            "diff_pixels":  diff_pixels,
            "total_pixels": total_pixels,
            "pass":         diff_pct <= threshold_pct,
            "diff_image":   str(diff_path),
        }
    except Exception as exc:
        return {
            "diff_pct": -1, "diff_pixels": 0, "total_pixels": 0,
            "pass": False, "error": str(exc), "diff_image": None,
        }


def annotate_screenshot(
    screenshot_path: Path,
    elements: List[Dict],
    output_path: Path,
) -> bool:
    """
    Рисует красные рамки на скриншоте в местах отсутствующих элементов.
    Сохраняет результат в output_path.
    """
    try:
        img = Image.open(screenshot_path).convert("RGBA")
        overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)

        for elem in elements:
            x = int(elem.get("x", 0))
            y = int(elem.get("y", 0))
            w = max(int(elem.get("w", 60)), 10)
            h = max(int(elem.get("h", 20)), 8)
            draw.rectangle(
                [x, y, x + w, y + h],
                fill=(255, 30, 30, 65),
                outline=(220, 0, 0, 255),
                width=3,
            )

        result = Image.alpha_composite(img, overlay).convert("RGB")
        output_path.parent.mkdir(parents=True, exist_ok=True)
        result.save(str(output_path))
        return True
    except Exception:
        return False
