# FILE: backend/app/services/chat_service.py
from __future__ import annotations

import json
import os
from typing import Any

from openai import OpenAI

from app.config import settings


DEFAULT_CHAT_API_BASE = "https://dashscope.aliyuncs.com/compatible-mode/v1"


def _get_chat_client() -> OpenAI:
    api_key = settings.chat_api_key or os.getenv("CHAT_API_KEY") or os.getenv("DASHSCOPE_API_KEY")
    if not api_key:
        raise RuntimeError(
            "Missing chat API key. Set CHAT_API_KEY, DASHSCOPE_API_KEY in backend/.env."
        )
    
    base_url = settings.chat_api_base_url or os.getenv("CHAT_API_BASE_URL") or DEFAULT_CHAT_API_BASE
    
    return OpenAI(
        api_key=api_key,
        base_url=base_url,
    )


def chat_with_ai(messages: list[dict[str, str]], model: str | None = None) -> dict[str, Any]:
    """
    与AI聊天接口（AI C）对话
    
    Args:
        messages: 消息列表，格式为 [{"role": "user/assistant/system", "content": "..."}]
        model: 可选的模型名称，默认为配置中的chat_model
    
    Returns:
        包含回复内容的字典
    """
    client = _get_chat_client()
    model_name = model or settings.chat_model
    
    response = client.chat.completions.create(
        model=model_name,
        messages=messages,
        temperature=0.7,
    )
    
    content = response.choices[0].message.content
    return {
        "content": content,
        "model": model_name,
        "role": "assistant",
    }


def chat_with_text_and_tts(messages: list[dict[str, str]], model: str | None = None) -> dict[str, Any]:
    """
    与AI聊天并生成语音（调用TTS）
    
    Args:
        messages: 消息列表
        model: 可选的模型名称
    
    Returns:
        包含文本回复和语音数据的字典
    """
    chat_result = chat_with_ai(messages, model)
    
    from app.services.tts_service import text_to_speech
    
    try:
        audio_data = text_to_speech(chat_result["content"])
        chat_result["audio_base64"] = audio_data
        chat_result["tts_success"] = True
    except Exception as e:
        chat_result["tts_success"] = False
        chat_result["tts_error"] = str(e)
    
    return chat_result