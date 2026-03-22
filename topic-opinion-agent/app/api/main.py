from __future__ import annotations

from uuid import uuid4

from fastapi import BackgroundTasks, FastAPI, HTTPException

from app.schemas.task import TopicAnalysisRequest
from app.storage.task_repo import task_repo
from app.workflow.pipeline import TopicAnalysisPipeline

app = FastAPI(title="Topic Opinion Agent", version="0.1.0")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/analysis/topic")
def create_topic_analysis(request: TopicAnalysisRequest, background: BackgroundTasks) -> dict[str, str]:
    task_id = str(uuid4())
    task_repo.create(task_id=task_id, topic_id=request.topic_id)

    def _runner() -> None:
        task_repo.update_status(task_id, "running")
        try:
            pipeline = TopicAnalysisPipeline()
            report, warnings = pipeline.run(
                topic_id=request.topic_id,
                target_date=request.target_date,
                enable_forecast=request.enable_forecast,
                use_external=request.use_external,
            )
            task_repo.save_report(task_id, report)
            if warnings:
                task_repo.update_status(task_id, "completed", warnings=warnings)
        except Exception as exc:
            task_repo.update_status(task_id, "failed", message=str(exc))

    background.add_task(_runner)
    return {"task_id": task_id}


@app.get("/analysis/{task_id}")
def get_analysis_status(task_id: str):
    task = task_repo.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="task not found")
    return task


@app.get("/report/{task_id}")
def get_report(task_id: str):
    report = task_repo.get_report(task_id)
    if not report:
        raise HTTPException(status_code=404, detail="report not found")
    return report
