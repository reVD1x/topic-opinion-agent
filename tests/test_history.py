from __future__ import annotations

import json
import tempfile
from pathlib import Path

from app.schemas.analysis import OpinionSummary, RiskResult
from app.schemas.report import TopicReport
from app.storage.history import load_history_raw, save_to_history, HISTORY_DIR, HISTORY_FILE


def test_save_and_load_history(tmp_path, monkeypatch):
    """Test save/load round-trip with a temp directory."""
    tmp_dir = tmp_path / "data"
    tmp_dir.mkdir()
    tmp_file = tmp_dir / "analysis_history.json"

    # Patch to use temp paths
    monkeypatch.setattr("app.storage.history.HISTORY_DIR", tmp_dir)
    monkeypatch.setattr("app.storage.history.HISTORY_FILE", tmp_file)

    report = TopicReport(
        topic_id="test_topic",
        overview="test overview",
        source_distribution={"news": 5},
        sentiment_summary={"positive": 2, "neutral": 2, "negative": 1},
        sentiment_items=[],
        opinion_blocks=OpinionSummary(),
        risk=RiskResult(risk_level="medium", triggers=["谣言"], evidence_ids=["doc_1"]),
        evidence_list=[],
        markdown="# test",
    )
    save_to_history(report, [])

    history = load_history_raw()
    assert len(history) == 1
    assert history[0]["topic_id"] == "test_topic"
    assert history[0]["risk_level"] == "medium"


def test_load_empty_history(tmp_path, monkeypatch):
    tmp_file = tmp_path / "nonexistent.json"
    monkeypatch.setattr("app.storage.history.HISTORY_FILE", tmp_file)
    result = load_history_raw()
    assert result == []


def test_load_corrupt_history(tmp_path, monkeypatch):
    tmp_file = tmp_path / "corrupt.json"
    tmp_file.write_text("not valid json", encoding="utf-8")
    monkeypatch.setattr("app.storage.history.HISTORY_FILE", tmp_file)
    result = load_history_raw()
    assert result == []
