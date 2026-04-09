# FILE: backend/app/config.py
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _load_env_file(path: Path) -> None:
    if not path.exists():
        return

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()

        if value and value[0] == value[-1] and value[0] in {'"', "'"}:
            value = value[1:-1]

        os.environ.setdefault(key, value)


@dataclass
class Settings:
    app_name: str = "AI Drawing Tutor Backend"
    host: str = "127.0.0.1"
    port: int = 8000
    token: str | None = None
    base_dir: Path = Path(__file__).resolve().parents[1]
    data_dir: Path = base_dir / "data"
    tasks_dir: Path = data_dir / "tasks"
    max_qwen_side: int = 1280
    lineart_size: int = 768
    step_count: int = 12
    fps: int = 2
    line_threshold: int = 220
    log_level: str = "INFO"
    recognizer_backend: str = "auto"
    lineart_backend: str = "mock"
    seedance_enabled: bool = False

    @classmethod
    def load(cls) -> "Settings":
        base_dir = Path(__file__).resolve().parents[1]
        _load_env_file(base_dir / ".env")
        data_dir = base_dir / "data"
        tasks_dir = data_dir / "tasks"
        tasks_dir.mkdir(parents=True, exist_ok=True)

        port_env = os.getenv("BACKEND_PORT", "8000")
        try:
            port = int(port_env)
        except ValueError:
            port = 8000

        return cls(
            host=os.getenv("BACKEND_HOST", "127.0.0.1"),
            port=port,
            token=os.getenv("BACKEND_TOKEN"),
            base_dir=base_dir,
            data_dir=data_dir,
            tasks_dir=tasks_dir,
            max_qwen_side=int(os.getenv("QWEN_MAX_SIDE", "1280")),
            lineart_size=int(os.getenv("LINEART_SIZE", "768")),
            step_count=int(os.getenv("STEP_COUNT", "12")),
            fps=int(os.getenv("VIDEO_FPS", "2")),
            line_threshold=int(os.getenv("LINE_THRESHOLD", "220")),
            log_level=os.getenv("LOG_LEVEL", "INFO"),
            recognizer_backend=os.getenv("RECOGNIZER_BACKEND", "auto"),
            lineart_backend=os.getenv("LINEART_BACKEND", "seedream5"),
            seedance_enabled=os.getenv("SEEDANCE_ENABLED", "0") == "1",
        )


settings = Settings.load()
