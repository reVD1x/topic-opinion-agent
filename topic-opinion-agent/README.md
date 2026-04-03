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
- Includes an independent full MindSpider module in this project
- Uses MindSpider through adapter calls to keep modules decoupled

## Quick Start

1. Install dependencies:

```bash
uv pip install -r requirements.txt
```

2. Create env file:

```bash
cp .env.example .env
```

3. Start service:

```bash
uv run uvicorn app.api.main:app --reload
```

或启动中文 Streamlit 页面（单一话题分析/预测）：

```bash
uv run streamlit run app/ui/streamlit_app.py
```

启动 MindSpider crawler（调用内置完整 MindSpider 模块）：

```bash
uv run python app/mindspider_crawler.py
```

4. Open docs:

- http://127.0.0.1:8000/docs
- Streamlit 默认地址: http://127.0.0.1:8501

## API

- `POST /analysis/topic`
- `GET /analysis/{task_id}`
- `GET /report/{task_id}`

## Docker Compose Deployment

This project can run as four isolated services:

- `db`: PostgreSQL for TopicOpinionAgent + MindSpider tables
- `api`: FastAPI
- `ui`: Streamlit
- `crawler`: MindSpider scheduled workflow runner

Compose now initializes PostgreSQL with `MindSpider/schema/mindspider_tables_postgres.sql`.

```bash
docker compose up --build -d
```

Check service status:

```bash
docker compose ps
```

Stop all:

```bash
docker compose down
```

MindSpider module is embedded as a full independent directory at `MindSpider/` with unchanged internal structure.

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
