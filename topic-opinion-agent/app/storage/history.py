from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any

from app.schemas.report import AgentStepLog, TopicReport

HISTORY_DIR = Path(__file__).resolve().parents[3] / "data"
HISTORY_FILE = HISTORY_DIR / "analysis_history.json"
MAX_HISTORY = 20


def _ensure_dir() -> None:
    HISTORY_DIR.mkdir(parents=True, exist_ok=True)


def save_to_history(report: TopicReport, agent_logs: list[AgentStepLog]) -> None:
    """Persist analysis result to JSON history file with atomic write."""
    _ensure_dir()
    entry = {
        "timestamp": datetime.now().isoformat(),
        "topic_id": report.topic_id,
        "overview": report.overview,
        "sentiment_summary": report.sentiment_summary,
        "risk_level": report.risk.risk_level,
        "agent_logs": [log.model_dump() for log in agent_logs],
        "report": report.model_dump(),
    }
    history = load_history_raw()
    history.insert(0, entry)
    history = history[:MAX_HISTORY]
    _write_history(history)


def load_history() -> list[dict[str, Any]]:
    """Load analysis history from JSON file (public API)."""
    return load_history_raw()


def load_history_raw() -> list[dict[str, Any]]:
    """Load and parse the history JSON file. Returns [] on any error."""
    if not HISTORY_FILE.exists():
        return []
    try:
        data = json.loads(HISTORY_FILE.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except (ValueError, TypeError):
        return []


def delete_history_entry(index: int) -> None:
    """Delete a single history entry by index."""
    history = load_history_raw()
    if 0 <= index < len(history):
        history.pop(index)
        _write_history(history)


def clear_history() -> None:
    """Delete all history entries."""
    _write_history([])


def _write_history(history: list[dict[str, Any]]) -> None:
    """Atomic write of history list to file."""
    _ensure_dir()
    tmp_fd, tmp_path = tempfile.mkstemp(
        suffix=".json", prefix="history_", dir=str(HISTORY_DIR)
    )
    try:
        with os.fdopen(tmp_fd, "w", encoding="utf-8") as f:
            json.dump(history, f, ensure_ascii=False, indent=2)
        os.replace(tmp_path, HISTORY_FILE)
    except Exception:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)
        raise
