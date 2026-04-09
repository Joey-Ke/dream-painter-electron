# FILE: backend/app/services/storage.py
from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any


class StorageService:
    def __init__(self, tasks_dir: Path) -> None:
        self.tasks_dir = tasks_dir
        self.tasks_dir.mkdir(parents=True, exist_ok=True)

    def create_task_dir(self) -> tuple[str, Path]:
        task_id = f"t_{uuid.uuid4().hex[:12]}"
        task_dir = self.tasks_dir / task_id
        (task_dir / "input").mkdir(parents=True, exist_ok=True)
        (task_dir / "debug").mkdir(parents=True, exist_ok=True)
        (task_dir / "output").mkdir(parents=True, exist_ok=True)
        return task_id, task_dir

    def task_dir(self, task_id: str) -> Path:
        return self.tasks_dir / task_id

    def meta_path(self, task_id: str) -> Path:
        return self.task_dir(task_id) / "meta.json"

    def error_log_path(self, task_id: str) -> Path:
        return self.task_dir(task_id) / "error.log"

    def output_asset_path(self, task_id: str, filename: str) -> Path:
        safe_name = Path(filename).name
        return self.task_dir(task_id) / "output" / safe_name

    def write_json(self, path: Path, data: Any) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def read_json(self, path: Path) -> Any:
        return json.loads(path.read_text(encoding="utf-8"))

    def write_text(self, path: Path, content: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    def append_error(self, path: Path, content: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as f:
            f.write(content)
            if not content.endswith("\n"):
                f.write("\n")