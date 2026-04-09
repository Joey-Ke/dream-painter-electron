# FILE: backend/app/utils/logger.py
from __future__ import annotations

import logging
import sys
from pathlib import Path


def setup_root_logger(level: str = "INFO") -> logging.Logger:
    logger = logging.getLogger("app")
    logger.setLevel(level)
    logger.handlers.clear()

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        logging.Formatter(
            fmt="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
    )
    logger.addHandler(handler)
    logger.propagate = False
    return logger


def create_task_logger(task_dir: Path) -> logging.Logger:
    logger_name = f"task.{task_dir.name}"
    logger = logging.getLogger(logger_name)
    logger.setLevel(logging.INFO)
    logger.handlers.clear()

    log_file = task_dir / "task.log"
    fh = logging.FileHandler(log_file, encoding="utf-8")
    fh.setFormatter(
        logging.Formatter(
            fmt="%(asctime)s | %(levelname)s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
    )
    logger.addHandler(fh)
    logger.propagate = False
    return logger