from __future__ import annotations

from pathlib import Path
from typing import Any

import cv2
import numpy as np
from PIL import Image, ImageDraw

from app.config import settings


class StepBuilder:
    def _duck_core_parts_present(
        self,
        part_masks: dict[str, np.ndarray],
        parts: list[str],
        subject_label: str,
    ) -> bool:
        subject_alias = self._subject_alias(subject_label)
        if subject_alias != "duck":
            return True

        canonical_pixel_counts: dict[str, int] = {}
        for part in parts:
            canonical = self._canonical_part_name(part, subject_alias)
            mask = part_masks.get(part)
            pixels = int(mask.sum()) if mask is not None else 0
            canonical_pixel_counts[canonical] = max(canonical_pixel_counts.get(canonical, 0), pixels)

        head_pixels = canonical_pixel_counts.get("head", 0)
        beak_pixels = canonical_pixel_counts.get("beak", 0)
        eye_pixels = max(canonical_pixel_counts.get("eye", 0), canonical_pixel_counts.get("eyes", 0))
        body_pixels = max(
            canonical_pixel_counts.get("body", 0),
            canonical_pixel_counts.get("back", 0) + canonical_pixel_counts.get("belly", 0),
        )

        return head_pixels >= 80 and beak_pixels >= 60 and eye_pixels >= 20 and body_pixels >= 800

    def _render_steps_from_masks(
        self,
        black_mask: np.ndarray,
        output_dir: Path,
        step_plan: dict[str, Any],
        fps: int,
        parts: list[str],
        part_masks: dict[str, np.ndarray],
    ) -> dict[str, Any]:
        steps = list(step_plan.get("steps") or [])
        height, width = black_mask.shape
        timestamps: list[float] = []
        prompts: list[str] = []

        for i, step in enumerate(steps):
            visible_parts = [
                str(part).strip()
                for part in step.get("visible_parts") or step.get("keep_parts") or step.get("new_parts") or []
                if str(part).strip()
            ]
            if not visible_parts:
                visible_parts = parts[: max(1, min(len(parts), i + 1))]

            canvas = np.full((height, width), 255, dtype=np.uint8)
            composed_mask = np.zeros_like(black_mask, dtype=bool)
            for part in visible_parts:
                if part in part_masks:
                    composed_mask |= part_masks[part]

            if not np.any(composed_mask):
                flat_indices = np.flatnonzero(black_mask)
                keep = max(1, int(len(flat_indices) * (i + 1) / max(len(steps), 1)))
                selected = flat_indices[:keep]
                composed_mask.flat[selected] = True

            canvas[composed_mask] = 0

            rgb = cv2.cvtColor(canvas, cv2.COLOR_GRAY2BGR)
            frame_path = output_dir / f"frame_{i:03d}.png"
            cv2.imwrite(str(frame_path), rgb)

            timestamps.append(round(i / fps, 4))
            prompts.append(str(step.get("instruction") or f"Step {i + 1}"))

        return {
            "stepCount": len(steps),
            "timestamps": timestamps,
            "prompts": prompts,
        }

    def _duck_part_pixel_masks(
        self,
        black_mask: np.ndarray,
        parts: list[str],
    ) -> dict[str, np.ndarray]:
        height, width = black_mask.shape
        xs = np.linspace(0.0, 1.0, width)
        ys = np.linspace(0.0, 1.0, height)
        x_grid = np.broadcast_to(xs, (height, width))
        y_grid = np.broadcast_to(ys[:, None], (height, width))

        region_masks: dict[str, np.ndarray] = {}
        for part in parts:
            geometry_mask = self._part_geometry_mask(part, "duck", x_grid, y_grid)
            if geometry_mask is not None:
                region_masks[part] = geometry_mask
                continue

            region = self._part_region(part, "duck")
            if region is None:
                continue
            x0, y0, x1, y1 = region
            region_masks[part] = (x_grid >= x0) & (x_grid <= x1) & (y_grid >= y0) & (y_grid <= y1)

        canonical_to_part = {
            self._canonical_part_name(part, "duck"): part
            for part in parts
            if part in region_masks
        }

        def region_for(canonical_name: str) -> np.ndarray:
            part_key = canonical_to_part.get(canonical_name)
            if part_key is None:
                return np.zeros_like(black_mask, dtype=bool)
            return region_masks.get(part_key, np.zeros_like(black_mask, dtype=bool))

        specific_regions: dict[str, np.ndarray] = {}
        for part, region_mask in region_masks.items():
            canonical = self._canonical_part_name(part, "duck")
            refined = region_mask.copy()

            if canonical == "head":
                refined &= ~region_for("beak")
                refined &= ~region_for("eye")
                refined &= ~region_for("eyes")
                refined &= ~region_for("neck")
            elif canonical == "back":
                refined &= ~region_for("wing")
                refined &= ~region_for("tail")
                refined &= ~region_for("neck")
            elif canonical == "belly":
                refined &= ~region_for("legs")
                refined &= ~region_for("feet")
                refined &= ~region_for("wing")
            elif canonical == "legs":
                refined &= ~region_for("feet")
            elif canonical == "body":
                refined &= ~region_for("neck")
                refined &= ~region_for("back")
                refined &= ~region_for("belly")
                refined &= ~region_for("wing")
                refined &= ~region_for("tail")
                refined &= ~region_for("legs")
                refined &= ~region_for("feet")

            specific_regions[part] = refined

        part_masks = {
            part: black_mask & specific_regions.get(part, np.zeros_like(black_mask, dtype=bool))
            for part in parts
        }

        assigned = np.zeros_like(black_mask, dtype=bool)
        for mask in part_masks.values():
            assigned |= mask

        fallback_part = next(
            (
                part
                for part in parts
                if self._canonical_part_name(part, "duck") in {"belly", "back", "body"}
            ),
            parts[-1] if parts else None,
        )
        uncovered = black_mask & ~assigned
        if fallback_part is not None and np.any(uncovered):
            part_masks[fallback_part] |= uncovered

        return part_masks

    def _draw_template_part(
        self,
        draw: ImageDraw.ImageDraw,
        subject_alias: str,
        canonical_part: str,
        size: int,
    ) -> None:
        s = size
        if subject_alias == "cat":
            if canonical_part == "head":
                draw.ellipse((s * 0.28, s * 0.16, s * 0.72, s * 0.50), outline="black", width=6)
            elif canonical_part == "ears":
                draw.polygon(
                    [(s * 0.34, s * 0.18), (s * 0.42, s * 0.06), (s * 0.47, s * 0.23)],
                    outline="black",
                    width=6,
                )
                draw.polygon(
                    [(s * 0.53, s * 0.23), (s * 0.58, s * 0.06), (s * 0.66, s * 0.18)],
                    outline="black",
                    width=6,
                )
            elif canonical_part == "eyes":
                draw.ellipse((s * 0.39, s * 0.28, s * 0.46, s * 0.36), outline="black", width=4)
                draw.ellipse((s * 0.54, s * 0.28, s * 0.61, s * 0.36), outline="black", width=4)
            elif canonical_part == "cheeks":
                draw.ellipse((s * 0.33, s * 0.35, s * 0.39, s * 0.40), outline="black", width=3)
                draw.ellipse((s * 0.61, s * 0.35, s * 0.67, s * 0.40), outline="black", width=3)
            elif canonical_part == "nose_mouth":
                draw.polygon(
                    [(s * 0.48, s * 0.36), (s * 0.52, s * 0.36), (s * 0.50, s * 0.40)],
                    outline="black",
                    width=4,
                )
                draw.arc((s * 0.43, s * 0.38, s * 0.50, s * 0.46), 210, 340, fill="black", width=3)
                draw.arc((s * 0.50, s * 0.38, s * 0.57, s * 0.46), 200, 330, fill="black", width=3)
            elif canonical_part == "whiskers":
                draw.line((s * 0.26, s * 0.36, s * 0.42, s * 0.38), fill="black", width=3)
                draw.line((s * 0.24, s * 0.40, s * 0.42, s * 0.40), fill="black", width=3)
                draw.line((s * 0.26, s * 0.44, s * 0.42, s * 0.42), fill="black", width=3)
                draw.line((s * 0.58, s * 0.38, s * 0.74, s * 0.36), fill="black", width=3)
                draw.line((s * 0.58, s * 0.40, s * 0.76, s * 0.40), fill="black", width=3)
                draw.line((s * 0.58, s * 0.42, s * 0.74, s * 0.44), fill="black", width=3)
            elif canonical_part == "body":
                draw.ellipse((s * 0.28, s * 0.46, s * 0.72, s * 0.88), outline="black", width=6)
            elif canonical_part == "front_legs":
                draw.line((s * 0.43, s * 0.60, s * 0.43, s * 0.88), fill="black", width=6)
                draw.line((s * 0.57, s * 0.60, s * 0.57, s * 0.88), fill="black", width=6)
            elif canonical_part == "back_legs":
                draw.arc((s * 0.27, s * 0.66, s * 0.43, s * 0.92), 70, 250, fill="black", width=5)
                draw.arc((s * 0.57, s * 0.66, s * 0.73, s * 0.92), 290, 110, fill="black", width=5)
            elif canonical_part == "tail":
                draw.arc((s * 0.62, s * 0.50, s * 0.92, s * 0.88), 240, 80, fill="black", width=6)
            elif canonical_part == "bow":
                draw.polygon(
                    [(s * 0.43, s * 0.49), (s * 0.35, s * 0.46), (s * 0.39, s * 0.54)],
                    outline="black",
                    width=4,
                )
                draw.polygon(
                    [(s * 0.57, s * 0.49), (s * 0.65, s * 0.46), (s * 0.61, s * 0.54)],
                    outline="black",
                    width=4,
                )
                draw.ellipse((s * 0.47, s * 0.47, s * 0.53, s * 0.55), outline="black", width=4)
            elif canonical_part == "ground_line":
                draw.line((s * 0.20, s * 0.90, s * 0.80, s * 0.90), fill="black", width=5)

        if subject_alias == "duck":
            if canonical_part == "head":
                draw.ellipse((s * 0.54, s * 0.16, s * 0.72, s * 0.30), outline="black", width=5)
            elif canonical_part == "beak":
                draw.line((s * 0.72, s * 0.22, s * 0.84, s * 0.24), fill="black", width=4)
                draw.line((s * 0.72, s * 0.28, s * 0.83, s * 0.26), fill="black", width=4)
                draw.line((s * 0.72, s * 0.22, s * 0.72, s * 0.28), fill="black", width=4)
                draw.line((s * 0.76, s * 0.24, s * 0.80, s * 0.24), fill="black", width=3)
            elif canonical_part == "eye" or canonical_part == "eyes":
                draw.ellipse((s * 0.61, s * 0.20, s * 0.65, s * 0.24), outline="black", width=3)
                draw.ellipse((s * 0.625, s * 0.215, s * 0.635, s * 0.225), fill="black")
            elif canonical_part == "neck":
                draw.arc((s * 0.44, s * 0.20, s * 0.70, s * 0.58), 200, 320, fill="black", width=5)
                draw.arc((s * 0.50, s * 0.20, s * 0.74, s * 0.60), 190, 300, fill="black", width=5)
            elif canonical_part == "back":
                draw.arc((s * 0.20, s * 0.30, s * 0.74, s * 0.78), 210, 355, fill="black", width=6)
            elif canonical_part == "belly":
                draw.arc((s * 0.22, s * 0.42, s * 0.72, s * 0.86), 10, 180, fill="black", width=6)
            elif canonical_part == "body":
                draw.arc((s * 0.20, s * 0.30, s * 0.74, s * 0.78), 210, 355, fill="black", width=6)
                draw.arc((s * 0.22, s * 0.42, s * 0.72, s * 0.86), 10, 180, fill="black", width=6)
            elif canonical_part == "wing":
                draw.arc((s * 0.34, s * 0.48, s * 0.60, s * 0.72), 215, 30, fill="black", width=4)
                draw.arc((s * 0.40, s * 0.52, s * 0.58, s * 0.70), 210, 35, fill="black", width=3)
                draw.line((s * 0.43, s * 0.56, s * 0.51, s * 0.66), fill="black", width=3)
            elif canonical_part == "legs":
                draw.line((s * 0.42, s * 0.76, s * 0.40, s * 0.90), fill="black", width=4)
                draw.line((s * 0.54, s * 0.76, s * 0.52, s * 0.90), fill="black", width=4)
            elif canonical_part == "feet":
                draw.line((s * 0.34, s * 0.90, s * 0.43, s * 0.90), fill="black", width=4)
                draw.line((s * 0.43, s * 0.90, s * 0.47, s * 0.94), fill="black", width=4)
                draw.line((s * 0.43, s * 0.90, s * 0.48, s * 0.90), fill="black", width=4)
                draw.line((s * 0.43, s * 0.90, s * 0.47, s * 0.86), fill="black", width=4)
                draw.line((s * 0.46, s * 0.90, s * 0.55, s * 0.90), fill="black", width=4)
                draw.line((s * 0.55, s * 0.90, s * 0.59, s * 0.94), fill="black", width=4)
                draw.line((s * 0.55, s * 0.90, s * 0.60, s * 0.90), fill="black", width=4)
                draw.line((s * 0.55, s * 0.90, s * 0.59, s * 0.86), fill="black", width=4)
            elif canonical_part == "tail":
                draw.line((s * 0.24, s * 0.54, s * 0.14, s * 0.50), fill="black", width=4)
                draw.line((s * 0.24, s * 0.56, s * 0.14, s * 0.61), fill="black", width=4)
                draw.line((s * 0.24, s * 0.54, s * 0.24, s * 0.58), fill="black", width=4)
            elif canonical_part == "ground_line":
                draw.line((s * 0.16, s * 0.94, s * 0.72, s * 0.94), fill="black", width=4)

    def _build_template_steps(
        self,
        output_dir: Path,
        step_plan: dict[str, Any],
        fps: int,
        subject_alias: str,
        canvas_size: int,
    ) -> dict[str, Any]:
        steps = list(step_plan.get("steps") or [])
        timestamps: list[float] = []
        prompts: list[str] = []

        for i, step in enumerate(steps):
            image = Image.new("RGB", (canvas_size, canvas_size), "white")
            draw = ImageDraw.Draw(image)
            visible_parts = [
                self._canonical_part_name(str(part), subject_alias)
                for part in step.get("visible_parts") or step.get("new_parts") or []
            ]
            for part in visible_parts:
                self._draw_template_part(draw, subject_alias, part, canvas_size)

            image.save(output_dir / f"frame_{i:03d}.png")
            timestamps.append(round(i / fps, 4))
            prompts.append(str(step.get("instruction") or f"Step {i + 1}"))

        return {
            "stepCount": len(steps),
            "timestamps": timestamps,
            "prompts": prompts,
        }

    def _part_geometry_mask(
        self,
        part_name: str,
        subject_alias: str,
        x_grid: np.ndarray,
        y_grid: np.ndarray,
    ) -> np.ndarray | None:
        part = self._canonical_part_name(part_name, subject_alias)

        if subject_alias in {"cat", "dog"}:
            if part == "head":
                outer = ((x_grid - 0.50) / 0.23) ** 2 + ((y_grid - 0.28) / 0.16) ** 2 <= 1.0
                inner = ((x_grid - 0.50) / 0.18) ** 2 + ((y_grid - 0.28) / 0.12) ** 2 <= 1.0
                return outer & ~inner
            if part == "body":
                outer = ((x_grid - 0.50) / 0.23) ** 2 + ((y_grid - 0.66) / 0.27) ** 2 <= 1.0
                inner = ((x_grid - 0.50) / 0.17) ** 2 + ((y_grid - 0.66) / 0.20) ** 2 <= 1.0
                return outer & ~inner

        if subject_alias == "duck":
            if part == "head":
                return (x_grid >= 0.28) & (x_grid <= 0.78) & (y_grid >= 0.06) & (y_grid <= 0.36)
            if part == "beak":
                left_side = (x_grid >= 0.06) & (x_grid <= 0.46) & (y_grid >= 0.10) & (y_grid <= 0.32)
                right_side = (x_grid >= 0.54) & (x_grid <= 0.94) & (y_grid >= 0.10) & (y_grid <= 0.32)
                return left_side | right_side
            if part in {"eye", "eyes"}:
                return (x_grid >= 0.38) & (x_grid <= 0.68) & (y_grid >= 0.12) & (y_grid <= 0.24)
            if part == "neck":
                return (x_grid >= 0.34) & (x_grid <= 0.64) & (y_grid >= 0.22) & (y_grid <= 0.58)
            if part == "back":
                return (x_grid >= 0.18) & (x_grid <= 0.82) & (y_grid >= 0.24) & (y_grid <= 0.58)
            if part == "belly":
                return (x_grid >= 0.20) & (x_grid <= 0.82) & (y_grid >= 0.46) & (y_grid <= 0.88)
            if part == "body":
                outer = ((x_grid - 0.46) / 0.30) ** 2 + ((y_grid - 0.60) / 0.24) ** 2 <= 1.0
                inner = ((x_grid - 0.46) / 0.22) ** 2 + ((y_grid - 0.60) / 0.18) ** 2 <= 1.0
                return outer & ~inner
            if part == "wing":
                outer = ((x_grid - 0.48) / 0.18) ** 2 + ((y_grid - 0.58) / 0.14) ** 2 <= 1.0
                inner = ((x_grid - 0.48) / 0.12) ** 2 + ((y_grid - 0.58) / 0.08) ** 2 <= 1.0
                return outer & ~inner
            if part == "tail":
                left_side = (x_grid >= 0.08) & (x_grid <= 0.30) & (y_grid >= 0.40) & (y_grid <= 0.68)
                right_side = (x_grid >= 0.70) & (x_grid <= 0.92) & (y_grid >= 0.40) & (y_grid <= 0.68)
                return left_side | right_side
            if part == "legs":
                return (x_grid >= 0.30) & (x_grid <= 0.64) & (y_grid >= 0.66) & (y_grid <= 0.92)
            if part == "feet":
                return (x_grid >= 0.22) & (x_grid <= 0.70) & (y_grid >= 0.84) & (y_grid <= 0.98)

        return None

    def _canonical_part_name(self, part_name: str, subject_alias: str) -> str:
        lowered = (part_name or "").strip().lower()

        if subject_alias == "duck":
            if any(keyword in lowered for keyword in ("喙", "鸭嘴", "嘴巴", "嘴")):
                return "beak"
            if "脚蹼" in lowered:
                return "feet"
            if any(keyword in lowered for keyword in ("翅", "翼")):
                return "wing"
            if "脖" in lowered:
                return "neck"
            if "腹" in lowered or "肚" in lowered:
                return "belly"
            if "背" in lowered:
                return "back"
            if "腿" in lowered:
                return "legs"
            if "眼" in lowered:
                return "eye"
            if "头" in lowered or "脸" in lowered:
                return "head"
            if "尾" in lowered:
                return "tail"

        keyword_groups = {
            "head": ["head", "\u5934", "\u8138", "\u8138\u90e8", "\u5934\u90e8", "\u8f6e\u5ed3"],
            "ears": ["ear", "ears", "\u8033"],
            "eyes": ["eye", "eyes", "\u773c"],
            "cheeks": ["cheek", "cheeks", "\u8138\u988a", "\u7ea2\u6655", "\u8138\u86cb"],
            "nose_mouth": ["nose", "mouth", "\u9f3b", "\u5634"],
            "whiskers": ["whisker", "whiskers", "\u80e1\u987b"],
            "body": ["body", "\u8eab\u4f53", "\u8eab\u5b50", "\u8eba\u5e72", "\u8eaf\u5e72"],
            "front_legs": ["front leg", "front legs", "\u524d\u817f", "\u524d\u811a"],
            "back_legs": ["back leg", "back legs", "\u540e\u817f", "\u540e\u811a"],
            "tail": ["tail", "\u5c3e"],
            "bow": ["bow", "bowtie", "\u8774\u8776\u7ed3", "\u9886\u7ed3"],
            "ground_line": ["ground", "ground line", "\u5730\u9762", "\u5730\u5e73\u7ebf", "\u6a2a\u7ebf"],
            "beak": ["beak", "\u5634\u5587", "\u9e2d\u5634"],
            "eye": ["eye", "eyes", "\u773c"],
            "neck": ["neck", "\u8116\u5b50"],
            "back": ["back", "\u80cc", "\u80cc\u90e8", "\u80cc\u90e8\u8f6e\u5ed3", "\u4e0a\u8f6e\u5ed3"],
            "belly": ["belly", "\u809a\u5b50", "\u8179\u90e8", "\u4e0b\u8f6e\u5ed3", "\u80f8\u8179"],
            "wing": ["wing", "\u7fc5\u8180"],
            "legs": ["legs", "\u817f"],
            "feet": ["feet", "foot", "\u811a"],
            "car_body": ["car body", "\u8f66\u8eab"],
            "roof": ["roof", "\u8f66\u9876", "\u623f\u9876"],
            "windows": ["window", "windows", "\u7a97"],
            "trunk": ["trunk", "\u6811\u5e72"],
            "main_canopy": ["canopy", "\u6811\u51a0"],
            "left_branches": ["left branch", "left branches", "\u5de6\u679d"],
            "right_branches": ["right branch", "right branches", "\u53f3\u679d"],
        }

        for canonical, keywords in keyword_groups.items():
            if any(keyword in lowered for keyword in keywords):
                return canonical

        if subject_alias == "duck" and "\u5634" in lowered:
            return "beak"
        if subject_alias in {"cat", "dog"} and "\u8138" in lowered:
            return "head"

        return lowered

    def _subject_alias(self, subject_label: str) -> str:
        lowered = (subject_label or "").strip().lower()
        if any(token in lowered for token in ("cat", "\u732b")):
            return "cat"
        if any(token in lowered for token in ("duck", "\u9e2d")):
            return "duck"
        if any(token in lowered for token in ("dog", "\u72d7")):
            return "dog"
        if any(token in lowered for token in ("car", "\u6c7d\u8f66", "\u8f66")):
            return "car"
        if any(token in lowered for token in ("house", "\u623f\u5b50")):
            return "house"
        if any(token in lowered for token in ("tree", "\u6811")):
            return "tree"
        return "generic"

    def _part_region(self, part_name: str, subject_alias: str) -> tuple[float, float, float, float] | None:
        part = self._canonical_part_name(part_name, subject_alias)
        regions: dict[str, tuple[float, float, float, float]] = {
            "head": (0.18, 0.04, 0.82, 0.35),
            "ears": (0.12, 0.00, 0.88, 0.18),
            "face": (0.22, 0.14, 0.78, 0.42),
            "eye": (0.28, 0.16, 0.72, 0.34),
            "eyes": (0.28, 0.16, 0.72, 0.34),
            "cheeks": (0.22, 0.24, 0.78, 0.44),
            "nose_mouth": (0.34, 0.22, 0.66, 0.44),
            "whiskers": (0.10, 0.22, 0.90, 0.48),
            "beak": (0.52, 0.12, 0.95, 0.34),
            "neck": (0.35, 0.22, 0.68, 0.50),
            "body": (0.15, 0.28, 0.88, 0.88),
            "wing": (0.36, 0.40, 0.78, 0.74),
            "tail": (0.68, 0.46, 0.98, 0.82),
            "front_legs": (0.24, 0.62, 0.58, 0.96),
            "back_legs": (0.42, 0.62, 0.80, 0.96),
            "legs": (0.30, 0.62, 0.72, 0.96),
            "feet": (0.24, 0.82, 0.82, 1.00),
            "bow": (0.34, 0.34, 0.66, 0.56),
            "car body": (0.14, 0.38, 0.90, 0.76),
            "roof": (0.28, 0.22, 0.76, 0.48),
            "windows": (0.34, 0.28, 0.68, 0.48),
            "front wheel": (0.18, 0.66, 0.42, 0.96),
            "rear wheel": (0.56, 0.66, 0.82, 0.96),
            "details": (0.12, 0.16, 0.88, 0.96),
            "walls": (0.20, 0.34, 0.80, 0.92),
            "door": (0.42, 0.56, 0.62, 0.96),
            "window": (0.22, 0.46, 0.46, 0.70),
            "ground line": (0.00, 0.84, 1.00, 1.00),
            "trunk": (0.38, 0.42, 0.62, 0.94),
            "main canopy": (0.14, 0.04, 0.86, 0.56),
            "left branches": (0.06, 0.16, 0.48, 0.62),
            "right branches": (0.52, 0.16, 0.94, 0.62),
            "main outline": (0.10, 0.10, 0.90, 0.90),
            "secondary outline": (0.18, 0.18, 0.82, 0.82),
            "facial or key details": (0.26, 0.18, 0.74, 0.52),
            "final details": (0.12, 0.12, 0.92, 0.92),
        }

        if subject_alias == "duck":
            if part == "head":
                return (0.48, 0.10, 0.76, 0.32)
            if part == "eye":
                return (0.58, 0.16, 0.68, 0.26)
            if part == "eyes":
                return (0.58, 0.16, 0.68, 0.26)
            if part == "neck":
                return (0.42, 0.20, 0.70, 0.52)
            if part == "back":
                return (0.16, 0.26, 0.74, 0.62)
            if part == "belly":
                return (0.20, 0.46, 0.72, 0.86)
            if part == "body":
                return (0.18, 0.32, 0.86, 0.86)
            if part == "beak":
                return (0.68, 0.16, 0.88, 0.30)
            if part == "wing":
                return (0.30, 0.42, 0.64, 0.74)
            if part == "legs":
                return (0.36, 0.72, 0.62, 0.92)
            if part == "feet":
                return (0.30, 0.84, 0.66, 1.00)
            if part == "tail":
                return (0.08, 0.42, 0.28, 0.64)

        if subject_alias in {"cat", "dog"}:
            if part == "head":
                return (0.22, 0.10, 0.78, 0.36)
            if part == "ears":
                return (0.14, 0.00, 0.86, 0.18)
            if part == "face":
                return (0.24, 0.14, 0.76, 0.40)
            if part == "eyes":
                return (0.32, 0.18, 0.70, 0.34)
            if part == "cheeks":
                return (0.20, 0.26, 0.80, 0.42)
            if part == "nose_mouth":
                return (0.36, 0.24, 0.64, 0.42)
            if part == "whiskers":
                return (0.10, 0.22, 0.90, 0.44)
            if part == "body":
                return (0.18, 0.30, 0.82, 0.84)
            if part == "front_legs":
                return (0.26, 0.58, 0.56, 0.96)
            if part == "back_legs":
                return (0.44, 0.58, 0.78, 0.96)
            if part == "tail":
                return (0.66, 0.46, 0.96, 0.86)
            if part == "bow":
                return (0.34, 0.36, 0.66, 0.56)

        return regions.get(part)

    def _part_pixel_masks(
        self,
        black_mask: np.ndarray,
        parts: list[str],
        subject_label: str,
    ) -> dict[str, np.ndarray]:
        subject_alias = self._subject_alias(subject_label)
        height, width = black_mask.shape
        xs = np.linspace(0.0, 1.0, width)
        ys = np.linspace(0.0, 1.0, height)
        x_grid = np.broadcast_to(xs, (height, width))
        y_grid = np.broadcast_to(ys[:, None], (height, width))

        region_masks: dict[str, np.ndarray] = {}
        for part in parts:
            geometry_mask = self._part_geometry_mask(part, subject_alias, x_grid, y_grid)
            if geometry_mask is not None:
                region_masks[part] = geometry_mask
                continue

            region = self._part_region(part, subject_alias)
            if region is None:
                continue
            x0, y0, x1, y1 = region
            region_masks[part] = (x_grid >= x0) & (x_grid <= x1) & (y_grid >= y0) & (y_grid <= y1)

        canonical_to_part = {
            self._canonical_part_name(part, subject_alias): part
            for part in parts
            if part in region_masks
        }

        def region_for(canonical_name: str) -> np.ndarray:
            part_key = canonical_to_part.get(canonical_name)
            if part_key is None:
                return np.zeros_like(black_mask, dtype=bool)
            return region_masks.get(part_key, np.zeros_like(black_mask, dtype=bool))

        specific_regions: dict[str, np.ndarray] = {}
        for part, region_mask in region_masks.items():
            canonical = self._canonical_part_name(part, subject_alias)
            refined = region_mask.copy()

            if canonical == "head":
                if subject_alias == "duck":
                    refined &= ~region_for("beak")
                    refined &= ~region_for("eye")
                    refined &= ~region_for("eyes")
                    refined &= ~region_for("neck")
                else:
                    refined &= ~region_for("ears")
                    refined &= ~region_for("eyes")
                    refined &= ~region_for("cheeks")
                    refined &= ~region_for("nose_mouth")
                    refined &= ~region_for("whiskers")
            elif canonical == "body":
                refined &= ~region_for("front_legs")
                refined &= ~region_for("back_legs")
                refined &= ~region_for("legs")
                refined &= ~region_for("tail")
                refined &= ~region_for("bow")
                refined &= ~region_for("wing")
                if subject_alias == "duck":
                    refined &= ~region_for("neck")
                    refined &= ~region_for("back")
                    refined &= ~region_for("belly")
            elif canonical == "legs":
                refined &= ~region_for("feet")
            elif subject_alias == "duck" and canonical == "back":
                refined &= ~region_for("wing")
                refined &= ~region_for("tail")
                refined &= ~region_for("neck")
            elif subject_alias == "duck" and canonical == "belly":
                refined &= ~region_for("legs")
                refined &= ~region_for("feet")
                refined &= ~region_for("wing")

            specific_regions[part] = refined

        part_masks = {
            part: black_mask & specific_regions.get(part, np.zeros_like(black_mask, dtype=bool))
            for part in parts
        }

        assigned = np.zeros_like(black_mask, dtype=bool)
        for mask in part_masks.values():
            assigned |= mask

        fallback_part = next(
            (part for part in parts if self._canonical_part_name(part, subject_alias) == "body"),
            parts[-1] if parts else None,
        )
        uncovered = black_mask & ~assigned
        if fallback_part is not None and np.any(uncovered):
            part_masks[fallback_part] |= uncovered

        return part_masks

    def _build_plan_driven_steps(
        self,
        black_mask: np.ndarray,
        output_dir: Path,
        step_plan: dict[str, Any],
        fps: int,
        subject_label: str,
    ) -> dict[str, Any]:
        steps = list(step_plan.get("steps") or [])
        parts = [str(part).strip() for part in step_plan.get("parts") or [] if str(part).strip()]
        if not steps or not parts:
            raise ValueError("step_plan must contain parts and steps")

        height, width = black_mask.shape
        subject_alias = self._subject_alias(subject_label)
        if subject_alias == "cat":
            return self._build_template_steps(
                output_dir=output_dir,
                step_plan=step_plan,
                fps=fps,
                subject_alias=subject_alias,
                canvas_size=max(height, width),
            )

        if subject_alias == "duck":
            part_masks = self._duck_part_pixel_masks(black_mask, parts)
        else:
            part_masks = self._part_pixel_masks(black_mask, parts, subject_label)
        if subject_alias == "duck" and not self._duck_core_parts_present(part_masks, parts, subject_label):
            return self._build_template_steps(
                output_dir=output_dir,
                step_plan=step_plan,
                fps=fps,
                subject_alias=subject_alias,
                canvas_size=max(height, width),
            )

        return self._render_steps_from_masks(
            black_mask=black_mask,
            output_dir=output_dir,
            step_plan=step_plan,
            fps=fps,
            parts=parts,
            part_masks=part_masks,
        )

    def _build_fallback_steps(
        self,
        black_mask: np.ndarray,
        output_dir: Path,
        step_count: int,
        fps: int,
    ) -> dict[str, Any]:
        coords = np.column_stack(np.where(black_mask))
        if coords.size == 0:
            raise RuntimeError("No drawable black pixels found in lineart image")

        order = np.lexsort((coords[:, 1], coords[:, 0]))
        coords = coords[order]

        height, width = black_mask.shape
        total = len(coords)
        timestamps: list[float] = []
        prompts: list[str] = []

        for i in range(step_count):
            ratio = (i + 1) / step_count
            keep = max(1, int(total * ratio))

            canvas = np.full((height, width), 255, dtype=np.uint8)
            selected = coords[:keep]
            canvas[selected[:, 0], selected[:, 1]] = 0

            rgb = cv2.cvtColor(canvas, cv2.COLOR_GRAY2BGR)
            frame_path = output_dir / f"frame_{i:03d}.png"
            cv2.imwrite(str(frame_path), rgb)

            timestamps.append(round(i / fps, 4))
            prompts.append(f"Step {i + 1}: continue the drawing")

        return {
            "stepCount": step_count,
            "timestamps": timestamps,
            "prompts": prompts,
        }

    def build_steps(
        self,
        lineart_path: Path,
        output_dir: Path,
        step_count: int | None = None,
        fps: int | None = None,
        step_plan: dict[str, Any] | None = None,
        subject_label: str = "",
    ) -> dict[str, Any]:
        step_count = step_count or settings.step_count
        fps = fps or settings.fps
        output_dir.mkdir(parents=True, exist_ok=True)

        gray = cv2.imread(str(lineart_path), cv2.IMREAD_GRAYSCALE)
        if gray is None:
            raise RuntimeError(f"Failed to read lineart image: {lineart_path}")

        _, binary = cv2.threshold(gray, settings.line_threshold, 255, cv2.THRESH_BINARY)
        black_mask = binary < 250

        if not np.any(black_mask):
            raise RuntimeError("No drawable black pixels found in lineart image")

        if step_plan:
            return self._build_plan_driven_steps(
                black_mask=black_mask,
                output_dir=output_dir,
                step_plan=step_plan,
                fps=fps,
                subject_label=subject_label,
            )

        return self._build_fallback_steps(
            black_mask=black_mask,
            output_dir=output_dir,
            step_count=step_count,
            fps=fps,
        )
