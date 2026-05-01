from __future__ import annotations

import logging
from datetime import date
from uuid import uuid4

from fastapi import BackgroundTasks, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from app.common.logging_config import setup_logging
from app.data.mindspider_adapter import MindSpiderAdapter
from app.schemas.report import TopicReport
from app.schemas.task import TopicAnalysisRequest, TopicAnalysisTask
from app.storage.task_repo import task_repo
from app.workflow.pipeline import TopicAnalysisPipeline

setup_logging()
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Topic Opinion Agent",
    summary="单话题舆情分析与预测 API",
    description="提供话题创建、状态查询、报告拉取及 MindSpider 爬取工作流。",
    version="0.2.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

mindspider = MindSpiderAdapter()


@app.get("/health")
def health() -> dict[str, str]:
    """Health check endpoint."""
    return {"status": "ok"}


@app.post("/analysis/topic", response_model=dict[str, str])
def create_topic_analysis(request: TopicAnalysisRequest, background: BackgroundTasks) -> dict[str, str]:
    """Create a new topic analysis task. Runs asynchronously via background tasks."""
    task_id = str(uuid4())
    task_repo.create(task_id=task_id, topic_id=request.topic_id)

    def _runner() -> None:
        task_repo.update_status(task_id, "running")
        try:
            pipeline = TopicAnalysisPipeline()
            report, warnings, _mindspider_log, agent_logs = pipeline.run(
                topic_id=request.topic_id,
                target_date=request.target_date,
                enable_forecast=request.enable_forecast,
                use_external=request.use_external,
                use_mindspider=request.use_mindspider,
            )
            task_repo.save_report(task_id, report)
            task_repo.save_agent_logs(task_id, agent_logs)
            if warnings:
                task_repo.update_status(task_id, "completed", warnings=warnings)
        except Exception as exc:
            task_repo.update_status(task_id, "failed", message=str(exc))

    background.add_task(_runner)
    return {"task_id": task_id}


@app.get("/analysis/{task_id}", response_model=TopicAnalysisTask)
def get_analysis_status(task_id: str):
    """Get status, warnings, and agent logs for a task."""
    task = task_repo.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="task not found")
    return task


@app.get("/report/{task_id}", response_model=TopicReport)
def get_report(task_id: str):
    """Get the final report for a completed task."""
    report = task_repo.get_report(task_id)
    if not report:
        raise HTTPException(status_code=404, detail="report not found")
    return report


@app.post("/mindspider/run")
def run_mindspider_workflow(run_date: date | None = Query(None)) -> dict[str, str]:
    """Run the MindSpider crawler workflow for a given date."""
    ok, message = mindspider.run_complete_workflow(target_date=run_date)
    if not ok:
        raise HTTPException(status_code=500, detail=message)
    return {"status": "ok", "message": message}
