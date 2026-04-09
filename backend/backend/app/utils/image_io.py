# FILE: backend/app/utils/image_io.py
from __future__ import annotations

from pathlib import Path
from typing import BinaryIO

import cv2
import numpy as np
from PIL import Image


def save_upload_image(file_obj: BinaryIO, save_path: Path) -> None:
    save_path.parent.mkdir(parents=True, exist_ok=True)
    image = Image.open(file_obj).convert("RGB")
    image.save(save_path)


def resize_for_recognition(input_path: Path, output_path: Path, max_side: int) -> tuple[int, int]:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    image = Image.open(input_path).convert("RGB")
    w, h = image.size

    scale = min(1.0, max_side / max(w, h))
    new_size = (max(1, int(w * scale)), max(1, int(h * scale)))

    if new_size != (w, h):
        image = image.resize(new_size, Image.LANCZOS)

    image.save(output_path)
    return new_size


def ensure_png_white_background(input_path: Path, output_path: Path) -> None:
    image = Image.open(input_path).convert("RGBA")
    bg = Image.new("RGBA", image.size, (255, 255, 255, 255))
    merged = Image.alpha_composite(bg, image).convert("RGB")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    merged.save(output_path)


def normalize_generated_lineart(
    input_path: Path,
    output_path: Path,
    size: int | None = None,
) -> tuple[int, int]:
    image = cv2.imread(str(input_path), cv2.IMREAD_COLOR)
    if image is None:
        raise RuntimeError(f"Failed to read generated image: {input_path}")

    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    edges = cv2.Canny(gray, 70, 160)
    edges = cv2.dilate(edges, np.ones((2, 2), dtype=np.uint8), iterations=1)

    height, width = edges.shape
    margin_x = max(8, int(width * 0.08))
    margin_y = max(8, int(height * 0.08))
    focus_mask = np.zeros_like(edges, dtype=bool)
    focus_mask[margin_y : height - margin_y, margin_x : width - margin_x] = True

    ys, xs = np.where((edges > 0) & focus_mask)
    if len(xs) == 0 or len(ys) == 0:
        ys, xs = np.where(edges > 0)
    if len(xs) == 0 or len(ys) == 0:
        raise RuntimeError("No line art edges were detected in generated image")

    x0, x1 = int(xs.min()), int(xs.max())
    y0, y1 = int(ys.min()), int(ys.max())
    pad_x = max(12, int((x1 - x0 + 1) * 0.08))
    pad_y = max(12, int((y1 - y0 + 1) * 0.08))
    x0 = max(0, x0 - pad_x)
    y0 = max(0, y0 - pad_y)
    x1 = min(width - 1, x1 + pad_x)
    y1 = min(height - 1, y1 + pad_y)

    cropped = edges[y0 : y1 + 1, x0 : x1 + 1]
    cropped = cv2.morphologyEx(cropped, cv2.MORPH_CLOSE, np.ones((3, 3), dtype=np.uint8), iterations=1)

    target_size = size or max(cropped.shape[0], cropped.shape[1])
    canvas = np.full((target_size, target_size), 255, dtype=np.uint8)
    draw_h, draw_w = cropped.shape
    scale = min((target_size * 0.86) / max(draw_w, 1), (target_size * 0.86) / max(draw_h, 1))
    resized_w = max(1, int(draw_w * scale))
    resized_h = max(1, int(draw_h * scale))
    resized = cv2.resize(cropped, (resized_w, resized_h), interpolation=cv2.INTER_AREA)

    top = (target_size - resized_h) // 2
    left = (target_size - resized_w) // 2
    canvas[top : top + resized_h, left : left + resized_w] = 255 - resized

    output_path.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(output_path), canvas)
    return (target_size, target_size)
