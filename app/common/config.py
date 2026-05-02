from __future__ import annotations

import os
from dataclasses import dataclass
from dataclasses import field

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Settings:
    pg_host: str = os.getenv("PG_HOST", "127.0.0.1")
    pg_port: int = int(os.getenv("PG_PORT", "5432"))
    pg_user: str = os.getenv("PG_USER", "postgres")
    pg_password: str = os.getenv("PG_PASSWORD", "")
    pg_db: str = os.getenv("PG_DB", "postgres")

    table_daily_topics: str = os.getenv("TABLE_DAILY_TOPICS", "daily_topics")
    table_daily_news: str = os.getenv("TABLE_DAILY_NEWS", "daily_news")
    table_topic_news_relation: str = os.getenv("TABLE_TOPIC_NEWS_RELATION", "topic_news_relation")
    table_crawling_tasks: str = os.getenv("TABLE_CRAWLING_TASKS", "crawling_tasks")
    table_platform_content: str = os.getenv("TABLE_PLATFORM_CONTENT", "platform_content")
    table_platforms_csv: str = os.getenv(
        "TABLE_PLATFORM_LIST",
        "xhs_note,douyin_aweme,kuaishou_video,bilibili_video,weibo_note,tieba_note,zhihu_content",
    )

    topic_id_column: str = os.getenv("TOPIC_ID_COLUMN", "topic_id")
    topic_name_column: str = os.getenv("TOPIC_NAME_COLUMN", "topic_name")
    topic_date_column: str = os.getenv("TOPIC_DATE_COLUMN", "topic_date")

    bocha_enabled: bool = os.getenv("BOCHA_ENABLED", "true").lower() == "true"
    bocha_api_key: str = os.getenv("BOCHA_API_KEY", "")
    bocha_base_url: str = os.getenv("BOCHA_BASE_URL", "")

    tavily_enabled: bool = os.getenv("TAVILY_ENABLED", "true").lower() == "true"
    tavily_api_key: str = os.getenv("TAVILY_API_KEY", "")
    tavily_base_url: str = os.getenv("TAVILY_BASE_URL", "https://api.tavily.com/search")

    llm_api_key: str = os.getenv("LLM_API_KEY", "")
    llm_base_url: str = os.getenv("LLM_BASE_URL", "")
    llm_model: str = os.getenv("LLM_MODEL", "")
    llm_timeout: int = int(os.getenv("LLM_TIMEOUT", "30"))
    llm_max_retries: int = int(os.getenv("LLM_MAX_RETRIES", "3"))
    llm_retry_base_seconds: float = float(os.getenv("LLM_RETRY_BASE_SECONDS", "1.0"))
    llm_retry_max_seconds: float = float(os.getenv("LLM_RETRY_MAX_SECONDS", "8.0"))
    llm_json_mode: bool = os.getenv("LLM_JSON_MODE", "true").lower() == "true"
    llm_temperature: float = float(os.getenv("LLM_TEMPERATURE", "-1"))
    llm_thinking_disabled: bool = os.getenv("LLM_THINKING_DISABLED", "true").lower() == "true"

    mindspider_enabled: bool = os.getenv("MINDSPIDER_ENABLED", "true").lower() == "true"
    mindspider_module_path: str = os.getenv("MINDSPIDER_MODULE_PATH", "MindSpider")
    mindspider_api_key: str = os.getenv("MINDSPIDER_API_KEY", "")
    mindspider_base_url: str = os.getenv("MINDSPIDER_BASE_URL", "https://api.deepseek.com")
    mindspider_model_name: str = os.getenv("MINDSPIDER_MODEL_NAME", "deepseek-chat")
    mindspider_crawler_loop: bool = os.getenv("MINDSPIDER_CRAWLER_LOOP", "true").lower() == "true"
    mindspider_run_on_start: bool = os.getenv("MINDSPIDER_RUN_ON_START", "true").lower() == "true"
    mindspider_crawler_interval_seconds: int = int(os.getenv("MINDSPIDER_CRAWLER_INTERVAL_SECONDS", "86400"))
    mindspider_keywords_count: int = int(os.getenv("MINDSPIDER_KEYWORDS_COUNT", "100"))
    mindspider_max_keywords: int = int(os.getenv("MINDSPIDER_MAX_KEYWORDS", "50"))
    mindspider_max_notes: int = int(os.getenv("MINDSPIDER_MAX_NOTES", "50"))
    mindspider_test_mode: bool = os.getenv("MINDSPIDER_TEST_MODE", "false").lower() == "true"
    mindspider_platforms: list[str] = field(
        default_factory=lambda: [
            p.strip() for p in os.getenv("MINDSPIDER_PLATFORMS", "").split(",") if p.strip()
        ]
    )


settings = Settings()
