# FILE: backend/app/utils/ffmpeg_util.py
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import cv2


def compose_mp4_from_frames(
    frames_pattern: str,
    output_path: Path,
    fps: int,
    workdir: Path,
) -> None:
    """
    优先使用 ffmpeg。
    若环境中没有 ffmpeg，则回退到 OpenCV VideoWriter，保证 MVP 能跑通。
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)

    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg:
        cmd = [
            ffmpeg,
            "-y",
            "-framerate",
            str(fps),
            "-i",
            frames_pattern,
            "-pix_fmt",
            "yuv420p",
            "-movflags",
            "+faststart",
            str(output_path),
        ]
        subprocess.run(cmd, cwd=str(workdir), check=True)
        return

    first_frame = workdir / "output" / "frames" / "frame_000.png"
    if not first_frame.exists():
        raise FileNotFoundError("frame_000.png not found for OpenCV fallback")

    sample = cv2.imread(str(first_frame))
    if sample is None:
        raise RuntimeError("OpenCV fallback failed to read first frame")

    height, width = sample.shape[:2]
    writer = cv2.VideoWriter(
        str(output_path),
        cv2.VideoWriter_fourcc(*"mp4v"),
        float(fps),
        (width, height),
    )
    if not writer.isOpened():
        raise RuntimeError("OpenCV VideoWriter failed to open output mp4")

    frame_index = 0
    while True:
        frame_path = workdir / "output" / "frames" / f"frame_{frame_index:03d}.png"
        if not frame_path.exists():
            break
        frame = cv2.imread(str(frame_path))
        if frame is None:
            raise RuntimeError(f"OpenCV failed to read frame: {frame_path}")
        writer.write(frame)
        frame_index += 1

    writer.release()
