from __future__ import annotations

import base64
import json
import os
from io import BytesIO
from pathlib import Path
from typing import Any

from openai import OpenAI
from PIL import Image


DEFAULT_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"
DEFAULT_TEXT_MODEL = "qwen-flash"
DEFAULT_VISION_MODEL_CANDIDATES = (
    "qwen-vl-max-latest",
    "qwen-vl-max",
    "qwen-vl-plus-latest",
    "qwen-vl-plus",
)
DEFAULT_STEP_COUNT = 6


def _get_client() -> OpenAI:
    api_key = os.getenv("DASHSCOPE_API_KEY") or os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError(
            "Missing API key. Set DASHSCOPE_API_KEY or OPENAI_API_KEY in backend/.env."
        )

    return OpenAI(
        api_key=api_key,
        base_url=os.getenv("OPENAI_BASE_URL", DEFAULT_BASE_URL),
    )


def _extract_text_content(content: Any) -> str:
    if isinstance(content, str):
        return content.strip()

    if isinstance(content, list):
        text_parts: list[str] = []
        for item in content:
            if isinstance(item, dict) and item.get("type") == "text":
                text_parts.append(str(item.get("text", "")))
        return "".join(text_parts).strip()

    return str(content).strip()


def _extract_json_blob(text: str) -> str:
    text = text.strip()
    if text.startswith("{") and text.endswith("}"):
        return text

    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end <= start:
        raise ValueError(f"Model did not return JSON: {text}")
    return text[start : end + 1]


def _load_image_data_url(image_path: Path) -> str:
    image = Image.open(image_path).convert("RGB")
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
    return f"data:image/png;base64,{encoded}"


def _unique_non_empty(items: list[Any]) -> list[str]:
    normalized: list[str] = []
    for item in items:
        text = str(item).strip()
        if text and text not in normalized:
            normalized.append(text)
    return normalized


def _subject_alias(subject: str) -> str:
    lowered = (subject or "").strip().lower()
    if any(token in lowered for token in ("duck", "\u9e2d")):
        return "duck"
    if any(token in lowered for token in ("cat", "\u732b")):
        return "cat"
    if any(token in lowered for token in ("dog", "\u72d7")):
        return "dog"
    if any(token in lowered for token in ("car", "\u6c7d\u8f66", "\u8f66")):
        return "car"
    if any(token in lowered for token in ("house", "\u623f\u5b50")):
        return "house"
    if any(token in lowered for token in ("tree", "\u6811")):
        return "tree"
    return "generic"


def _default_parts(subject: str) -> list[str]:
    alias = _subject_alias(subject)
    parts_map = {
        "duck": ["head", "beak", "eye", "neck", "back", "belly", "wing", "tail", "legs", "feet"],
        "cat": ["head", "ears", "face", "body", "front legs", "back legs", "tail"],
        "dog": ["head", "ears", "face", "body", "front legs", "back legs", "tail"],
        "car": ["car body", "roof", "windows", "front wheel", "rear wheel", "details"],
        "house": ["roof", "walls", "door", "window", "ground line"],
        "tree": ["trunk", "main canopy", "left branches", "right branches", "ground line"],
        "generic": ["main outline", "secondary outline", "facial or key details", "final details"],
    }
    return parts_map[alias]


def _default_step_plan(subject: str, step_count: int) -> dict[str, Any]:
    parts = _default_parts(subject) or ["main outline", "details"]
    steps: list[dict[str, Any]] = []
    visible_parts: list[str] = []
    total_steps = max(1, step_count)

    groups: list[list[str]] = []
    cursor = 0
    remaining = len(parts)
    remaining_steps = total_steps
    while remaining > 0 and remaining_steps > 0:
        take = max(1, round(remaining / remaining_steps))
        groups.append(parts[cursor : cursor + take])
        cursor += take
        remaining -= take
        remaining_steps -= 1
    while len(groups) < total_steps:
        groups.append([])

    for idx, new_parts in enumerate(groups):
        keep_parts = list(visible_parts)
        visible_parts = _unique_non_empty(visible_parts + new_parts)
        hidden_parts = [part for part in parts if part not in visible_parts]
        if idx == 0:
            instruction = f"Start with the biggest simple shape for the {subject}."
        elif idx == total_steps - 1:
            instruction = f"Finish the {subject} by adding the last missing parts and small details."
        else:
            instruction = f"Keep the existing lines and add {' and '.join(new_parts) or 'the next part'}."

        steps.append(
            {
                "title": f"Step {idx + 1}",
                "instruction": instruction,
                "focus_parts": list(new_parts or visible_parts[-1:]),
                "new_parts": list(new_parts or visible_parts[-1:]),
                "keep_parts": keep_parts,
                "visible_parts": list(visible_parts),
                "hidden_parts": hidden_parts,
            }
        )

    return {
        "subject": subject,
        "overall_shape": f"Simple child-friendly drawing of {subject}.",
        "parts": parts,
        "steps": steps,
    }


def _normalize_step_plan(payload: dict[str, Any], subject: str, step_count: int) -> dict[str, Any]:
    fallback = _default_step_plan(subject, step_count)
    plan_subject = str(payload.get("subject") or subject).strip() or subject
    overall_shape = str(payload.get("overall_shape") or "").strip() or fallback["overall_shape"]

    parts = _unique_non_empty(list(payload.get("parts") or []))
    raw_steps = payload.get("steps") or payload.get("drawing_steps") or []

    inferred_parts: list[str] = []
    normalized_steps: list[dict[str, Any]] = []
    visible_parts: list[str] = []

    for index, raw_step in enumerate(raw_steps):
        if not isinstance(raw_step, dict):
            raw_step = {"instruction": str(raw_step)}

        focus_parts = _unique_non_empty(
            list(raw_step.get("focus_parts") or raw_step.get("parts") or raw_step.get("current_parts") or [])
        )
        new_parts = _unique_non_empty(list(raw_step.get("new_parts") or []))
        if not new_parts:
            new_parts = [part for part in focus_parts if part not in visible_parts]
        if not new_parts and focus_parts:
            new_parts = focus_parts[:1]

        keep_parts = _unique_non_empty(list(raw_step.get("keep_parts") or visible_parts))
        visible_parts = _unique_non_empty(keep_parts + new_parts)

        hidden_parts = _unique_non_empty(list(raw_step.get("hidden_parts") or []))
        title = str(raw_step.get("title") or f"Step {index + 1}").strip()
        instruction = str(
            raw_step.get("instruction")
            or raw_step.get("prompt")
            or raw_step.get("desc")
            or raw_step.get("text")
            or ""
        ).strip()
        if not instruction:
            instruction = fallback["steps"][min(index, len(fallback["steps"]) - 1)]["instruction"]

        inferred_parts.extend(focus_parts)
        inferred_parts.extend(new_parts)
        inferred_parts.extend(keep_parts)
        inferred_parts.extend(hidden_parts)

        normalized_steps.append(
            {
                "title": title,
                "instruction": instruction,
                "focus_parts": focus_parts or list(new_parts),
                "new_parts": new_parts,
                "keep_parts": keep_parts,
                "visible_parts": list(visible_parts),
                "hidden_parts": hidden_parts,
            }
        )

    if not parts:
        parts = _unique_non_empty(inferred_parts) or list(fallback["parts"])

    if not normalized_steps:
        normalized_steps = list(fallback["steps"])
        parts = list(fallback["parts"])
    else:
        for index, step in enumerate(normalized_steps):
            if not step["visible_parts"]:
                step["visible_parts"] = _unique_non_empty(step["keep_parts"] + step["new_parts"])
            if not step["hidden_parts"]:
                step["hidden_parts"] = [part for part in parts if part not in step["visible_parts"]]
            if not step["focus_parts"]:
                step["focus_parts"] = list(step["new_parts"] or step["visible_parts"][-1:])
            if not step["new_parts"]:
                fallback_step = fallback["steps"][min(index, len(fallback["steps"]) - 1)]
                step["new_parts"] = list(fallback_step["new_parts"])
                step["visible_parts"] = _unique_non_empty(step["keep_parts"] + step["new_parts"])
                step["hidden_parts"] = [part for part in parts if part not in step["visible_parts"]]

    if len(normalized_steps) < step_count:
        extra_source = fallback["steps"]
        while len(normalized_steps) < step_count:
            source = extra_source[min(len(normalized_steps), len(extra_source) - 1)]
            previous_visible = list(normalized_steps[-1]["visible_parts"]) if normalized_steps else []
            visible = _unique_non_empty(previous_visible + source["new_parts"])
            normalized_steps.append(
                {
                    "title": source["title"],
                    "instruction": source["instruction"],
                    "focus_parts": list(source["focus_parts"]),
                    "new_parts": [part for part in source["new_parts"] if part not in previous_visible]
                    or list(source["new_parts"]),
                    "keep_parts": previous_visible,
                    "visible_parts": visible,
                    "hidden_parts": [part for part in parts if part not in visible],
                }
            )

    normalized_steps = normalized_steps[:step_count]

    if normalized_steps:
        normalized_steps[-1]["visible_parts"] = list(parts)
        normalized_steps[-1]["hidden_parts"] = []
        normalized_steps[-1]["keep_parts"] = _unique_non_empty(
            [part for part in parts if part not in normalized_steps[-1]["new_parts"]]
        )

    prompts = [f"{step['title']}: {step['instruction']}" for step in normalized_steps]
    timestamps = [round(i / 2, 4) for i in range(len(normalized_steps))]

    return {
        "subject": plan_subject,
        "overall_shape": overall_shape,
        "parts": parts,
        "steps": normalized_steps,
        "prompts": prompts,
        "timestamps": timestamps,
        "stepCount": len(normalized_steps),
    }


def _model_candidates(reference_image_path: Path | None) -> list[str]:
    if reference_image_path is None:
        return [os.getenv("DRAWING_STEPS_MODEL", DEFAULT_TEXT_MODEL)]

    configured = os.getenv("DRAWING_STEPS_VISION_MODEL")
    extra = os.getenv("DRAWING_STEPS_VISION_MODEL_CANDIDATES", "")
    candidates: list[str] = []
    for value in [configured, *extra.split(",")]:
        value = (value or "").strip()
        if value and value not in candidates:
            candidates.append(value)
    for value in DEFAULT_VISION_MODEL_CANDIDATES:
        if value not in candidates:
            candidates.append(value)
    return candidates


def generate_steps_ai(
    subject: str,
    prompt: str,
    reference_image_path: Path | None = None,
    step_count: int = DEFAULT_STEP_COUNT,
) -> dict[str, Any]:
    step_count = max(1, step_count)
    fallback = _default_step_plan(subject, step_count)

    system_prompt = (
        "You are a children's drawing teacher. "
        "Plan a cumulative drawing tutorial. "
        "Each step must keep all previous lines and add only one or two new parts. "
        "Early steps must look unfinished. The last step completes the whole subject. "
        "Return only valid JSON with keys subject, overall_shape, parts, steps. "
        "Each step must contain title, instruction, focus_parts, new_parts, keep_parts, hidden_parts."
    )

    user_text = (
        f"Create a {step_count}-step drawing tutorial for {subject}.\n"
        f"Extra user prompt: {prompt or '(empty)'}\n"
        "Make the steps suitable for children, simple, and based on visible body parts.\n"
        "If a reference image is provided, analyze the full pose first, then split it into drawable parts.\n"
        "Do not output a polished art prompt. Output a teaching plan."
    )

    if _subject_alias(subject) == "duck":
        user_text += (
            "\nFor a duck, prefer a cute side-view worksheet duck."
            "\nUse clear parts such as head, beak, eye, neck, back, belly, wing, tail, legs, feet."
            "\nAvoid reducing the duck to only circles and straight lines."
            "\nKeep it simple enough for children, but make the silhouette clearly read as a duck."
        )

    if reference_image_path is None:
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_text},
        ]
    else:
        data_url = _load_image_data_url(reference_image_path)
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

    client = _get_client()
    last_error: Exception | None = None

    for model in _model_candidates(reference_image_path):
        try:
            response = client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=0.2,
                response_format={"type": "json_object"},
            )
            content = _extract_text_content(response.choices[0].message.content)
            payload = json.loads(_extract_json_blob(content))
            plan = _normalize_step_plan(payload, subject=subject, step_count=step_count)
            plan["model"] = model
            return plan
        except Exception as exc:  # noqa: BLE001
            last_error = exc

    fallback["prompts"] = [f"{step['title']}: {step['instruction']}" for step in fallback["steps"]]
    fallback["timestamps"] = [round(i / 2, 4) for i in range(len(fallback["steps"]))]
    fallback["stepCount"] = len(fallback["steps"])
    if last_error is not None:
        fallback["fallback_reason"] = str(last_error)
    return fallback


if __name__ == "__main__":
    print("=== Validate drawing steps API call ===")
    try:
        result = generate_steps_ai(subject="duck", prompt="simple worksheet")
        print("API call succeeded")
        print(json.dumps(result, ensure_ascii=False, indent=2))
    except Exception as exc:  # noqa: BLE001
        print(f"API call failed: {exc}")
