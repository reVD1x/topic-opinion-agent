# MindSpider 可调用 API 总表

本文档整理 `MindSpider/` 目录下可直接调用的接口，包括：
- 命令行接口（CLI）
- Python 模块级/类级调用接口
- FastAPI HTTP/WebSocket 接口（MediaCrawler WebUI API）

说明：
- 以“可调用”为标准，优先收录对外入口和公开方法（非 `_` 开头）。
- 部分方法虽为公开方法，但主要用于内部流程，已在“用途”中标注。

---

## 1. 顶层主入口 API

来源：`MindSpider/main.py`

### 1.1 CLI 入口

```bash
python MindSpider/main.py [options]
```

可用参数：
- `--setup`: 初始化项目（配置/依赖/数据库检查）
- `--status`: 显示项目状态
- `--init-db`: 初始化数据库
- `--broad-topic`: 仅运行话题提取模块
- `--deep-sentiment`: 仅运行深度情感爬取模块
- `--complete`: 运行完整流程（话题提取 + 深度爬取）
- `--date YYYY-MM-DD`: 指定目标日期
- `--platforms xhs dy ...`: 指定平台列表，支持 `xhs dy ks bili wb tieba zhihu`
- `--keywords-count N`: 话题提取关键词数量（默认 100）
- `--max-keywords N`: 每个平台最大关键词数（默认 50）
- `--max-notes N`: 每个关键词最大爬取数量（默认 50）
- `--test`: 测试模式

示例：
```bash
python MindSpider/main.py --complete --date 2026-03-09 --platforms xhs zhihu --test
```

### 1.2 Python 类调用

类：`MindSpider`

公开方法：
- `check_config() -> bool`: 校验基础配置
- `check_database_connection() -> bool`: 校验数据库连接
- `check_database_tables() -> bool`: 校验核心表是否存在
- `initialize_database() -> bool`: 初始化数据库结构
- `check_dependencies() -> bool`: 检查依赖并安装 MediaCrawler 子模块依赖
- `run_broad_topic_extraction(extract_date=None, keywords_count=100) -> bool`
- `run_deep_sentiment_crawling(target_date=None, platforms=None, max_keywords=50, max_notes=50, test_mode=False) -> bool`
- `run_complete_workflow(target_date=None, platforms=None, keywords_count=100, max_keywords=50, max_notes=50, test_mode=False) -> bool`
- `show_status() -> None`: 打印状态
- `setup_project() -> bool`: 项目一键初始化

---

## 2. BroadTopicExtraction 模块 API

目录：`MindSpider/BroadTopicExtraction/`

### 2.1 模块 CLI

来源：`MindSpider/BroadTopicExtraction/main.py`

```bash
python MindSpider/BroadTopicExtraction/main.py [options]
```

参数：
- `--sources <source...>`: 指定新闻源（可多选）
- `--keywords N`: 最大关键词数量（默认 100，范围 1-200）
- `--quiet`: 简化输出
- `--list-sources`: 列出支持新闻源

### 2.2 主流程类 API

类：`BroadTopicExtraction`

公开方法：
- `close()`
- `run_daily_extraction(news_sources=None, max_keywords=100) -> Dict`: 每日话题提取完整流程
- `print_extraction_results(extraction_result: Dict)`
- `get_keywords_for_crawling(extract_date=None) -> List[str]`
- `get_daily_analysis(target_date=None) -> Optional[Dict]`
- `get_recent_analysis(days=7) -> List[Dict]`

模块级函数：
- `run_extraction_command(sources=None, keywords_count=100, show_details=True) -> bool`
- `main()`

### 2.3 新闻采集 API

来源：`MindSpider/BroadTopicExtraction/get_today_news.py`

类：`NewsCollector`

公开方法：
- `close()`
- `fetch_news(source: str) -> dict`: 拉取单个新闻源
- `get_popular_news(sources=None) -> List[dict]`: 批量拉取新闻源
- `collect_and_save_news(sources=None) -> Dict`: 拉取并存储
- `get_today_news() -> List[Dict]`: 读当日新闻

可用新闻源常量：`SOURCE_NAMES`，典型包括：
- `weibo`, `zhihu`, `bilibili-hot-search`, `toutiao`, `douyin`, `github-trending-today`, `coolapk`, `tieba`, `wallstreetcn`, `thepaper`, `cls-hot`, `xueqiu`

### 2.4 关键词提取 API

来源：`MindSpider/BroadTopicExtraction/topic_extractor.py`

类：`TopicExtractor`

公开方法：
- `extract_keywords_and_summary(news_list, max_keywords=100) -> Tuple[List[str], str]`
- `get_search_keywords(keywords, limit=10) -> List[str]`

### 2.5 数据存储 API（BroadTopicExtraction）

来源：`MindSpider/BroadTopicExtraction/database_manager.py`

类：`DatabaseManager`

公开方法：
- `connect()`
- `close()`
- `save_daily_news(news_data, crawl_date=None) -> int`
- `get_daily_news(crawl_date=None) -> List[Dict]`
- `save_daily_topics(keywords, summary, extract_date=None) -> bool`
- `get_daily_topics(extract_date=None) -> Optional[Dict]`
- `get_recent_topics(days=7) -> List[Dict]`
- `get_summary_stats(days=7) -> Dict`

---

## 3. DeepSentimentCrawling 模块 API

目录：`MindSpider/DeepSentimentCrawling/`

### 3.1 模块 CLI

来源：`MindSpider/DeepSentimentCrawling/main.py`

```bash
python MindSpider/DeepSentimentCrawling/main.py [options]
```

参数：
- `--date YYYY-MM-DD`
- `--platform <one>`: 单平台爬取（`xhs dy ks bili wb tieba zhihu`）
- `--platforms <multi...>`: 多平台爬取
- `--max-keywords N`: 每个平台最大关键词数（默认 50）
- `--max-notes N`: 每个平台最大内容数（默认 50）
- `--login-type qrcode|phone|cookie`
- `--list-topics`: 查看最近话题
- `--days N`: 配合 `--list-topics` 使用（默认 7）
- `--guide`: 显示平台使用指南
- `--test`: 测试模式（自动压小抓取规模）

### 3.2 主流程类 API

类：`DeepSentimentCrawling`

公开方法：
- `run_daily_crawling(target_date=None, platforms=None, max_keywords_per_platform=50, max_notes_per_platform=50, login_type="qrcode") -> Dict`
- `run_platform_crawling(platform, target_date=None, max_keywords=50, max_notes=50, login_type="qrcode") -> Dict`
- `list_available_topics(days=7)`
- `show_platform_guide()`
- `close()`

### 3.3 关键词管理 API

来源：`MindSpider/DeepSentimentCrawling/keyword_manager.py`

类：`KeywordManager`

公开方法：
- `connect()`
- `get_latest_keywords(target_date=None, max_keywords=100) -> List[str]`
- `get_daily_topics(extract_date=None) -> Optional[Dict]`
- `get_recent_topics(days=7) -> List[Dict]`
- `get_all_keywords_for_platforms(platforms, target_date=None, max_keywords=100) -> List[str]`
- `get_keywords_for_platform(platform, target_date=None, max_keywords=50) -> List[str]`
- `get_crawling_summary(target_date=None) -> Dict`
- `close()`

### 3.4 平台爬虫调度 API

来源：`MindSpider/DeepSentimentCrawling/platform_crawler.py`

类：`PlatformCrawler`

公开方法：
- `configure_mediacrawler_db() -> bool`
- `create_base_config(platform, keywords, crawler_type="search", max_notes=50) -> bool`
- `run_crawler(platform, keywords, login_type="qrcode", max_notes=50) -> Dict`
- `run_multi_platform_crawl_by_keywords(keywords, platforms, login_type="qrcode", max_notes_per_keyword=50) -> Dict`
- `get_crawl_statistics() -> Dict`
- `save_crawl_log(log_path=None)`

---

## 4. MediaCrawler 子模块 API（MindSpider 内嵌）

目录：`MindSpider/DeepSentimentCrawling/MediaCrawler/`

### 4.1 MediaCrawler CLI

来源：`MediaCrawler/main.py` + `MediaCrawler/cmd_arg/arg.py`

```bash
cd MindSpider/DeepSentimentCrawling/MediaCrawler
python main.py [options]
```

参数（核心）：
- `--platform xhs|dy|ks|bili|wb|tieba|zhihu`
- `--lt qrcode|phone|cookie`
- `--type search|detail|creator`
- `--start N`
- `--keywords "词1,词2"`
- `--get_comment true|false`
- `--get_sub_comment true|false`
- `--headless true|false`
- `--save_data_option csv|db|json|sqlite|mongodb|excel|postgres`
- `--init_db sqlite|mysql|postgres`
- `--cookies "..."`
- `--specified_id "id1,id2,..."`（`detail` 模式）
- `--creator_id "id1,id2,..."`（`creator` 模式）

### 4.2 WebUI FastAPI HTTP API

来源：`MediaCrawler/api/main.py` + `MediaCrawler/api/routers/*.py`

启动方式：
```bash
cd MindSpider/DeepSentimentCrawling/MediaCrawler
uvicorn api.main:app --port 8080 --reload
```

Base URL：`http://localhost:8080`

HTTP 路由：
- `GET /`: 返回 WebUI 首页或 API 说明
- `GET /api/health`: 健康检查
- `GET /api/env/check`: 环境检查（调用 `uv run main.py --help`）
- `GET /api/config/platforms`: 支持平台列表
- `GET /api/config/options`: 登录方式/爬取类型/存储方式等配置项

Crawler 控制路由（前缀 `/api/crawler`）：
- `POST /api/crawler/start`: 启动爬虫
  - Body: `CrawlerStartRequest`
- `POST /api/crawler/stop`: 停止爬虫
- `GET /api/crawler/status`: 获取状态（`CrawlerStatusResponse`）
- `GET /api/crawler/logs?limit=100`: 获取日志

数据路由（前缀 `/api/data`）：
- `GET /api/data/files?platform=&file_type=`: 列出数据文件
- `GET /api/data/files/{file_path}?preview=true&limit=100`: 文件预览/内容
- `GET /api/data/download/{file_path}`: 文件下载
- `GET /api/data/stats`: 数据统计

WebSocket 路由：
- `WS /api/ws/logs`: 日志流
- `WS /api/ws/status`: 状态流（约每秒推送）

### 4.3 请求/响应模型（关键）

来源：`MediaCrawler/api/schemas/crawler.py`

`CrawlerStartRequest` 字段：
- `platform`: `xhs|dy|ks|bili|wb|tieba|zhihu`
- `login_type`: `qrcode|phone|cookie`（默认 `qrcode`）
- `crawler_type`: `search|detail|creator`（默认 `search`）
- `keywords`: `str`
- `specified_ids`: `str`（`detail`）
- `creator_ids`: `str`（`creator`）
- `start_page`: `int`（默认 1）
- `enable_comments`: `bool`（默认 `True`）
- `enable_sub_comments`: `bool`（默认 `False`）
- `save_option`: `csv|db|json|sqlite|mongodb|excel`
- `cookies`: `str`
- `headless`: `bool`（默认 `False`）

### 4.4 服务层 API（供路由/集成调用）

来源：`MediaCrawler/api/services/crawler_manager.py`

对象：`crawler_manager`（`CrawlerManager` 单例）

公开方法：
- `get_log_queue() -> asyncio.Queue`
- `start(config: CrawlerStartRequest) -> bool`
- `stop() -> bool`
- `get_status() -> dict`

公开属性：
- `logs -> List[LogEntry]`

---

## 5. 数据库脚本 API

目录：`MindSpider/schema/`

### 5.1 数据库初始化脚本

来源：`MindSpider/schema/init_database.py`

调用方式：
```bash
python MindSpider/schema/init_database.py
```

入口：
- `async main()`: 创建表与视图（MySQL/PostgreSQL 兼容路径）

### 5.2 数据库管理 CLI

来源：`MindSpider/schema/db_manager.py`

调用方式：
```bash
python MindSpider/schema/db_manager.py [options]
```

参数：
- `--tables`: 显示所有表
- `--stats`: 显示统计
- `--recent N`: 最近 N 天数据（默认 7）
- `--cleanup N`: 清理 N 天前数据
- `--execute`: 与 `--cleanup` 配合，执行实际删除（否则为预览）

类：`DatabaseManager`

公开方法：
- `connect()`
- `close()`
- `show_tables()`
- `show_statistics()`
- `show_recent_data(days=7)`
- `cleanup_old_data(days=90, dry_run=True)`

---

## 6. 配置 API

来源：`MindSpider/config.py`（示例见 `config.py.example`）

配置对象：
- `settings = Settings()`

常用配置字段：
- `DB_DIALECT` (`mysql|postgresql`)
- `DB_HOST`, `DB_PORT`, `DB_USER`, `DB_PASSWORD`, `DB_NAME`, `DB_CHARSET`
- `MINDSPIDER_API_KEY`, `MINDSPIDER_BASE_URL`, `MINDSPIDER_MODEL_NAME`

---

## 7. 快速调用示例

### 7.1 一键完整流程

```bash
python MindSpider/main.py --complete --date 2026-03-09 --platforms xhs dy wb --max-keywords 30 --max-notes 30
```

### 7.2 仅做话题提取

```bash
python MindSpider/main.py --broad-topic --keywords-count 120
```

### 7.3 仅做多平台深爬

```bash
python MindSpider/main.py --deep-sentiment --platforms xhs zhihu --test
```

### 7.4 启动 MediaCrawler Web API

```bash
cd MindSpider/DeepSentimentCrawling/MediaCrawler
uvicorn api.main:app --host 0.0.0.0 --port 8080
```
