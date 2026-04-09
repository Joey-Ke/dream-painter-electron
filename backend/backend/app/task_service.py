# FILE: backend/app/task_service.py
from __future__ import annotations

import shutil
import threading
import time
import traceback
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from app.config import settings
from app.schemas import RecognizedSubject
from app.services.lineart_generator import build_lineart_generator
from app.services.recognizer import build_recognizer
from app.services.step_builder import StepBuilder
from app.services.storage import StorageService
from app.services.video_composer import VideoComposer
from app.services.video_enhancer import build_video_enhancer
from app.utils.image_io import resize_for_recognition, save_upload_image
from app.utils.logger import create_task_logger


class TaskService:
    def __init__(self) -> None:
        self.storage = StorageService(settings.tasks_dir)
        self.recognizer = build_recognizer(settings.recognizer_backend)
        self.lineart_generator = build_lineart_generator(settings.lineart_backend)
        self.step_builder = StepBuilder()
        self.video_composer = VideoComposer()
        self.video_enhancer = build_video_enhancer(settings.seedance_enabled)
        self.pool = ThreadPoolExecutor(max_workers=2)
        self.lock = threading.Lock()
        self.tasks: dict[str, dict[str, Any]] = {}

    def _now_meta(
        self,
        task_id: str,
        status: str,
        progress: float,
        stage: str,
        error: str | None = None,
        recognized_subject: dict[str, Any] | None = None,
        steps: dict[str, Any] | None = None,
        video_asset: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return {
            "taskId": task_id,
            "status": status,
            "progress": progress,
            "stage": stage,
            "error": error,
            "recognized_subject": recognized_subject,
            "steps": steps,
            "video_asset": video_asset,
            "updatedAt": time.time(),
        }

    def _save_meta(self, task_id: str, meta: dict[str, Any]) -> None:
        with self.lock:
            self.tasks[task_id] = meta
        self.storage.write_json(self.storage.meta_path(task_id), meta)

    def _update_meta(self, task_id: str, **kwargs: Any) -> dict[str, Any]:
        current = self.get_task(task_id)
        current.update(kwargs)
        self._save_meta(task_id, current)
        return current

    def create_task(self, image_file, prompt: str) -> str:
        task_id, task_dir = self.storage.create_task_dir()
        logger = create_task_logger(task_dir)

        input_raw = task_dir / "input" / "input_raw.png"
        save_upload_image(image_file.file, input_raw)

        self.storage.write_text(task_dir / "input" / "prompt.txt", prompt or "")

        meta = self._now_meta(
            task_id=task_id,
            status="queued",
            progress=0.0,
            stage="queued",
        )
        self._save_meta(task_id, meta)

        logger.info("Task created")
        logger.info("Saved input_raw=%s", input_raw)

        self.pool.submit(self._run_task, task_id, prompt)
        return task_id

    def get_task(self, task_id: str) -> dict[str, Any]:
        with self.lock:
            if task_id in self.tasks:
                return dict(self.tasks[task_id])

        meta_path = self.storage.meta_path(task_id)
        if meta_path.exists():
            meta = self.storage.read_json(meta_path)
            with self.lock:
                self.tasks[task_id] = meta
            return dict(meta)

        raise KeyError(task_id)

    def _run_task(self, task_id: str, prompt: str) -> None:
        task_dir = self.storage.task_dir(task_id)
        logger = create_task_logger(task_dir)
        input_raw = task_dir / "input" / "input_raw.png"
        input_to_qwen = task_dir / "input" / "input_to_qwen.png"
        debug_dir = task_dir / "debug"
        output_dir = task_dir / "output"
        lineart_path = output_dir / "lineart.png"
        steps_path = output_dir / "steps.json"
        local_video_path = output_dir / "tutorial_local.mp4"
        video_path = output_dir / "tutorial.mp4"
        error_log = task_dir / "error.log"

        try:
            started_at = time.time()

            self._update_meta(task_id, status="running", progress=0.05, stage="save_input")
            logger.info("Stage save_input started")

            new_size = resize_for_recognition(input_raw, input_to_qwen, settings.max_qwen_side)
            logger.info("Prepared input_to_qwen=%s, size=%s", input_to_qwen, new_size)

            self._update_meta(task_id, progress=0.20, stage="recognize_subject")
            logger.info("Stage recognize_subject started")
            t0 = time.time()
            subject: RecognizedSubject = self.recognizer.recognize(
                image_path=input_to_qwen,
                user_prompt=prompt,
                debug_dir=debug_dir,
            )
            logger.info("Recognized subject=%s in %.3fs", subject.label, time.time() - t0)

    
            self._update_meta(
                task_id,
                progress=0.45,
                stage="generate_lineart",
                recognized_subject=subject.model_dump(),
            )
            logger.info("Stage generate_lineart started")
            print("🔥 已进入 AI 生成模块")

            generation_result = self.lineart_generator.generate(
                subject=subject,
                user_prompt=prompt,
                output_path=lineart_path,
                debug_dir=debug_dir,
                size=settings.lineart_size,
                reference_image_path=input_to_qwen,
            )

            logger.info("AI image generation done")
            
            self._update_meta(
                task_id,
                progress=0.70,
                stage="build_steps",
                recognized_subject=subject.model_dump(),
            )
            logger.info("Stage build_steps started")

            frames_dir = output_dir / "frames"

            frames = sorted(frames_dir.glob("frame_*.png"))
            
            if not frames:
                raise RuntimeError("AI未生成任何图片，请检查API或生成逻辑")
            generated_steps = generation_result.get("steps") if isinstance(generation_result, dict) else None
            if isinstance(generated_steps, dict):
                steps = dict(generated_steps)
            else:
                steps = {}

            steps.setdefault("frames", [f.name for f in frames])
            steps.setdefault("count", len(frames))
            steps.setdefault("stepCount", len(frames))
            steps.setdefault("timestamps", [round(i / settings.fps, 4) for i in range(len(frames))])
            steps.setdefault(
                "prompts",
                [f"Step {i + 1}: continue the drawing" for i in range(len(frames))],
            )

            self.storage.write_json(steps_path, steps)
            logger.info("Using AI generated frames: %d", len(frames))

            self._update_meta(
                task_id,
                progress=0.88,
                stage="compose_video",
                recognized_subject=subject.model_dump(),
                steps=steps,
            )
            logger.info("Stage compose_video started")
            t3 = time.time()
            self.video_composer.compose(
                task_dir=task_dir,
                fps=settings.fps,
                output_path=local_video_path,
            )
            final_video_path = self.video_enhancer.enhance(
                input_video=local_video_path,
                output_video=video_path,
                subject_label=subject.label,
                user_prompt=prompt,
                reference_image=lineart_path,
                step_prompts=steps.get("prompts"),
                debug_dir=debug_dir,
            )
            logger.info("Composed video in %.3fs", time.time() - t3)
            logger.info("Final video path=%s", final_video_path)

            video_asset = {
                "name": "tutorial.mp4",
                "url": f"/tasks/{task_id}/assets/tutorial.mp4",
            }

            final_meta = self._now_meta(
                task_id=task_id,
                status="done",
                progress=1.0,
                stage="done",
                recognized_subject=subject.model_dump(),
                steps=steps,
                video_asset=video_asset,
            )
            self._save_meta(task_id, final_meta)
            logger.info("Task done in %.3fs", time.time() - started_at)

        except Exception as exc:  # noqa: BLE001
            tb = traceback.format_exc()
            self.storage.append_error(error_log, tb)
            logger.error("Task failed: %s", exc)
            logger.error(tb)

            error_meta = self._now_meta(
                task_id=task_id,
                status="error",
                progress=1.0,
                stage="error",
                error=str(exc),
            )
            self._save_meta(task_id, error_meta)

    def get_asset_path(self, task_id: str, filename: str) -> Path:
        path = self.storage.output_asset_path(task_id, filename)
        if not path.exists():
            raise FileNotFoundError(filename)
        return path

    def get_step_frame_path(self, task_id: str, k: int) -> Path:
        frame_path = self.storage.task_dir(task_id) / "output" / "frames" / f"frame_{k:03d}.png"
        if not frame_path.exists():
            raise FileNotFoundError(frame_path.name)
        return frame_path


task_service = TaskService()
