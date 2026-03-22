# Topic Opinion Agent

Single-topic opinion analysis service for interview/demo scenarios.

## What This Project Implements

- Pulls topic evidence from MindSpider tables in PostgreSQL
- Optionally enriches evidence from Bocha and Tavily
- Runs a simple multi-step analysis pipeline:
  - preprocess
  - sentiment
  - opinion extraction
  - risk judgement
  - optional LLM-only forecast
- Produces a traceable report with `evidence_ids`
- Exposes APIs via FastAPI

## Quick Start

1. Install dependencies:

```bash
pip install -r requirements.txt
```

2. Create env file:

```bash
cp .env.example .env
```

3. Start service:

```bash
uvicorn app.api.main:app --reload
```

或启动中文 Streamlit 页面（单一话题分析/预测）：

```bash
streamlit run app/ui/streamlit_app.py
```

4. Open docs:

- http://127.0.0.1:8000/docs
- Streamlit 默认地址: http://127.0.0.1:8501

## API

- `POST /analysis/topic`
- `GET /analysis/{task_id}`
- `GET /report/{task_id}`

## Notes

- Forecast is explicitly `llm_inference_only`
- External search failure will not break the main pipeline
- Current task storage is in-memory (for quick MVP)

## MindSpider Tables

- `daily_news`
- `daily_topics`
- `topic_news_relation`
- `platform_content`
- `crawling_tasks`

Legacy compatibility is kept for older deployments that still use platform-specific tables.

Repository logic now reads topic-linked news via `daily_topics -> topic_news_relation -> daily_news`, and reads platform evidence from `platform_content` first.
