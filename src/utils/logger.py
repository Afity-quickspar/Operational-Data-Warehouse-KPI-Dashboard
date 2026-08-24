"""
Structured, colorized logging used across every pipeline task.

Writes simultaneously to stdout (human-friendly) and a rolling run log file
under data/logs/, so each orchestrated run leaves an auditable trail — the
kind of observability an Airflow task log would give you, without Airflow.
"""
from __future__ import annotations

import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

_LOG_DIR = Path("data/logs")
_LEVEL_COLORS = {
    "DEBUG": "\033[38;5;245m",
    "INFO": "\033[38;5;39m",
    "WARNING": "\033[38;5;214m",
    "ERROR": "\033[38;5;196m",
    "CRITICAL": "\033[48;5;196m\033[38;5;231m",
}
_RESET = "\033[0m"


class _ColorFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        color = _LEVEL_COLORS.get(record.levelname, "")
        ts = datetime.now(timezone.utc).strftime("%H:%M:%S")
        msg = super().format(record)
        return f"{color}{ts} | {record.levelname:<7}{_RESET} | {msg}"


def get_logger(name: str = "pipeline") -> logging.Logger:
    """Return a configured logger; safe to call repeatedly (idempotent)."""
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger

    logger.setLevel(logging.DEBUG)

    # Force UTF-8 on the console so box/pipe glyphs never crash on Windows cp1252.
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

    console = logging.StreamHandler(sys.stdout)
    console.setLevel(logging.INFO)
    console.setFormatter(_ColorFormatter("%(name)s | %(message)s"))
    logger.addHandler(console)

    _LOG_DIR.mkdir(parents=True, exist_ok=True)
    run_stamp = datetime.now(timezone.utc).strftime("%Y%m%d")
    file_handler = logging.FileHandler(_LOG_DIR / f"pipeline_{run_stamp}.log", encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(
        logging.Formatter("%(asctime)s | %(levelname)-8s | %(name)s | %(message)s")
    )
    logger.addHandler(file_handler)

    logger.propagate = False
    return logger
