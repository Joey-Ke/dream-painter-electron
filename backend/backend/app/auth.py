# FILE: backend/app/auth.py
from __future__ import annotations

from fastapi import Header, HTTPException

from app.config import settings


def require_token(x_token: str | None = Header(default=None)) -> None:
    """
    生产环境若设置 BACKEND_TOKEN，则所有接口必须校验 X-Token。
    开发环境未设置时默认放行。
    """
    if not settings.token:
        return

    if x_token != settings.token:
        raise HTTPException(status_code=401, detail="Invalid X-Token")