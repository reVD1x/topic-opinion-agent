# Topic Opinion Agent — 单话题舆情分析与预测系统

基于 LLM 的多维度舆情分析流水线，支持证据追溯、风险研判与趋势预测。提供 FastAPI + Streamlit 双入口。

## 系统架构

```
streamlit_app.py / api/main.py        ← 表示层
        │
TopicAnalysisPipeline (pipeline.py)   ← 编排层 (8 步流水线)
        │
┌───────┼───────┬────────┬───────┐
│       │       │        │       │
Preprocess Sentiment Opinion Risk  Forecast  Report  ← Agent 层
│       │       │        │       │       │
        │
LLMGateway  PgRepository  ExternalBocha/Tavily  MindSpiderAdapter  ← 基础设施层
        │
PostgreSQL  ·  Bocha API  ·  Tavily API  ·  MindSpider 子模块    ← 外部依赖
```

### 数据模型

| 模型 | 文件 | 用途 |
|------|------|------|
| `UnifiedDoc` | `schemas/doc.py` | 统一文档表示（跨新闻/平台/外部源） |
| `SentimentItem` | `schemas/analysis.py` | 单条情感标注（positive/neutral/negative + confidence + reasoning） |
| `OpinionPoint` / `OpinionSummary` | `schemas/analysis.py` | 观点阵营（支持/反对/中立/争议 + evidence_ids） |
| `RiskResult` | `schemas/analysis.py` | 风险等级 + 触发因素 + 证据ID |
| `ForecastResult` | `schemas/analysis.py` | 趋势判断 + 假设 + 反事实 + 不确定性 |
| `TopicReport` | `schemas/report.py` | 聚合所有分析维度的最终报告 |
| `AgentStepLog` | `schemas/report.py` | 每个 pipeline 步骤的结构化日志 |

### 核心证据追溯机制

所有 Agent 输出均携带 `evidence_ids`，指向具体的 `UnifiedDoc.doc_id`。Pipeline 第 7 步（`evidence_chain`）会校验所有节点的证据 ID 能否回溯到原始文档，无法回溯的 ID 会被移除并产生警告。

---

## 8 步分析流水线

| 步骤 | 模块 | 说明 | LLM 依赖 |
|------|------|------|----------|
| 1 | `collect` | 从 PostgreSQL 加载话题证据，可选 Bocha/Tavily 外部检索、MindSpider 实时爬取 | 否 |
| 2 | `preprocess` | 去重（标题+前120字符）、空内容移除、长文截断（2000字符） | 否 |
| 3 | `sentiment` | 基于 LLM 的情感三分类（正向/中性/负向），含推理过程 | 是* |
| 4 | `opinion` | 抽取四大观点阵营（支持/反对/中立/争议），每观点最多5条 + 证据追溯 | 是* |
| 5 | `risk` | 关键词基线扫描 + LLM 补充触发词，输出高/中/低三级 | 是** |
| 6 | `forecast` | 趋势推断（上升/平稳/下降）、关键假设、反事实分析、不确定性评估 | 是* |
| 7 | `evidence_chain` | 验证所有节点 evidence_ids 可回溯至原始文档，自动修复断链 | 否 |
| 8 | `report` | 生成模块总结（7模块）、200-300字综合总结、完整 Markdown 报告 | 是* |

\* LLM 不可用时自动回退为保守默认值。
\*\* 基线扫描为确定性规则，LLM 仅用于补充发现。

---

## 快速开始

### 环境要求

- Python 3.11+
- PostgreSQL 数据库（含 MindSpider schema）
- （可选）Bocha / Tavily API key
- （可选）LLM API key（OpenAI 兼容接口）

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 配置环境变量

```bash
cp .env.example .env
# 编辑 .env 填入数据库连接、API key 等信息
```

关键环境变量见 `.env.example`，主要包括：
- `PG_*` — PostgreSQL 连接
- `LLM_*` — LLM API 配置
- `BOCHA_*` / `TAVILY_*` — 外部检索（可选）
- `MINDSPIDER_*` — 爬虫模块（可选）

### 3. 启动服务

**FastAPI 接口：**
```bash
uvicorn app.api.main:app --reload
# 访问 http://127.0.0.1:8000/docs
```

**Streamlit WebUI（中文）：**
```bash
streamlit run app/ui/streamlit_app.py
# 访问 http://127.0.0.1:8501
```

**MindSpider 后台爬虫：**
```bash
python app/mindspider_crawler.py
```

### 4. 运行测试

```bash
pytest tests/ -v
```

---

## API 接口

| 方法 | 路径 | 说明 |
|------|------|------|
| `GET` | `/health` | 健康检查 |
| `POST` | `/analysis/topic` | 创建话题分析任务（异步后台执行） |
| `GET` | `/analysis/{task_id}` | 查询任务状态、警告、Agent 日志 |
| `GET` | `/report/{task_id}` | 获取完整分析报告 |
| `POST` | `/mindspider/run` | 手动触发 MindSpider 爬取工作流 |

### 请求示例

```json
POST /analysis/topic
{
    "topic_id": "某品牌新品发布",
    "enable_forecast": true,
    "use_external": true,
    "use_mindspider": false
}
```

---

## 项目结构

```
topic-opinion-agent/
├── app/
│   ├── agents/          # 6 个分析 Agent（preprocess/sentiment/opinion/risk/forecast/report）
│   ├── api/             # FastAPI 入口与路由
│   ├── common/          # 共享常量（constants.py）、工具（utils.py）、配置（config.py）、日志（logging_config.py）
│   ├── data/            # 数据源适配（PgRepository/ExternalBocha/ExternalTavily/MindSpiderAdapter/fusion）
│   ├── llm/             # LLM 网关（OpenAI 兼容 + 指数退避重试）
│   ├── schemas/         # Pydantic 数据模型（analysis/doc/report/task）
│   ├── storage/         # 存储层（task_repo/history/db）
│   ├── ui/              # Streamlit WebUI
│   └── workflow/        # 核心编排器（pipeline.py）
├── tests/               # 32 个单元测试
├── MindSpider/          # 独立嵌入式爬虫子模块
├── docker-compose.yml
├── Dockerfile
├── requirements.txt
├── pytest.ini
└── .env.example
```

### 依赖分层

```
requirements/
├── base.txt      # 核心依赖（sqlalchemy, psycopg2, openai, pandas 等）
├── api.txt       # fastapi, uvicorn, pydantic
├── ui.txt        # streamlit
└── crawler.txt   # playwright, opencv, redis, jieba, wordcloud 等
```

---

## LLM 回退行为

系统在以下情况会自动回退而不中断流水线：

| Agent | LLM 不可用时行为 |
|-------|-----------------|
| Sentiment | 全部标记为 neutral（置信度 0.5） |
| Opinion | 返回占位观点 |
| Risk | 仅使用基线关键词扫描（确定性规则） |
| Forecast | 返回保守默认值（flat / high uncertainty） |
| Report (module summaries) | 返回格式化模板文本 |
| Report (narrative) | 返回模板化总结 |

---

## Docker Compose 部署

四个隔离服务：

| 服务 | 说明 |
|------|------|
| `db` | PostgreSQL（含 MindSpider schema 初始化） |
| `api` | FastAPI 后端 |
| `ui` | Streamlit 前端 |
| `crawler` | MindSpider 定时爬虫 |

```bash
docker compose up --build -d
docker compose ps          # 检查状态
docker compose down        # 停止所有服务
```

---

## 设计要点

### 已实现
- **证据可追溯**：每个分析节点输出均携带 `evidence_ids`，第 7 步自动校验完整性
- **LLM 降级**：LLM 不可用时所有 Agent 有确定性回退路径，流水线不会中断
- **模块解耦**：MindSpider 通过 Adapter 模式隔离，Agent 与数据源解耦
- **实时计时**：WebUI `st.status` 中每步显示已用时间（如 `采集 (2.3s): 完成`）
- **分析历史**：Streamlit 侧边栏保存最近 20 次分析记录，点击可恢复查看
- **报告导出**：支持下载 Markdown 格式报告
- **结构化日志**：所有 Agent 和基础设施模块接入 Python logging
- **安全输入**：WebUI 输入含字符限制和 SQL 特殊字符过滤

### 当前限制
- 任务存储为内存模式（重启丢失），生产环境需替换为数据库
- API 不支持任务取消/删除/分页
- 部分 SQL 使用 f-string 拼接表名（来源为环境变量，风险可控）

---

## 开发

```bash
# 运行所有测试
pytest tests/ -v

# 运行单个测试文件
pytest tests/test_evidence_chain.py -v

# 检查代码导入
python -c "from app.workflow.pipeline import TopicAnalysisPipeline; print('OK')"
```
