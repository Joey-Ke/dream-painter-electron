# FILE: backend/app/services/video_enhancer.py
from __future__ import annotations

import base64
import json
import os
import shutil
import time
from abc import ABC, abstractmethod
from io import BytesIO
from pathlib import Path

import requests
from PIL import Image


class VideoEnhancer(ABC):
    @abstractmethod
    def enhance(
        self,
        input_video: Path,
        output_video: Path,
        *,
        subject_label: str = "",
        user_prompt: str = "",
        reference_image: Path | None = None,
        step_prompts: list[str] | None = None,
        debug_dir: Path | None = None,
    ) -> Path:
        raise NotImplementedError


class NoopVideoEnhancer(VideoEnhancer):
    def enhance(
        self,
        input_video: Path,
        output_video: Path,
        *,
        subject_label: str = "",
        user_prompt: str = "",
        reference_image: Path | None = None,
        step_prompts: list[str] | None = None,
        debug_dir: Path | None = None,
    ) -> Path:
        output_video.parent.mkdir(parents=True, exist_ok=True)
        if input_video.resolve() != output_video.resolve():
            shutil.copy2(input_video, output_video)
        return output_video


class SeedanceVideoEnhancer(VideoEnhancer):
    def __init__(self) -> None:
        self.api_key = None
        for key in ("SEEDANCE_API_KEY", "ARK_API_KEY", "LAS_API_KEY"):
            value = os.getenv(key)
            if value:
                self.api_key = value
                break

        self.base_url = (
            os.getenv("SEEDANCE_BASE_URL")
            or os.getenv("LAS_BASE_URL")
            or "https://operator.las.cn-beijing.volces.com/api/v1"
        ).rstrip("/")
        self.model = os.getenv("SEEDANCE_MODEL", "doubao-seedance-1-5-pro-251215")
        self.duration = int(os.getenv("SEEDANCE_DURATION", "5"))
        self.ratio = os.getenv("SEEDANCE_RATIO", "1:1")
        self.watermark = os.getenv("SEEDANCE_WATERMARK", "false").strip().lower() in {
            "1",
            "true",
            "yes",
            "on",
        }
        self.return_last_frame = os.getenv("SEEDANCE_RETURN_LAST_FRAME", "true").strip().lower() in {
            "1",
            "true",
            "yes",
            "on",
        }
        self.poll_seconds = max(1, int(os.getenv("SEEDANCE_POLL_SECONDS", "3")))
        self.timeout_seconds = max(30, int(os.getenv("SEEDANCE_TIMEOUT_SECONDS", "600")))
        self.strict = os.getenv("SEEDANCE_STRICT", "false").strip().lower() in {
            "1",
            "true",
            "yes",
            "on",
        }

    def _create_image_data_url(self, image_path: Path) -> str:
        image = Image.open(image_path).convert("RGB")
        buffer = BytesIO()
        image.save(buffer, format="PNG")
        encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
        return f"data:image/png;base64,{encoded}"

    def _build_prompt(
        self,
        subject_label: str,
        user_prompt: str,
        step_prompts: list[str] | None,
    ) -> str:
        subject = subject_label or "object"
        step_hint = ""
        if step_prompts:
            condensed = " | ".join(step_prompts[:4])
            step_hint = f" Tutorial stages: {condensed}."

        extra = f" Extra user prompt: {user_prompt}." if user_prompt else ""
        return (
            f"Create a clean educational drawing animation for {subject}. "
            "Use the provided first frame as the starting image and animate it into a simple worksheet-style result. "
            "Keep a fixed camera, white background, black line art, no scenery, no text, no color, and no heavy texture. "
            "The motion should feel like a calm step-by-step drawing demonstration, not a cinematic shot."
            f"{step_hint}{extra}"
        )

    def _create_task(
        self,
        prompt: str,
        image_url: str | None,
    ) -> str:
        if not self.api_key:
            raise RuntimeError("Missing Seedance API key. Set ARK_API_KEY or SEEDANCE_API_KEY in backend/.env.")

        content: list[dict[str, object]] = [{"type": "text", "text": prompt}]
        if image_url:
            content.append({"type": "image_url", "image_url": {"url": image_url}})

        response = requests.post(
            f"{self.base_url}/contents/generations/tasks",
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": self.model,
                "content": content,
                "duration": self.duration,
                "ratio": self.ratio,
                "watermark": self.watermark,
                "return_last_frame": self.return_last_frame,
            },
            timeout=60,
        )
        response.raise_for_status()
        payload = response.json()
        task_id = payload.get("id")
        if not task_id:
            raise RuntimeError(f"Seedance create task response missing id: {payload}")
        return str(task_id)

    def _poll_task(self, task_id: str) -> dict:
        started = time.time()
        while time.time() - started < self.timeout_seconds:
            response = requests.get(
                f"{self.base_url}/contents/generations/tasks/{task_id}",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                timeout=60,
            )
            response.raise_for_status()
            payload = response.json()
            status = str(payload.get("status", "")).lower()
            if status == "succeeded":
                return payload
            if status in {"failed", "expired", "cancelled"}:
                raise RuntimeError(f"Seedance task failed: {payload.get('error') or payload}")
            time.sleep(self.poll_seconds)
        raise TimeoutError(f"Seedance task timed out after {self.timeout_seconds} seconds")

    def _download_video(self, url: str, output_video: Path) -> None:
        response = requests.get(url, timeout=120)
        response.raise_for_status()
        output_video.parent.mkdir(parents=True, exist_ok=True)
        with output_video.open("wb") as handle:
            handle.write(response.content)

    def enhance(
        self,
        input_video: Path,
        output_video: Path,
        *,
        subject_label: str = "",
        user_prompt: str = "",
        reference_image: Path | None = None,
        step_prompts: list[str] | None = None,
        debug_dir: Path | None = None,
    ) -> Path:
        prompt = self._build_prompt(subject_label, user_prompt, step_prompts)
        image_url = self._create_image_data_url(reference_image) if reference_image and reference_image.exists() else None

        try:
            task_id = self._create_task(prompt, image_url=image_url)
            result = self._poll_task(task_id)
            content = result.get("content") or {}
            video_url = content.get("video_url")
            if not video_url:
                raise RuntimeError(f"Seedance succeeded but video_url missing: {result}")
            self._download_video(str(video_url), output_video)

            if debug_dir is not None:
                debug_dir.mkdir(parents=True, exist_ok=True)
                (debug_dir / "seedance_task.json").write_text(
                    json.dumps(result, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
                last_frame_url = content.get("last_frame_url")
                if last_frame_url:
                    (debug_dir / "seedance_last_frame_url.txt").write_text(str(last_frame_url), encoding="utf-8")
            return output_video
        except Exception as exc:  # noqa: BLE001
            if debug_dir is not None:
                debug_dir.mkdir(parents=True, exist_ok=True)
                (debug_dir / "seedance_error.txt").write_text(str(exc), encoding="utf-8")
            if self.strict:
                raise
            output_video.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(input_video, output_video)
            return output_video


def build_video_enhancer(enabled: bool) -> VideoEnhancer:
    if enabled:
        return SeedanceVideoEnhancer()
    return NoopVideoEnhancer()
