# FILE: backend/app/services/video_composer.py
from __future__ import annotations

import time
from pathlib import Path

import cv2
import numpy as np

from app.utils.ffmpeg_util import compose_mp4_from_frames


class VideoComposer:
    def _read_frame(self, path: Path) -> np.ndarray:
        frame = cv2.imread(str(path), cv2.IMREAD_COLOR)
        if frame is None:
            raise RuntimeError(f"Failed to read frame: {path}")
        return frame

    def _ink_mask(self, frame: np.ndarray) -> np.ndarray:
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        return gray < 245

    def _ordered_pixels(self, mask: np.ndarray) -> np.ndarray:
        labels_count, labels = cv2.connectedComponents(mask.astype(np.uint8), connectivity=8)
        ordered_components: list[tuple[float, np.ndarray]] = []

        for label in range(1, labels_count):
            coords = np.column_stack(np.where(labels == label))
            if coords.size == 0:
                continue

            ys = coords[:, 0].astype(np.float32)
            xs = coords[:, 1].astype(np.float32)
            if len(coords) >= 3:
                centered = np.column_stack((xs - xs.mean(), ys - ys.mean()))
                _, _, vh = np.linalg.svd(centered, full_matrices=False)
                axis = vh[0]
                projection = centered @ axis
                order = np.argsort(projection)
            else:
                order = np.lexsort((xs, ys))

            sorted_coords = coords[order]
            component_key = float(sorted_coords[0, 0] + sorted_coords[0, 1] * 0.35)
            ordered_components.append((component_key, sorted_coords))

        if not ordered_components:
            return np.empty((0, 2), dtype=np.int64)

        ordered_components.sort(key=lambda item: item[0])
        return np.vstack([coords for _, coords in ordered_components])

    def _transition_frames(
        self,
        previous: np.ndarray,
        target: np.ndarray,
        frame_count: int,
    ) -> list[np.ndarray]:
        previous_ink = self._ink_mask(previous)
        target_ink = self._ink_mask(target)
        diff = cv2.absdiff(previous, target)
        changed = np.any(diff > 12, axis=2)
        new_ink = target_ink & (~previous_ink | changed)
        coords = self._ordered_pixels(new_ink)

        if len(coords) == 0:
            return [target.copy() for _ in range(frame_count)]

        rendered: list[np.ndarray] = []
        total = len(coords)
        for index in range(frame_count):
            take = max(1, int(round(total * ((index + 1) / frame_count))))
            reveal = coords[:take]
            frame = previous.copy()
            frame[reveal[:, 0], reveal[:, 1]] = target[reveal[:, 0], reveal[:, 1]]
            if index == frame_count - 1:
                frame = target.copy()
            rendered.append(frame)

        return rendered

    def _write_frame(self, output_dir: Path, index: int, frame: np.ndarray) -> None:
        cv2.imwrite(str(output_dir / f"frame_{index:04d}.png"), frame)

    def compose(
        self,
        task_dir: Path,
        fps: int,
        output_path: Path,
    ) -> list[float]:
        source_frames = sorted((task_dir / "output" / "frames").glob("frame_*.png"))
        if not source_frames:
            raise FileNotFoundError("No source step frames found for video composition")

        render_dir_name = f"render_frames_{int(time.time() * 1000)}"
        render_dir = task_dir / "output" / render_dir_name
        render_dir.mkdir(parents=True, exist_ok=True)

        first = self._read_frame(source_frames[0])
        previous = np.full_like(first, 255)
        transition_frame_count = max(4, fps // 2)
        hold_frame_count = max(1, fps // 6)
        output_index = 0
        timestamps: list[float] = []

        for source_frame in source_frames:
            target = self._read_frame(source_frame)
            if target.shape != previous.shape:
                target = cv2.resize(target, (previous.shape[1], previous.shape[0]), interpolation=cv2.INTER_AREA)

            timestamps.append(round(output_index / fps, 4))
            for frame in self._transition_frames(previous, target, transition_frame_count):
                self._write_frame(render_dir, output_index, frame)
                output_index += 1

            for _ in range(hold_frame_count):
                self._write_frame(render_dir, output_index, target)
                output_index += 1

            previous = target

        frames_pattern = f"output/{render_dir_name}/frame_%04d.png"
        compose_mp4_from_frames(
            frames_pattern=frames_pattern,
            output_path=output_path,
            fps=fps,
            workdir=task_dir,
        )
        return timestamps
