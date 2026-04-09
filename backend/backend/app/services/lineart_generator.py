from __future__ import annotations

import base64
import json
import os
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

import requests
from PIL import Image, ImageDraw

from app.config import settings
from app.schemas import RecognizedSubject
from app.services.ai_step_generator import generate_steps_ai
from app.services.step_builder import StepBuilder
from app.utils.image_io import normalize_generated_lineart


class LineartGenerator(ABC):
    @abstractmethod
    def generate(
        self,
        subject: RecognizedSubject,
        user_prompt: str,
        output_path: Path,
        debug_dir: Path,
        size: int = 768,
        reference_image_path: Path | None = None,
    ) -> dict[str, Any]:
        raise NotImplementedError


class MockLineartGenerator(LineartGenerator):
    def _prompt_text(self, subject: RecognizedSubject, user_prompt: str) -> str:
        base = (
            f"Generate a kid-friendly line drawing tutorial for {subject.label}. "
            "Black lines on white background, single subject, no text, no background."
        )
        if user_prompt:
            base += f" Extra user prompt: {user_prompt}"
        return base

    def _draw_cat(self, draw: ImageDraw.ImageDraw, s: int) -> None:
        draw.ellipse((s * 0.25, s * 0.25, s * 0.75, s * 0.75), outline="black", width=6)
        draw.polygon(
            [(s * 0.33, s * 0.27), (s * 0.42, s * 0.12), (s * 0.47, s * 0.32)],
            outline="black",
            width=6,
        )
        draw.polygon(
            [(s * 0.53, s * 0.32), (s * 0.58, s * 0.12), (s * 0.67, s * 0.27)],
            outline="black",
            width=6,
        )
        draw.ellipse((s * 0.40, s * 0.42, s * 0.46, s * 0.48), outline="black", width=4)
        draw.ellipse((s * 0.54, s * 0.42, s * 0.60, s * 0.48), outline="black", width=4)
        draw.polygon(
            [(s * 0.48, s * 0.53), (s * 0.52, s * 0.53), (s * 0.50, s * 0.57)],
            outline="black",
            width=4,
        )
        draw.line((s * 0.36, s * 0.56, s * 0.47, s * 0.55), fill="black", width=3)
        draw.line((s * 0.53, s * 0.55, s * 0.64, s * 0.56), fill="black", width=3)
        draw.arc((s * 0.42, s * 0.56, s * 0.50, s * 0.65), 200, 340, fill="black", width=3)
        draw.arc((s * 0.50, s * 0.56, s * 0.58, s * 0.65), 200, 340, fill="black", width=3)

    def _draw_cup(self, draw: ImageDraw.ImageDraw, s: int) -> None:
        draw.rectangle((s * 0.28, s * 0.30, s * 0.62, s * 0.72), outline="black", width=6)
        draw.arc((s * 0.55, s * 0.38, s * 0.78, s * 0.62), 270, 90, fill="black", width=6)
        draw.line((s * 0.22, s * 0.72, s * 0.70, s * 0.72), fill="black", width=6)

    def _draw_car(self, draw: ImageDraw.ImageDraw, s: int) -> None:
        draw.rectangle((s * 0.22, s * 0.46, s * 0.76, s * 0.64), outline="black", width=6)
        draw.polygon(
            [(s * 0.32, s * 0.46), (s * 0.44, s * 0.34), (s * 0.62, s * 0.34), (s * 0.70, s * 0.46)],
            outline="black",
            width=6,
        )
        draw.ellipse((s * 0.28, s * 0.60, s * 0.40, s * 0.72), outline="black", width=6)
        draw.ellipse((s * 0.58, s * 0.60, s * 0.70, s * 0.72), outline="black", width=6)

    def _draw_apple(self, draw: ImageDraw.ImageDraw, s: int) -> None:
        draw.ellipse((s * 0.28, s * 0.28, s * 0.72, s * 0.76), outline="black", width=6)
        draw.line((s * 0.50, s * 0.25, s * 0.53, s * 0.14), fill="black", width=6)
        draw.ellipse((s * 0.52, s * 0.10, s * 0.65, s * 0.20), outline="black", width=5)

    def _draw_house(self, draw: ImageDraw.ImageDraw, s: int) -> None:
        draw.rectangle((s * 0.28, s * 0.40, s * 0.72, s * 0.76), outline="black", width=6)
        draw.polygon(
            [(s * 0.24, s * 0.40), (s * 0.50, s * 0.18), (s * 0.76, s * 0.40)],
            outline="black",
            width=6,
        )
        draw.rectangle((s * 0.44, s * 0.56, s * 0.56, s * 0.76), outline="black", width=5)
        draw.rectangle((s * 0.32, s * 0.50, s * 0.40, s * 0.58), outline="black", width=4)

    def _draw_tree(self, draw: ImageDraw.ImageDraw, s: int) -> None:
        draw.rectangle((s * 0.44, s * 0.54, s * 0.56, s * 0.78), outline="black", width=6)
        draw.ellipse((s * 0.26, s * 0.18, s * 0.74, s * 0.58), outline="black", width=6)
        draw.ellipse((s * 0.18, s * 0.28, s * 0.52, s * 0.56), outline="black", width=5)
        draw.ellipse((s * 0.48, s * 0.28, s * 0.82, s * 0.56), outline="black", width=5)

    def _draw_generic(self, draw: ImageDraw.ImageDraw, s: int) -> None:
        draw.ellipse((s * 0.24, s * 0.24, s * 0.76, s * 0.76), outline="black", width=6)
        draw.line((s * 0.38, s * 0.58, s * 0.62, s * 0.58), fill="black", width=5)
        draw.ellipse((s * 0.38, s * 0.42, s * 0.46, s * 0.50), outline="black", width=4)
        draw.ellipse((s * 0.54, s * 0.42, s * 0.62, s * 0.50), outline="black", width=4)

    def _draw_by_label(self, draw: ImageDraw.ImageDraw, label: str, size: int) -> None:
        normalized = label.lower()
        if any(token in normalized for token in ("cat", "\u732b")):
            self._draw_cat(draw, size)
        elif any(token in normalized for token in ("cup", "\u676f")):
            self._draw_cup(draw, size)
        elif any(token in normalized for token in ("car", "\u8f66", "\u6c7d\u8f66")):
            self._draw_car(draw, size)
        elif any(token in normalized for token in ("apple", "\u82f9\u679c")):
            self._draw_apple(draw, size)
        elif any(token in normalized for token in ("house", "\u623f", "\u5c4b")):
            self._draw_house(draw, size)
        elif any(token in normalized for token in ("tree", "\u6811")):
            self._draw_tree(draw, size)
        else:
            self._draw_generic(draw, size)

    def generate(
        self,
        subject: RecognizedSubject,
        user_prompt: str,
        output_path: Path,
        debug_dir: Path,
        size: int = 768,
        reference_image_path: Path | None = None,
    ) -> dict[str, Any]:
        prompt_text = self._prompt_text(subject, user_prompt)
        params = {
            "backend": "mock",
            "size": size,
            "style": "black line on white background",
            "subject": subject.label,
            "reference_image_path": str(reference_image_path) if reference_image_path else None,
        }

        debug_dir.mkdir(parents=True, exist_ok=True)
        (debug_dir / "seedream_prompt.txt").write_text(prompt_text, encoding="utf-8")
        (debug_dir / "seedream_params.json").write_text(
            json.dumps(params, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        image = Image.new("RGB", (size, size), "white")
        draw = ImageDraw.Draw(image)
        self._draw_by_label(draw, subject.label, size)

        output_path.parent.mkdir(parents=True, exist_ok=True)
        image.save(output_path)

        step_plan = generate_steps_ai(
            subject=subject.label,
            prompt=user_prompt,
            reference_image_path=reference_image_path,
            step_count=settings.step_count,
        )
        steps = StepBuilder().build_steps(
            lineart_path=output_path,
            output_dir=output_path.parent / "frames",
            step_count=settings.step_count,
            fps=settings.fps,
            step_plan=step_plan,
            subject_label=subject.label,
        )
        steps["frames"] = [f"frame_{i:03d}.png" for i in range(steps["stepCount"])]
        steps["count"] = steps["stepCount"]

        (debug_dir / "step_plan.json").write_text(
            json.dumps(step_plan, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        return {
            "backend": "mock",
            "prompt": prompt_text,
            "step_plan": step_plan,
            "steps": steps,
        }


class RealSeedreamGenerator(LineartGenerator):
    def __init__(self) -> None:
        self.api_key = (
            os.getenv("SEEDREAM5_API_KEY")
            or os.getenv("VOLCENGINE_API_KEY")
            or os.getenv("ARK_API_KEY")
            or os.getenv("LAS_API_KEY")
        )
        configured_url = os.getenv(
            "SEEDREAM5_IMAGE_URL",
            "https://operator.las.cn-beijing.volces.com/api/v1/images/generations",
        )
        self.url = configured_url.replace("/api/v1/online/images/generations", "/api/v1/images/generations")
        self.model = os.getenv("SEEDREAM5_MODEL", "doubao-seedream-5-0-lite-260128")
        self.request_size = os.getenv("SEEDREAM5_REQUEST_SIZE", "2048x2048")
        self.response_format = os.getenv("SEEDREAM5_RESPONSE_FORMAT", "url").strip().lower() or "url"
        self.output_format = os.getenv("SEEDREAM5_OUTPUT_FORMAT", "png").strip().lower() or "png"
        self.watermark = os.getenv("SEEDREAM5_WATERMARK", "false").strip().lower() in {"1", "true", "yes", "on"}
        self.sequential_image_generation = (
            os.getenv("SEEDREAM5_SEQUENTIAL_IMAGE_GENERATION", "disabled").strip().lower() or "disabled"
        )
        self.siliconflow_api_key = os.getenv("SILICONFLOW_API_KEY")
        self.siliconflow_url = os.getenv(
            "SILICONFLOW_IMAGE_URL",
            "https://api.siliconflow.cn/v1/images/generations",
        )
        self.siliconflow_model = os.getenv("SILICONFLOW_IMAGE_MODEL", "Kwai-Kolors/Kolors")

    def _build_final_lineart_prompt(
        self,
        subject: RecognizedSubject,
        user_prompt: str,
        step_plan: dict[str, Any],
    ) -> str:
        overall_shape = step_plan.get("overall_shape") or f"Simple drawing of {subject.label}"
        parts = ", ".join(step_plan.get("parts") or [])
        extra = f" Extra user prompt: {user_prompt}." if user_prompt else ""
        subject_name = subject.label.lower()
        subject_style = ""
        if any(token in subject_name for token in ("duck", "鸭")):
            subject_style = (
                " Keep the duck clearly recognizable and close to the reference silhouette and proportions, "
                "not a mascot, not chibi, and not a big-eyed cartoon baby. "
                "Make it a simple children's worksheet duck in side view with a medium oval body larger than the head, "
                "a flat broad beak, a small round eye, a smooth neck, one clean wing, a short tail, and two visible webbed feet. "
                "Use clean outer contours and only a few interior helper lines that are easy for a child to copy. "
                "Do not add a decorative border, plants, grass, water, puddles, reeds, hearts, scenery, feathers texture, or realistic shading."
            )
        return (
            f"Create one final children's drawing worksheet line art of {subject.label}. "
            f"Reference pose and composition: {overall_shape}. "
            f"Important body parts to preserve: {parts}. "
            "Return a complete but simple final outline that can be split into step-by-step drawing frames later. "
            "Stay close to the reference pose and main silhouette instead of inventing a different character design. "
            "Black outline only, white background, centered subject, no color, no fill, no shading, no texture, "
            "no realistic rendering, no extra props, no background, no text, no decorative frame."
            f"{subject_style}{extra}"
        )

    def _load_reference_image(self, reference_image_path: Path | None) -> str | None:
        if reference_image_path is None or not reference_image_path.exists():
            return None
        encoded = base64.b64encode(reference_image_path.read_bytes()).decode("utf-8")
        suffix = reference_image_path.suffix.lower()
        mime = {
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".png": "image/png",
            ".webp": "image/webp",
        }.get(suffix, "image/png")
        return f"data:{mime};base64,{encoded}"

    def _normalize_response_payload(self, result: dict[str, Any]) -> dict[str, Any]:
        if isinstance(result.get("data"), dict):
            return result["data"]
        return result

    def _download_image_bytes(self, result: dict[str, Any]) -> bytes:
        payload = self._normalize_response_payload(result)
        images = payload.get("data") or []
        if not images:
            raise RuntimeError(f"Unexpected Seedream 5.0 response: {result}")

        first = images[0]
        error_info = first.get("error")
        if error_info:
            raise RuntimeError(f"Seedream 5.0 image generation failed: {error_info}")

        if "b64_json" in first:
            return base64.b64decode(first["b64_json"])
        if "url" in first:
            image_resp = requests.get(first["url"], timeout=60)
            image_resp.raise_for_status()
            return image_resp.content
        raise RuntimeError(f"Unexpected Seedream 5.0 image payload: {result}")

    def _download_siliconflow_image_bytes(self, result: dict[str, Any]) -> bytes:
        images = result.get("images") or result.get("data") or []
        if not images:
            raise RuntimeError(f"Unexpected SiliconFlow response: {result}")

        first = images[0]
        if "b64_json" in first:
            return base64.b64decode(first["b64_json"])
        if "url" in first:
            image_resp = requests.get(first["url"], timeout=60)
            image_resp.raise_for_status()
            return image_resp.content
        raise RuntimeError(f"Unexpected SiliconFlow image payload: {result}")

    def _generate_with_seedream5(
        self,
        final_prompt: str,
        reference_image_b64: str | None,
    ) -> bytes:
        payload: dict[str, Any] = {
            "model": self.model,
            "prompt": final_prompt,
            "size": self.request_size,
            "response_format": self.response_format,
            "output_format": self.output_format,
            "watermark": self.watermark,
            "sequential_image_generation": self.sequential_image_generation,
        }
        if reference_image_b64:
            payload["image"] = reference_image_b64

        response = requests.post(
            self.url,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=60,
        )
        response.raise_for_status()
        return self._download_image_bytes(response.json())

    def _generate_with_siliconflow(
        self,
        final_prompt: str,
        size: int,
    ) -> bytes:
        if not self.siliconflow_api_key:
            raise RuntimeError("Missing SILICONFLOW_API_KEY for fallback image generation.")

        response = requests.post(
            self.siliconflow_url,
            headers={
                "Authorization": f"Bearer {self.siliconflow_api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": self.siliconflow_model,
                "prompt": final_prompt,
                "image_size": f"{size}x{size}",
                "batch_size": 1,
                "num_inference_steps": 20,
                "guidance_scale": 7.5,
            },
            timeout=60,
        )
        response.raise_for_status()
        return self._download_siliconflow_image_bytes(response.json())

    def generate(
        self,
        subject: RecognizedSubject,
        user_prompt: str,
        output_path: Path,
        debug_dir: Path,
        size: int = 768,
        reference_image_path: Path | None = None,
    ) -> dict[str, Any]:
        if not self.api_key:
            raise RuntimeError(
                "Missing Seedream 5.0 API key. Set SEEDREAM5_API_KEY (or VOLCENGINE_API_KEY/ARK_API_KEY/LAS_API_KEY) "
                "in backend/.env, "
                "or change LINEART_BACKEND=mock if you only want to test locally."
            )

        debug_dir.mkdir(parents=True, exist_ok=True)

        step_plan = generate_steps_ai(
            subject=subject.label,
            prompt=user_prompt,
            reference_image_path=reference_image_path,
            step_count=settings.step_count,
        )
        final_prompt = self._build_final_lineart_prompt(subject, user_prompt, step_plan)
        reference_image_b64 = self._load_reference_image(reference_image_path)
        backend_used = "seedream5"
        try:
            image_bytes = self._generate_with_seedream5(final_prompt, reference_image_b64)
        except requests.RequestException as exc:
            if not self.siliconflow_api_key:
                raise
            backend_used = "siliconflow_fallback"
            (debug_dir / "seedream5_fallback_reason.txt").write_text(str(exc), encoding="utf-8")
            image_bytes = self._generate_with_siliconflow(final_prompt, size=size)

        raw_output_path = debug_dir / "lineart_raw.png"
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with raw_output_path.open("wb") as handle:
            handle.write(image_bytes)
        normalize_generated_lineart(raw_output_path, output_path, size=size)

        steps = StepBuilder().build_steps(
            lineart_path=output_path,
            output_dir=output_path.parent / "frames",
            step_count=settings.step_count,
            fps=settings.fps,
            step_plan=step_plan,
            subject_label=subject.label,
        )
        steps["frames"] = [f"frame_{i:03d}.png" for i in range(steps["stepCount"])]
        steps["count"] = steps["stepCount"]

        (debug_dir / "step_plan.json").write_text(
            json.dumps(step_plan, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        (debug_dir / "seedream_prompt.txt").write_text(final_prompt, encoding="utf-8")
        (debug_dir / "seedream_params.json").write_text(
            json.dumps(
                {
                    "backend_used": backend_used,
                    "model": self.model if backend_used == "seedream5" else self.siliconflow_model,
                    "request_size": self.request_size,
                    "response_format": self.response_format,
                    "output_format": self.output_format,
                    "watermark": self.watermark,
                    "sequential_image_generation": self.sequential_image_generation,
                    "seedream5_url": self.url,
                    "siliconflow_url": self.siliconflow_url,
                    "subject": subject.label,
                    "reference_image_path": str(reference_image_path) if reference_image_path else None,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

        return {
            "backend": backend_used,
            "prompt": final_prompt,
            "step_plan": step_plan,
            "steps": steps,
        }


def build_lineart_generator(backend_name: str) -> LineartGenerator:
    if backend_name == "mock":
        return MockLineartGenerator()
    if backend_name in {"seedream", "seedream5"}:
        return RealSeedreamGenerator()
    raise ValueError(f"Unknown lineart generator backend: {backend_name}")
