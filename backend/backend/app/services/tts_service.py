# FILE: backend/app/services/tts_service.py
from __future__ import annotations

import base64
import os

import requests

from app.config import settings


DEFAULT_TTS_API_BASE = "https://dashscope.aliyuncs.com/api/text2speech/v1"


def text_to_speech(text: str, voice: str | None = None) -> str:
    """
    将文本转换为语音，返回Base64编码的音频数据
    
    Args:
        text: 要转换的文本
        voice: 可选的语音名称，默认为配置中的tts_voice
    
    Returns:
        Base64编码的音频数据字符串
    """
    api_key = settings.tts_api_key or os.getenv("TTS_API_KEY") or os.getenv("DASHSCOPE_API_KEY")
    if not api_key:
        raise RuntimeError(
            "Missing TTS API key. Set TTS_API_KEY or DASHSCOPE_API_KEY in backend/.env."
        )
    
    voice_name = voice or settings.tts_voice
    base_url = settings.tts_api_base_url or os.getenv("TTS_API_BASE_URL") or DEFAULT_TTS_API_BASE
    
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    
    payload = {
        "model": "sambert-zh-general",
        "input": text,
        "voice": voice_name,
        "format": "mp3",
        "sample_rate": 16000,
    }
    
    response = requests.post(base_url, headers=headers, json=payload)
    
    if response.status_code != 200:
        raise RuntimeError(f"TTS API request failed: {response.status_code} - {response.text}")
    
    result = response.json()
    audio_data = result.get("audio")
    
    if not audio_data:
        raise RuntimeError(f"TTS API returned no audio data: {result}")
    
    return audio_data


def text_to_speech_file(text: str, output_path: str, voice: str | None = None) -> None:
    """
    将文本转换为语音并保存到文件
    
    Args:
        text: 要转换的文本
        output_path: 输出文件路径
        voice: 可选的语音名称
    """
    audio_base64 = text_to_speech(text, voice)
    audio_bytes = base64.b64decode(audio_base64)
    
    with open(output_path, "wb") as f:
        f.write(audio_bytes)