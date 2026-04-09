# FILE: backend/app/services/video_composer.py
from __future__ import annotations

from pathlib import Path

from app.utils.ffmpeg_util import compose_mp4_from_frames


class VideoComposer:
    def compose(
        self,
        task_dir: Path,
        fps: int,
        output_path: Path,
    ) -> None:
        frames_pattern = "output/frames/frame_%03d.png"
        compose_mp4_from_frames(
            frames_pattern=frames_pattern,
            output_path=output_path,
            fps=fps,
            workdir=task_dir,
        )
