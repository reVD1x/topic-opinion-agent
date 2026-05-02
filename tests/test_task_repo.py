from __future__ import annotations

from app.storage.task_repo import TaskRepository


def test_create_task():
    repo = TaskRepository()
    task = repo.create("id1", "test_topic")
    assert task.task_id == "id1"
    assert task.status == "queued"


def test_lifecycle():
    repo = TaskRepository()
    repo.create("id1", "test_topic")
    repo.update_status("id1", "running")
    t = repo.get_task("id1")
    assert t.status == "running"

    from app.schemas.report import TopicReport
    from app.schemas.analysis import RiskResult, OpinionSummary

    report = TopicReport(
        topic_id="test",
        overview="test",
        source_distribution={},
        sentiment_summary={},
        sentiment_items=[],
        opinion_blocks=OpinionSummary(),
        risk=RiskResult(risk_level="low", triggers=[], evidence_ids=[]),
        evidence_list=[],
        markdown="# test",
    )
    repo.save_report("id1", report)
    t = repo.get_task("id1")
    assert t.status == "completed"
    r = repo.get_report("id1")
    assert r is not None
    assert r.topic_id == "test"


def test_get_nonexistent():
    repo = TaskRepository()
    assert repo.get_task("noexist") is None
    assert repo.get_report("noexist") is None


def test_save_agent_logs():
    repo = TaskRepository()
    repo.create("id1", "test_topic")
    from app.schemas.report import AgentStepLog
    logs = [
        AgentStepLog(step=1, module="collect", status="ok", input_docs=0, output_summary="ok", evidence_count=5, duration_ms=100),
    ]
    repo.save_agent_logs("id1", logs)
    t = repo.get_task("id1")
    assert len(t.agent_logs) == 1
    assert t.agent_logs[0].module == "collect"
