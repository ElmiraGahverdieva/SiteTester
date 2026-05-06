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
    Рисует яркие пронумерованные рамки на скриншоте для каждого
    отсутствующего элемента. Номер и текст ссылки — в метке над рамкой.
    """
    try:
        from PIL import ImageFont

        img  = Image.open(screenshot_path).convert("RGBA")
        W, H = img.size

        overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
        draw    = ImageDraw.Draw(overlay)

        # Пытаемся загрузить читаемый шрифт; падаем на встроенный
        try:
            font_big   = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 28)
            font_small = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 18)
        except Exception:
            try:
                font_big   = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 28)
                font_small = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 18)
            except Exception:
                font_big = font_small = ImageFont.load_default()

        for i, elem in enumerate(elements, 1):
            x = max(int(elem.get("x", 0)), 0)
            y = max(int(elem.get("y", 0)), 0)
            w = max(int(elem.get("w", 120)), 30)
            h = max(int(elem.get("h", 24)), 14)

            # Ограничиваем по размеру страницы
            x2 = min(x + w, W - 1)
            y2 = min(y + h, H - 1)

            # Яркая полупрозрачная заливка
            draw.rectangle([x, y, x2, y2], fill=(255, 0, 0, 90))
            # Жирная рамка — 5 пикселей
            for off in range(5):
                draw.rectangle([x - off, y - off, x2 + off, y2 + off],
                               outline=(220, 0, 0, 255))

            # Метка с номером над рамкой
            label_text = f" {i} "
            link_text  = (elem.get("text") or elem.get("abs_href") or "")[:40]

            lx = x
            ly = max(y - 28, 2)

            # Фон метки
            try:
                bbox = draw.textbbox((lx, ly), label_text, font=font_big)
                lw = bbox[2] - bbox[0]
                lh = bbox[3] - bbox[1]
            except AttributeError:
                lw, lh = 24, 20

            draw.rectangle([lx, ly, lx + lw + 6, ly + lh + 4], fill=(220, 0, 0, 230))
            draw.text((lx + 3, ly + 2), label_text, fill=(255, 255, 255, 255), font=font_big)

            # Текст ссылки рядом с номером
            if link_text:
                tx = lx + lw + 10
                draw.rectangle([tx, ly, tx + len(link_text) * 8 + 6, ly + lh + 4],
                               fill=(40, 40, 40, 200))
                draw.text((tx + 3, ly + 2), link_text, fill=(255, 255, 200, 255), font=font_small)

        result = Image.alpha_composite(img, overlay).convert("RGB")
        output_path.parent.mkdir(parents=True, exist_ok=True)
        result.save(str(output_path))
        return True
    except Exception:
        return False
