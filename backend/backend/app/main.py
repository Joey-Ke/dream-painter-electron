# FILE: backend/app/main.py
from __future__ import annotations

import socket
import sys
from contextlib import closing

from fastapi import Depends, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from app.auth import require_token
from app.config import settings
from app.schemas import HealthResponse, TaskCreateResponse, TaskStatusResponse
from app.task_service import task_service
from app.utils.logger import setup_root_logger

logger = setup_root_logger(settings.log_level)

app = FastAPI(
    title=settings.app_name,
    dependencies=[Depends(require_token)],
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health", response_model=HealthResponse)
def health() -> dict:
    return {"status": "ok"}


@app.post("/tasks", response_model=TaskCreateResponse)
async def create_task(
    image: UploadFile = File(...),
    prompt: str = Form(default=""),
) -> dict:
    if not image.filename:
        raise HTTPException(status_code=400, detail="image file is required")

    content_type = image.content_type or ""
    if not content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="uploaded file must be an image")

    task_id = task_service.create_task(image_file=image, prompt=prompt or "")
    return {"taskId": task_id}


@app.get("/tasks/{task_id}", response_model=TaskStatusResponse)
def get_task(task_id: str) -> dict:
    try:
        return task_service.get_task(task_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="task not found") from exc


@app.get("/tasks/{task_id}/assets/{filename}")
def get_asset(task_id: str, filename: str):
    try:
        path = task_service.get_asset_path(task_id, filename)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="asset not found") from exc
    return FileResponse(path)


@app.get("/tasks/{task_id}/steps/{k}/frame")
def get_step_frame(task_id: str, k: int):
    try:
        path = task_service.get_step_frame_path(task_id, k)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="frame not found") from exc
    return FileResponse(path, media_type="image/png")


def find_free_port() -> int:
    with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as s:
        s.bind((settings.host, 0))
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        return int(s.getsockname()[1])


def run() -> None:
    import uvicorn

    port = settings.port
    if port <= 0:
        port = find_free_port()

    # Electron main 进程依赖这行 stdout 来解析端口
    print(f"PORT={port}", flush=True)

    uvicorn.run(
        "app.main:app",
        host=settings.host,
        port=port,
        reload=False,
        log_level=settings.log_level.lower(),
    )


if __name__ == "__main__":
    run()