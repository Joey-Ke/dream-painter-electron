# FILE: backend/app/main.py
from __future__ import annotations

import socket
import sys
from contextlib import closing

from fastapi import Depends, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel

from app.auth import require_token
from app.config import settings
from app.schemas import HealthResponse, TaskCreateResponse, TaskStatusResponse
from app.services.chat_service import chat_with_ai, chat_with_text_and_tts
from app.services.tts_service import text_to_speech
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


# ========== 聊天接口（AI C） ==========

class ChatMessage(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    messages: list[ChatMessage]
    model: str | None = None
    include_tts: bool = False


class ChatResponse(BaseModel):
    content: str
    model: str
    role: str
    audio_base64: str | None = None
    tts_success: bool | None = None


@app.post("/chat", response_model=ChatResponse)
def chat(request: ChatRequest) -> dict:
    """
    与AI聊天（AI C）
    
    Args:
        messages: 消息列表
        model: 可选的模型名称
        include_tts: 是否同时生成语音
    """
    try:
        messages_dict = [m.dict() for m in request.messages]
        
        if request.include_tts:
            result = chat_with_text_and_tts(messages_dict, request.model)
        else:
            result = chat_with_ai(messages_dict, request.model)
        
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ========== TTS接口 ==========

class TTSRequest(BaseModel):
    text: str
    voice: str | None = None


class TTSResponse(BaseModel):
    audio_base64: str


@app.post("/tts", response_model=TTSResponse)
def tts(request: TTSRequest) -> dict:
    """
    将文本转换为语音
    
    Args:
        text: 要转换的文本
        voice: 可选的语音名称
    """
    try:
        audio_base64 = text_to_speech(request.text, request.voice)
        return {"audio_base64": audio_base64}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ========== 视频生成接口 ==========

class VideoGenerateRequest(BaseModel):
    task_id: str
    step_indices: list[int] | None = None
    fps: int = 12


class VideoGenerateResponse(BaseModel):
    video_url: str
    step_count: int


@app.post("/tasks/{task_id}/generate-video", response_model=VideoGenerateResponse)
def generate_video(task_id: str, request: VideoGenerateRequest) -> dict:
    """
    为指定步骤生成视频
    
    Args:
        task_id: 任务ID
        step_indices: 要生成视频的步骤索引列表，默认全部步骤
        fps: 视频帧率
    """
    try:
        task = task_service.get_task(task_id)
        if task["status"] != "done":
            raise HTTPException(status_code=400, detail="Task is not completed")
        
        steps = task.get("steps", {})
        step_count = steps.get("stepCount", 0)
        
        if step_count == 0:
            raise HTTPException(status_code=400, detail="No steps found for this task")
        
        from app.services.video_composer import VideoComposer
        
        task_dir = task_service.storage.task_dir(task_id)
        output_dir = task_dir / "output"
        
        if request.step_indices:
            selected_indices = sorted(set(request.step_indices))
            selected_indices = [i for i in selected_indices if 0 <= i < step_count]
        else:
            selected_indices = list(range(step_count))
        
        if not selected_indices:
            raise HTTPException(status_code=400, detail="No valid step indices provided")
        
        video_composer = VideoComposer()
        output_path = output_dir / f"tutorial_{min(selected_indices)}-{max(selected_indices)}.mp4"
        
        video_composer.compose(
            task_dir=task_dir,
            fps=request.fps,
            output_path=output_path,
            step_indices=selected_indices,
        )
        
        video_url = f"/tasks/{task_id}/assets/{output_path.name}"
        
        return {
            "video_url": video_url,
            "step_count": len(selected_indices),
        }
    except KeyError:
        raise HTTPException(status_code=404, detail="Task not found")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


def find_free_port() -> int:
    with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as s:
        s.bind((settings.host, 0))
        s.setsockopt(socket.SOL_SOCKET, SO_REUSEADDR, 1)
        return int(s.getsockname()[1])


def run() -> None:
    import uvicorn

    port = settings.port
    if port <= 0:
        port = find_free_port()

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