# FILE: backend/app/utils/image_io.py
from __future__ import annotations

from pathlib import Path
from typing import BinaryIO
from typing import Any

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


def estimate_drawing_step_count(
    input_path: Path,
    default_steps: int,
    min_steps: int,
    max_steps: int,
) -> dict[str, Any]:
    image = cv2.imread(str(input_path), cv2.IMREAD_COLOR)
    if image is None:
        return {
            "step_count": default_steps,
            "reason": f"failed to read image: {input_path}",
        }

    height, width = image.shape[:2]
    scale = min(1.0, 512 / max(height, width))
    if scale < 1.0:
        image = cv2.resize(image, (max(1, int(width * scale)), max(1, int(height * scale))), interpolation=cv2.INTER_AREA)

    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    gray = cv2.bilateralFilter(gray, 7, 55, 55)
    edges = cv2.Canny(gray, 80, 180)
    edges = cv2.morphologyEx(edges, cv2.MORPH_CLOSE, np.ones((2, 2), dtype=np.uint8), iterations=1)

    area = max(1, edges.shape[0] * edges.shape[1])
    contours, _ = cv2.findContours(edges, cv2.RETR_LIST, cv2.CHAIN_APPROX_NONE)
    arcs = [float(cv2.arcLength(contour, closed=False)) for contour in contours]
    usable_arcs = [arc for arc in arcs if arc >= 24]
    long_arcs = [arc for arc in usable_arcs if arc >= 80]
    edge_density = float(np.count_nonzero(edges)) / area
    total_arc = float(sum(usable_arcs))
    diagonal = float(np.hypot(*edges.shape))

    complexity = (
        edge_density * 95.0
        + min(len(usable_arcs), 140) * 0.055
        + min(len(long_arcs), 70) * 0.075
        + min(total_arc / max(diagonal, 1.0), 160.0) * 0.018
    )

    if complexity < 2.0:
        step_count = min_steps
        bucket = "simple"
    elif complexity < 3.8:
        step_count = max(min_steps, min(default_steps, max_steps))
        bucket = "normal"
    else:
        extra_ratio = min(1.0, (complexity - 3.8) / 7.0)
        step_count = round(default_steps + extra_ratio * (max_steps - default_steps))
        bucket = "complex"

    step_count = int(max(min_steps, min(max_steps, step_count)))
    return {
        "step_count": step_count,
        "bucket": bucket,
        "complexity": round(complexity, 4),
        "edge_density": round(edge_density, 5),
        "usable_contours": len(usable_arcs),
        "long_contours": len(long_arcs),
        "total_arc": round(total_arc, 2),
        "default_steps": default_steps,
        "min_steps": min_steps,
        "max_steps": max_steps,
    }


def ensure_png_white_background(input_path: Path, output_path: Path) -> None:
    image = Image.open(input_path).convert("RGBA")
    bg = Image.new("RGBA", image.size, (255, 255, 255, 255))
    merged = Image.alpha_composite(bg, image).convert("RGB")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    merged.save(output_path)


def _remove_small_components(mask: np.ndarray, min_pixels: int) -> np.ndarray:
    labels_count, labels, stats, _ = cv2.connectedComponentsWithStats(mask.astype(np.uint8), connectivity=8)
    cleaned = np.zeros_like(mask, dtype=np.uint8)
    for label in range(1, labels_count):
        if int(stats[label, cv2.CC_STAT_AREA]) >= min_pixels:
            cleaned[labels == label] = 1
    return cleaned


def _zhang_suen_thinning(mask: np.ndarray, max_iterations: int = 80) -> np.ndarray:
    image = (mask > 0).astype(np.uint8)
    if not np.any(image):
        return image

    for _ in range(max_iterations):
        changed = False

        for sub_iteration in (0, 1):
            padded = np.pad(image, 1, mode="constant")
            p2 = padded[:-2, 1:-1]
            p3 = padded[:-2, 2:]
            p4 = padded[1:-1, 2:]
            p5 = padded[2:, 2:]
            p6 = padded[2:, 1:-1]
            p7 = padded[2:, :-2]
            p8 = padded[1:-1, :-2]
            p9 = padded[:-2, :-2]

            neighbors = p2 + p3 + p4 + p5 + p6 + p7 + p8 + p9
            transitions = (
                ((p2 == 0) & (p3 == 1)).astype(np.uint8)
                + ((p3 == 0) & (p4 == 1)).astype(np.uint8)
                + ((p4 == 0) & (p5 == 1)).astype(np.uint8)
                + ((p5 == 0) & (p6 == 1)).astype(np.uint8)
                + ((p6 == 0) & (p7 == 1)).astype(np.uint8)
                + ((p7 == 0) & (p8 == 1)).astype(np.uint8)
                + ((p8 == 0) & (p9 == 1)).astype(np.uint8)
                + ((p9 == 0) & (p2 == 1)).astype(np.uint8)
            )

            if sub_iteration == 0:
                branch_condition = (p2 * p4 * p6 == 0) & (p4 * p6 * p8 == 0)
            else:
                branch_condition = (p2 * p4 * p8 == 0) & (p2 * p6 * p8 == 0)

            removable = (
                (image == 1)
                & (neighbors >= 2)
                & (neighbors <= 6)
                & (transitions == 1)
                & branch_condition
            )

            if np.any(removable):
                image[removable] = 0
                changed = True

        if not changed:
            break

    return image


def _compact_ink_features(ink: np.ndarray) -> np.ndarray:
    labels_count, labels, stats, centroids = cv2.connectedComponentsWithStats(ink.astype(np.uint8), connectivity=8)
    height, width = ink.shape
    max_feature_side = max(8, int(min(height, width) * 0.09))
    image_area = max(1, height * width)
    features = np.zeros_like(ink, dtype=np.uint8)

    for label in range(1, labels_count):
        x = int(stats[label, cv2.CC_STAT_LEFT])
        y = int(stats[label, cv2.CC_STAT_TOP])
        w = int(stats[label, cv2.CC_STAT_WIDTH])
        h = int(stats[label, cv2.CC_STAT_HEIGHT])
        area = int(stats[label, cv2.CC_STAT_AREA])
        if area < 18 or area > image_area * 0.004:
            continue
        if w > max_feature_side or h > max_feature_side:
            continue
        aspect = w / max(h, 1)
        fill_ratio = area / max(w * h, 1)
        if aspect < 0.45 or aspect > 2.2 or fill_ratio < 0.35:
            continue

        cx, cy = centroids[label]
        radius = max(3, min(w, h) // 4)
        cv2.circle(features, (int(round(cx)), int(round(cy))), radius, 1, thickness=-1, lineType=cv2.LINE_AA)

    return features


def _centerline_from_ink(gray: np.ndarray) -> np.ndarray | None:
    smoothed = cv2.bilateralFilter(gray, 7, 55, 55)
    ink = smoothed < 230
    image_area = max(1, gray.shape[0] * gray.shape[1])
    ink_ratio = float(np.count_nonzero(ink)) / image_area
    white_ratio = float(np.count_nonzero(smoothed > 245)) / image_area

    if ink_ratio < 0.002 or ink_ratio > 0.35 or white_ratio < 0.55:
        return None

    ink = cv2.morphologyEx(ink.astype(np.uint8), cv2.MORPH_CLOSE, np.ones((3, 3), dtype=np.uint8), iterations=1)
    ink = _remove_small_components(ink, min_pixels=24)
    compact_features = _compact_ink_features(ink)
    skeleton = _zhang_suen_thinning(ink)
    skeleton = _remove_small_components(skeleton, min_pixels=12)
    skeleton = np.maximum(skeleton, compact_features)

    if np.count_nonzero(skeleton) < 40:
        return None

    return cv2.dilate(skeleton * 255, np.ones((2, 2), dtype=np.uint8), iterations=1)


def _edges_from_canny(gray: np.ndarray) -> np.ndarray:
    gray = cv2.bilateralFilter(gray, 7, 55, 55)
    edges = cv2.Canny(gray, 105, 220)

    contours, _ = cv2.findContours(edges, cv2.RETR_LIST, cv2.CHAIN_APPROX_NONE)
    image_area = max(1, gray.shape[0] * gray.shape[1])
    selected: list[tuple[float, float, float, np.ndarray]] = []
    for contour in contours:
        arc = float(cv2.arcLength(contour, closed=False))
        area = float(abs(cv2.contourArea(contour)))
        if arc < 44:
            continue
        if area < image_area * 0.0001 and arc < 110:
            continue
        x, y, w, h = cv2.boundingRect(contour)
        score = area + arc * 1.2 + max(w, h) * 8 - min(w, h) * 0.2
        selected.append((score, area, arc, contour))

    selected.sort(key=lambda item: item[0], reverse=True)
    selected = selected[:22]

    simplified = np.zeros_like(edges)
    for _, _, _, contour in selected:
        epsilon = max(1.3, 0.004 * cv2.arcLength(contour, closed=False))
        approx = cv2.approxPolyDP(contour, epsilon, closed=False)
        cv2.polylines(simplified, [approx], isClosed=False, color=255, thickness=2, lineType=cv2.LINE_AA)

    if np.count_nonzero(simplified) < 40:
        simplified = edges

    return cv2.morphologyEx(simplified, cv2.MORPH_CLOSE, np.ones((2, 2), dtype=np.uint8), iterations=1)


def normalize_generated_lineart(
    input_path: Path,
    output_path: Path,
    size: int | None = None,
) -> tuple[int, int]:
    image = cv2.imread(str(input_path), cv2.IMREAD_COLOR)
    if image is None:
        raise RuntimeError(f"Failed to read generated image: {input_path}")

    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    edges = _centerline_from_ink(gray)
    if edges is None:
        edges = _edges_from_canny(gray)

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
