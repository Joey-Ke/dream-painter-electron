from __future__ import annotations

import base64
import json
import os
from abc import ABC, abstractmethod
from io import BytesIO
from pathlib import Path
from typing import Any

import numpy as np
from openai import OpenAI
from PIL import Image

from app.schemas import RecognizedSubject


DEFAULT_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"
DEFAULT_MODEL_CANDIDATES = (
    "qwen-vl-max-latest",
    "qwen-vl-max",
    "qwen-vl-plus-latest",
    "qwen-vl-plus",
)

CAT_LABEL = "\u732b"
DOG_LABEL = "\u72d7"
CUP_LABEL = "\u676f\u5b50"
CAR_LABEL = "\u6c7d\u8f66"
APPLE_LABEL = "\u82f9\u679c"
HOUSE_LABEL = "\u623f\u5b50"
TREE_LABEL = "\u6811"
GENERIC_LABEL = "\u4e3b\u4f53"

LABEL_ALIASES: dict[str, tuple[str, ...]] = {
    CAT_LABEL: (
        CAT_LABEL,
        "\u5c0f\u732b",
        "\u732b\u54aa",
        "\u5ba0\u7269\u732b",
        "cat",
        "kitty",
        "kitten",
    ),
    DOG_LABEL: (
        DOG_LABEL,
        "\u5c0f\u72d7",
        "\u72d7\u72d7",
        "dog",
        "puppy",
    ),
    CUP_LABEL: (
        CUP_LABEL,
        "\u8336\u676f",
        "\u9a6c\u514b\u676f",
        "\u6c34\u676f",
        "cup",
        "mug",
    ),
    CAR_LABEL: (
        CAR_LABEL,
        "\u5c0f\u6c7d\u8f66",
        "\u8f66",
        "\u8f7f\u8f66",
        "car",
        "auto",
    ),
    APPLE_LABEL: (
        APPLE_LABEL,
        "apple",
    ),
    HOUSE_LABEL: (
        HOUSE_LABEL,
        "\u5c0f\u623f\u5b50",
        "\u5c4b\u5b50",
        "\u623f\u5c4b",
        "house",
        "home",
    ),
    TREE_LABEL: (
        TREE_LABEL,
        "\u5927\u6811",
        "\u6811\u6728",
        "tree",
    ),
}
KEYWORD_TO_LABEL = {
    alias.lower(): label
    for label, aliases in LABEL_ALIASES.items()
    for alias in aliases
}


class VisionRecognizer(ABC):
    @abstractmethod
    def recognize(
        self,
        image_path: Path,
        user_prompt: str,
        debug_dir: Path,
    ) -> RecognizedSubject:
        raise NotImplementedError


def _extract_text_content(content: Any) -> str:
    if isinstance(content, str):
        return content.strip()

    if isinstance(content, list):
        text_parts: list[str] = []
        for item in content:
            if not isinstance(item, dict):
                continue
            if item.get("type") == "text":
                text_parts.append(str(item.get("text", "")))
        return "".join(text_parts).strip()

    return str(content).strip()


def _extract_json_blob(text: str) -> str:
    text = text.strip()
    if text.startswith("{") and text.endswith("}"):
        return text

    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end < start:
        raise ValueError(f"Recognizer did not return JSON: {text}")
    return text[start : end + 1]


def _write_debug_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _write_debug_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _normalize_label(raw_label: str) -> str:
    cleaned = (raw_label or "").strip()
    if not cleaned:
        return GENERIC_LABEL

    lowered = cleaned.lower()
    for alias, canonical in KEYWORD_TO_LABEL.items():
        if alias in lowered:
            return canonical

    return cleaned


def _default_alternatives(label: str) -> list[str]:
    aliases = list(LABEL_ALIASES.get(label, ()))
    return aliases[:3] if aliases else [label]


def _normalize_subject_payload(payload: dict[str, Any]) -> RecognizedSubject:
    raw_label = str(payload.get("label", "")).strip()
    label = _normalize_label(raw_label)

    alternatives: list[str] = []
    for item in payload.get("alternatives", []) or []:
        item_text = str(item).strip()
        if item_text and item_text not in alternatives:
            alternatives.append(item_text)

    if not alternatives:
        alternatives = _default_alternatives(label)
    elif label not in alternatives and label != GENERIC_LABEL:
        alternatives.insert(0, label)

    reason = str(payload.get("reason", "")).strip()
    unsure = bool(payload.get("unsure", False))

    if label == GENERIC_LABEL and not reason:
        reason = "Could not confidently identify the subject from the image."
        unsure = True

    return RecognizedSubject(
        label=label,
        alternatives=alternatives,
        unsure=unsure,
        reason=reason,
    )


def _keyword_hint(user_prompt: str) -> RecognizedSubject | None:
    prompt_lower = (user_prompt or "").lower()
    for alias, label in KEYWORD_TO_LABEL.items():
        if alias in prompt_lower:
            return RecognizedSubject(
                label=label,
                alternatives=_default_alternatives(label),
                unsure=False,
                reason="Matched an explicit subject keyword in the user prompt.",
            )
    return None


class LocalHeuristicRecognizer(VisionRecognizer):
    def _image_features(self, image_path: Path) -> dict[str, float]:
        image = Image.open(image_path).convert("RGB")
        if max(image.size) > 512:
            scale = 512 / max(image.size)
            resized = (
                max(1, int(image.size[0] * scale)),
                max(1, int(image.size[1] * scale)),
            )
            image = image.resize(resized, Image.LANCZOS)

        arr = np.asarray(image, dtype=np.uint8)
        total = float(arr.shape[0] * arr.shape[1]) or 1.0

        red = arr[:, :, 0].astype(np.int16)
        green = arr[:, :, 1].astype(np.int16)
        blue = arr[:, :, 2].astype(np.int16)

        white_ratio = float(np.mean((red > 235) & (green > 235) & (blue > 235)))
        dark_ratio = float(np.mean((red < 45) & (green < 45) & (blue < 45)))
        red_ratio = float(np.mean((red > 150) & (green < 90) & (blue < 90)))
        green_ratio = float(np.mean((green > red + 20) & (green > blue + 20) & (green > 80)))
        brown_ratio = float(
            np.mean(
                (red > 70)
                & (red < 170)
                & (green > 40)
                & (green < 120)
                & (blue > 20)
                & (blue < 100)
            )
        )
        aspect_ratio = image.size[0] / max(image.size[1], 1)

        return {
            "width": float(image.size[0]),
            "height": float(image.size[1]),
            "aspect_ratio": float(aspect_ratio),
            "white_ratio": white_ratio,
            "dark_ratio": dark_ratio,
            "red_ratio": red_ratio,
            "green_ratio": green_ratio,
            "brown_ratio": brown_ratio,
            "pixel_count": total,
        }

    def _guess_from_features(self, features: dict[str, float]) -> RecognizedSubject:
        cat_score = 0.0
        if features["white_ratio"] >= 0.12:
            cat_score += 1.4
        if features["white_ratio"] >= 0.20:
            cat_score += 1.2
        if features["dark_ratio"] >= 0.05:
            cat_score += 1.0
        if 0.35 <= features["aspect_ratio"] <= 1.15:
            cat_score += 0.6
        if features["red_ratio"] >= 0.003:
            cat_score += 0.8
        if features["green_ratio"] <= 0.03:
            cat_score += 0.5

        tree_score = features["green_ratio"] * 10.0
        if features["green_ratio"] >= 0.08:
            tree_score += 1.0
        if features["brown_ratio"] >= 0.18:
            tree_score += 0.4
        if features["white_ratio"] <= 0.12:
            tree_score += 0.6

        apple_score = features["red_ratio"] * 14.0
        if features["red_ratio"] >= 0.08 and features["white_ratio"] <= 0.12:
            apple_score += 1.0

        scores = {
            CAT_LABEL: cat_score,
            TREE_LABEL: tree_score,
            APPLE_LABEL: apple_score,
        }
        best_label, best_score = max(scores.items(), key=lambda item: item[1])
        second_score = sorted(scores.values(), reverse=True)[1]

        if best_score < 2.0 or best_score - second_score < 0.45:
            return RecognizedSubject(
                label=GENERIC_LABEL,
                alternatives=[GENERIC_LABEL],
                unsure=True,
                reason="Local fallback could not confidently classify the image content.",
            )

        return RecognizedSubject(
            label=best_label,
            alternatives=_default_alternatives(best_label),
            unsure=False,
            reason=(
                "Local fallback selected the subject from image color and composition cues. "
                f"Scores={scores}"
            ),
        )

    def recognize(
        self,
        image_path: Path,
        user_prompt: str,
        debug_dir: Path,
    ) -> RecognizedSubject:
        hint = _keyword_hint(user_prompt)
        if hint is not None:
            _write_debug_json(
                debug_dir / "recognizer_fallback.json",
                {
                    "mode": "keyword_hint",
                    "subject": hint.model_dump(),
                },
            )
            return hint

        features = self._image_features(image_path)
        subject = self._guess_from_features(features)
        _write_debug_json(
            debug_dir / "recognizer_fallback.json",
            {
                "mode": "local_heuristic",
                "features": features,
                "subject": subject.model_dump(),
            },
        )
        return subject


class RealQwenRecognizer(VisionRecognizer):
    def __init__(self) -> None:
        api_key = os.getenv("DASHSCOPE_API_KEY") or os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise RuntimeError(
                "Missing API key. Set DASHSCOPE_API_KEY or OPENAI_API_KEY in backend/.env."
            )

        self.client = OpenAI(
            api_key=api_key,
            base_url=os.getenv("OPENAI_BASE_URL", DEFAULT_BASE_URL),
        )
        configured_model = os.getenv("RECOGNIZER_MODEL") or os.getenv("QWEN_VL_MODEL")
        configured_candidates = os.getenv("RECOGNIZER_MODEL_CANDIDATES", "")

        model_candidates: list[str] = []
        for value in [configured_model, *configured_candidates.split(",")]:
            value = (value or "").strip()
            if value and value not in model_candidates:
                model_candidates.append(value)
        for value in DEFAULT_MODEL_CANDIDATES:
            if value not in model_candidates:
                model_candidates.append(value)

        self.model_candidates = tuple(model_candidates)

    def _build_messages(self, image_path: Path, user_prompt: str) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        image = Image.open(image_path).convert("RGB")
        buffer = BytesIO()
        image.save(buffer, format="PNG")
        data_url = f"data:image/png;base64,{base64.b64encode(buffer.getvalue()).decode('ascii')}"

        system_prompt = (
            "You are a children's drawing subject recognizer. "
            "Look at the uploaded image and identify the single main subject that should be taught. "
            "Ignore background, decoration, and text. "
            "Return only valid JSON with keys label, alternatives, unsure, reason. "
            "Prefer short Chinese labels such as 猫, 狗, 杯子, 汽车, 苹果, 房子, 树."
        )
        user_text = (
            "Identify the single drawing subject in this image.\n"
            f"User prompt: {user_prompt or '(empty)'}\n"
            "Return JSON only."
        )
        messages = [
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": user_text},
                    {"type": "image_url", "image_url": {"url": data_url}},
                ],
            },
        ]
        request_debug = {
            "system_prompt": system_prompt,
            "user_text": user_text,
            "models": list(self.model_candidates),
            "image_path": str(image_path),
        }
        return messages, request_debug

    def recognize(
        self,
        image_path: Path,
        user_prompt: str,
        debug_dir: Path,
    ) -> RecognizedSubject:
        messages, request_debug = self._build_messages(image_path, user_prompt)
        _write_debug_json(debug_dir / "qwen_request.json", request_debug)

        last_error: Exception | None = None
        attempts: list[dict[str, str]] = []

        for model in self.model_candidates:
            try:
                response = self.client.chat.completions.create(
                    model=model,
                    messages=messages,
                    temperature=0.1,
                    response_format={"type": "json_object"},
                )
                content = _extract_text_content(response.choices[0].message.content)
                payload = json.loads(_extract_json_blob(content))
                subject = _normalize_subject_payload(payload)

                _write_debug_json(
                    debug_dir / "qwen_response.json",
                    {
                        "model": model,
                        "raw": payload,
                        "normalized": subject.model_dump(),
                        "attempts": attempts,
                    },
                )
                return subject
            except Exception as exc:  # noqa: BLE001
                last_error = exc
                attempts.append({"model": model, "error": str(exc)})

        _write_debug_json(debug_dir / "qwen_error.json", {"attempts": attempts})

        if last_error is None:
            raise RuntimeError("No recognizer model candidates were configured.")
        raise RuntimeError(f"Vision recognizer failed for all models: {last_error}") from last_error


class AutoVisionRecognizer(VisionRecognizer):
    def __init__(self) -> None:
        self.local_fallback = LocalHeuristicRecognizer()
        self.remote_enabled = bool(os.getenv("DASHSCOPE_API_KEY") or os.getenv("OPENAI_API_KEY"))

    def recognize(
        self,
        image_path: Path,
        user_prompt: str,
        debug_dir: Path,
    ) -> RecognizedSubject:
        if self.remote_enabled:
            try:
                remote = RealQwenRecognizer()
                return remote.recognize(image_path=image_path, user_prompt=user_prompt, debug_dir=debug_dir)
            except Exception as exc:  # noqa: BLE001
                _write_debug_text(debug_dir / "qwen_error.txt", f"{exc}\n")

        return self.local_fallback.recognize(
            image_path=image_path,
            user_prompt=user_prompt,
            debug_dir=debug_dir,
        )


def build_recognizer(backend_name: str) -> VisionRecognizer:
    normalized = (backend_name or "").strip().lower()

    if normalized in {"mock", "local", "heuristic"}:
        return LocalHeuristicRecognizer()
    if normalized in {"qwen", "remote"}:
        return RealQwenRecognizer()
    if normalized in {"auto", ""}:
        return AutoVisionRecognizer()

    raise ValueError(f"Unknown recognizer backend: {backend_name}")
