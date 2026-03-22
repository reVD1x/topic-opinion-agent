from __future__ import annotations

from datetime import datetime
from threading import Lock
from typing import Literal

from app.schemas.report import TopicReport
from app.schemas.task import TopicAnalysisTask


class TaskRepository:
    def __init__(self) -> None:
        self._lock = Lock()
        self._tasks: dict[str, TopicAnalysisTask] = {}
        self._reports: dict[str, TopicReport] = {}

    def create(self, task_id: str, topic_id: str) -> TopicAnalysisTask:
        now = datetime.utcnow()
        task = TopicAnalysisTask(
            task_id=task_id,
            topic_id=topic_id,
            status="queued",
            created_at=now,
            updated_at=now,
        )
        with self._lock:
            self._tasks[task_id] = task
        return task

    def update_status(
        self,
        task_id: str,
        status: Literal["queued", "running", "completed", "failed"],
        message: str | None = None,
        warnings: list[str] | None = None,
    ) -> None:
        with self._lock:
            task = self._tasks[task_id]
            task.status = status
            task.updated_at = datetime.utcnow()
            task.message = message
            if warnings is not None:
                task.warnings = warnings

    def save_report(self, task_id: str, report: TopicReport) -> None:
        with self._lock:
            self._reports[task_id] = report
            task = self._tasks[task_id]
            task.status = "completed"
            task.updated_at = datetime.utcnow()

    def get_task(self, task_id: str) -> TopicAnalysisTask | None:
        return self._tasks.get(task_id)

    def get_report(self, task_id: str) -> TopicReport | None:
        return self._reports.get(task_id)


task_repo = TaskRepository()
