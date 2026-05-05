"""Pixel-level image comparison and diff generation."""
from pathlib import Path
from typing import Dict, Any

import numpy as np
from PIL import Image


def compute_visual_diff(
    orig_path: Path,
    mirror_path: Path,
    diff_path: Path,
    threshold_pct: float,
    pixel_sensitivity: int = 10,
) -> Dict[str, Any]:
    """
    Compare two full-page screenshots and produce a diff overlay image.

    Diff pixels are coloured:
      - RED   if total diff area > threshold_pct  (major regression)
      - YELLOW if total diff area <= threshold_pct (minor drift)
    Non-diff pixels are rendered as a dimmed version of the original.
    """
    try:
        img1 = Image.open(orig_path).convert("RGB")
        img2 = Image.open(mirror_path).convert("RGB")

        # Normalise to identical canvas size (use maximum of both)
        w = max(img1.width, img2.width)
        h = max(img1.height, img2.height)

        def pad(img: Image.Image) -> np.ndarray:
            if img.size == (w, h):
                return np.array(img, dtype=np.int32)
            canvas = Image.new("RGB", (w, h), (255, 255, 255))
            canvas.paste(img, (0, 0))
            return np.array(canvas, dtype=np.int32)

        arr1 = pad(img1)
        arr2 = pad(img2)

        channel_diff = np.abs(arr1 - arr2)
        pixel_diff = channel_diff.max(axis=2)  # worst channel per pixel

        diff_mask = pixel_diff > pixel_sensitivity
        total_pixels = diff_mask.size
        diff_pixels = int(diff_mask.sum())
        diff_pct = diff_pixels / total_pixels * 100

        # Build overlay: dim original + highlight changed pixels
        base = (arr1 * 0.22).astype(np.uint8)
        overlay = base.copy()
        highlight = [220, 30, 30] if diff_pct > threshold_pct else [255, 215, 0]
        overlay[diff_mask] = highlight

        diff_path.parent.mkdir(parents=True, exist_ok=True)
        Image.fromarray(overlay).save(str(diff_path))

        return {
            "diff_pct": round(diff_pct, 2),
            "diff_pixels": diff_pixels,
            "total_pixels": total_pixels,
            "pass": diff_pct <= threshold_pct,
            "diff_image": str(diff_path),
        }
    except Exception as exc:
        return {
            "diff_pct": -1,
            "diff_pixels": 0,
            "total_pixels": 0,
            "pass": False,
            "error": str(exc),
            "diff_image": None,
        }
