-- MindSpider core tables for PostgreSQL bootstrap
-- This script is intentionally minimal and compatible with app/data/pg_repository.py.

CREATE TABLE IF NOT EXISTS daily_news (
    id BIGSERIAL PRIMARY KEY,
    news_id VARCHAR(128) NOT NULL,
    source_platform VARCHAR(32) NOT NULL,
    title VARCHAR(500) NOT NULL,
    url VARCHAR(512),
    description TEXT,
    extra_info TEXT,
    crawl_date DATE NOT NULL,
    rank_position INTEGER,
    add_ts BIGINT NOT NULL,
    last_modify_ts BIGINT NOT NULL,
    CONSTRAINT uq_daily_news_id_unique UNIQUE (news_id),
    CONSTRAINT uq_daily_news_unique UNIQUE (news_id, source_platform, crawl_date)
);

CREATE INDEX IF NOT EXISTS idx_daily_news_date ON daily_news (crawl_date);
CREATE INDEX IF NOT EXISTS idx_daily_news_platform ON daily_news (source_platform);
CREATE INDEX IF NOT EXISTS idx_daily_news_rank ON daily_news (rank_position);

CREATE TABLE IF NOT EXISTS daily_topics (
    id BIGSERIAL PRIMARY KEY,
    topic_id VARCHAR(64) NOT NULL,
    topic_name VARCHAR(255) NOT NULL,
    topic_description TEXT,
    keywords TEXT,
    extract_date DATE NOT NULL,
    relevance_score DOUBLE PRECISION,
    news_count INTEGER DEFAULT 0,
    processing_status VARCHAR(16) DEFAULT 'pending',
    add_ts BIGINT NOT NULL,
    last_modify_ts BIGINT NOT NULL,
    CONSTRAINT uq_daily_topics_id_unique UNIQUE (topic_id),
    CONSTRAINT uq_daily_topics_unique UNIQUE (topic_id, extract_date)
);

CREATE INDEX IF NOT EXISTS idx_daily_topics_date ON daily_topics (extract_date);
CREATE INDEX IF NOT EXISTS idx_daily_topics_status ON daily_topics (processing_status);
CREATE INDEX IF NOT EXISTS idx_daily_topics_score ON daily_topics (relevance_score);
CREATE INDEX IF NOT EXISTS idx_topic_date_status ON daily_topics (extract_date, processing_status);

CREATE TABLE IF NOT EXISTS topic_news_relation (
    id BIGSERIAL PRIMARY KEY,
    topic_id VARCHAR(64) NOT NULL,
    news_id VARCHAR(128) NOT NULL,
    relation_score DOUBLE PRECISION,
    extract_date DATE NOT NULL,
    add_ts BIGINT NOT NULL,
    CONSTRAINT uq_topic_news_unique UNIQUE (topic_id, news_id, extract_date),
    CONSTRAINT fk_topic_news_topic_id FOREIGN KEY (topic_id)
        REFERENCES daily_topics(topic_id) ON DELETE CASCADE,
    CONSTRAINT fk_topic_news_news_id FOREIGN KEY (news_id)
        REFERENCES daily_news(news_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_topic_news_topic ON topic_news_relation (topic_id);
CREATE INDEX IF NOT EXISTS idx_topic_news_news ON topic_news_relation (news_id);
CREATE INDEX IF NOT EXISTS idx_topic_news_date ON topic_news_relation (extract_date);

CREATE TABLE IF NOT EXISTS crawling_tasks (
    id BIGSERIAL PRIMARY KEY,
    task_id VARCHAR(64) NOT NULL,
    topic_id VARCHAR(64) NOT NULL,
    platform VARCHAR(32) NOT NULL,
    search_keywords TEXT NOT NULL,
    task_status VARCHAR(16) DEFAULT 'pending',
    start_time BIGINT,
    end_time BIGINT,
    total_crawled INTEGER DEFAULT 0,
    success_count INTEGER DEFAULT 0,
    error_count INTEGER DEFAULT 0,
    error_message TEXT,
    config_params TEXT,
    scheduled_date DATE NOT NULL,
    add_ts BIGINT NOT NULL,
    last_modify_ts BIGINT NOT NULL,
    CONSTRAINT uq_crawling_tasks_unique UNIQUE (task_id),
    CONSTRAINT fk_crawling_tasks_topic_id FOREIGN KEY (topic_id)
        REFERENCES daily_topics(topic_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_crawling_tasks_topic ON crawling_tasks (topic_id);
CREATE INDEX IF NOT EXISTS idx_crawling_tasks_platform ON crawling_tasks (platform);
CREATE INDEX IF NOT EXISTS idx_crawling_tasks_status ON crawling_tasks (task_status);
CREATE INDEX IF NOT EXISTS idx_crawling_tasks_date ON crawling_tasks (scheduled_date);
CREATE INDEX IF NOT EXISTS idx_task_topic_platform ON crawling_tasks (topic_id, platform, task_status);

-- Unified platform table used by TopicOpinionAgent as preferred source.
CREATE TABLE IF NOT EXISTS platform_content (
    id BIGSERIAL PRIMARY KEY,
    topic_id VARCHAR(64),
    topic_name VARCHAR(255),
    platform VARCHAR(64),
    title TEXT,
    content TEXT,
    url TEXT,
    author TEXT,
    publish_time TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW(),
    extra JSONB
);

CREATE INDEX IF NOT EXISTS idx_platform_content_topic_id ON platform_content (topic_id);
CREATE INDEX IF NOT EXISTS idx_platform_content_topic_name ON platform_content (topic_name);
CREATE INDEX IF NOT EXISTS idx_platform_content_platform ON platform_content (platform);

CREATE OR REPLACE VIEW v_topic_crawling_stats AS
SELECT
    dt.topic_id,
    dt.topic_name,
    dt.extract_date,
    dt.processing_status,
    COUNT(DISTINCT ct.task_id) AS total_tasks,
    SUM(CASE WHEN ct.task_status = 'completed' THEN 1 ELSE 0 END) AS completed_tasks,
    SUM(CASE WHEN ct.task_status = 'failed' THEN 1 ELSE 0 END) AS failed_tasks,
    SUM(COALESCE(ct.total_crawled, 0)) AS total_content_crawled,
    SUM(COALESCE(ct.success_count, 0)) AS total_success_count,
    SUM(COALESCE(ct.error_count, 0)) AS total_error_count
FROM daily_topics dt
LEFT JOIN crawling_tasks ct ON dt.topic_id = ct.topic_id
GROUP BY dt.topic_id, dt.topic_name, dt.extract_date, dt.processing_status;

CREATE OR REPLACE VIEW v_daily_summary AS
SELECT
    dn.crawl_date,
    COUNT(DISTINCT dn.news_id) AS total_news,
    COUNT(DISTINCT dn.source_platform) AS platforms_covered,
    (SELECT COUNT(*) FROM daily_topics WHERE extract_date = dn.crawl_date) AS topics_extracted,
    (SELECT COUNT(*) FROM crawling_tasks WHERE scheduled_date = dn.crawl_date) AS tasks_created
FROM daily_news dn
GROUP BY dn.crawl_date
ORDER BY dn.crawl_date DESC;
