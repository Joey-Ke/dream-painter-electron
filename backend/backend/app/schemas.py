# FILE: backend/app/schemas.py
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


TaskStatusLiteral = Literal["queued", "running", "done", "error"]


class RecognizedSubject(BaseModel):
    label: str
    alternatives: list[str] = Field(default_factory=list)
    unsure: bool = False
    reason: str = ""


class VideoAsset(BaseModel):
    name: str
    url: str


class StepsPayload(BaseModel):
    stepCount: int
    timestamps: list[float]
    prompts: list[str]


class TaskCreateResponse(BaseModel):
    taskId: str


class TaskStatusResponse(BaseModel):
    taskId: str
    status: TaskStatusLiteral
    progress: float = 0.0
    stage: str = "queued"
    error: str | None = None
    video_asset: VideoAsset | None = None
    steps: StepsPayload | None = None
    recognized_subject: RecognizedSubject | None = None


class HealthResponse(BaseModel):
    status: str