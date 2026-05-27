# 舆情分析智能体 — Topic Opinion Agent

基于大语言模型的舆情分析智能体，支持多维度舆情分析、证据追溯、风险研判与趋势预测。提供 FastAPI 接口与 Streamlit 可视化界面双入口。

## 系统架构

```
streamlit_app.py / api/main.py        ← 表示层
        │
TopicAnalysisPipeline (pipeline.py)   ← 编排层（8 步流水线）
        │
┌───────┼───────┬────────┬───────┬──────────┐
│       │       │        │       │          │
Preprocess Sentiment Opinion Risk  Forecast Report ← Agent 层
│       │       │        │       │       │
        │
LLMGateway  PgRepository  ExternalBocha/Tavily  MindSpiderAdapter  DataFusion ← 基础设施层
        │
PostgreSQL  ·  Bocha API  ·  Tavily API  ·  MindSpider 子模块    ← 外部依赖
```

### 核心数据模型

| 模型 | 文件 | 关键字段 |
|------|------|---------|
| `UnifiedDoc` | `schemas/doc.py` | doc_id, topic_id, source_type, title, content, url, publish_time |
| `SentimentItem` | `schemas/analysis.py` | doc_id, label（positive/neutral/negative）, confidence, reasoning |
| `OpinionPoint` / `OpinionSummary` | `schemas/analysis.py` | supports / opposes / neutrals / controversy_points，均含 content + evidence_ids |
| `RiskResult` | `schemas/analysis.py` | risk_level, triggers, evidence_ids, time_sensitivity, time_rationale |
| `ForecastResult` | `schemas/analysis.py` | trend_judgement, time_horizon, assumptions, counterfactuals, uncertainty, reasoning |
| `TopicReport` | `schemas/report.py` | 聚合所有分析维度的最终报告，含 module_summaries + narrative_summary |
| `AgentStepLog` | `schemas/report.py` | 每步的耗时、状态、输入/输出规模、告警信息 |

### 证据追溯与校验机制

所有 Agent 的输出均携带 `evidence_ids`，指向具体 `UnifiedDoc.doc_id`。流水线在第 7 步（`evidence_chain`）对所有节点的证据 ID 进行可回溯性校验，无法回溯的引用将被自动移除并产生结构化告警（warnings），在前端面板和 API 响应中均可见。校验范围覆盖情感分析、观点阵营、风险研判、趋势预测四个模块。

---

## 8 步分析流水线

| 步骤 | 模块 | 说明 | LLM 依赖 |
|------|------|------|----------|
| 1 | `collect` | 从 PostgreSQL 加载历史语料，可选启用 Bocha/Tavily 外部检索与 MindSpider 实时爬取 | 否 |
| 2 | `preprocess` | 话题相关性过滤（LLM 判定）、去重、空内容清理、长文本截断 | 是* |
| 3 | `sentiment` | 围绕话题主体的情感三分类（正向/中性/负向），含置信度与推理依据 | 是* |
| 4 | `opinion` | 提取支持/反对/中立/争议四类观点阵营，每条观点附带 evidence_ids | 是* |
| 5 | `risk` | 触发词基线扫描（确定性规则）+ LLM 补充发现，含时间敏感性评估 | 是** |
| 6 | `forecast` | 趋势推断（上升/平稳/下降）、关键假设与反事实、不确定性评估 | 是* |
| 7 | `evidence_chain` | 校验所有节点 evidence_ids 可回溯至原始文档，移除断链引用并告警 | 否 |
| 8 | `report` | 生成 7 个模块总结与综合叙述（350-500 字），输出完整 Markdown 报告 | 是* |

\* LLM 不可用时自动回退为保守默认值。
\*\* 基线触发词扫描为确定性规则，LLM 仅用于补充额外触发因素与时间敏感性判断。

---

## 常用命令速查

> 环境要求：Python 3.11+、PostgreSQL、`uv` 包管理工具。

本项目使用 `uv` 管理 Python 依赖和虚拟环境。

### 从零开始（克隆 → 运行）

```bash
# 1. 克隆仓库
git clone https://github.com/reVD1x/topic-opinion-agent.git
cd topic-opinion-agent

# 2. 安装依赖（uv 自动创建 venv）
uv sync                                          # 核心依赖
uv sync --all-extras                             # 含 API / 爬虫 / Streamlit 全部依赖
uv sync --extra api --extra crawler --extra ui   # 等价于 --all-extras

# 3. 配置环境变量
cp .env.example .env
# 编辑 .env，至少填入 PG_* 和 LLM_* 相关变量

# 4. 启动 Streamlit WebUI（最常用）
uv run --extra ui streamlit run app/ui/streamlit_app.py --server.port 8501

# 4. 或者启动 FastAPI 后端
uv run --extra api uvicorn app.api.main:app --host 127.0.0.1 --port 8000 --reload
```

### 日常启动

```bash
# Streamlit（分析入口，日常最常用）
lsof -ti :8501 | xargs kill -9 2>/dev/null   # 先杀掉旧进程
uv run --extra ui streamlit run app/ui/streamlit_app.py --server.port 8501

# FastAPI（API 入口）
lsof -ti :8000 | xargs kill -9 2>/dev/null
uv run --extra api uvicorn app.api.main:app --host 127.0.0.1 --port 8000 --reload

# 打开浏览器
open http://localhost:8501    # Streamlit
open http://localhost:8000/docs  # FastAPI Swagger 文档
```

### 爬虫相关

**支持的平台代码：**

| 代码 | 平台 | 代码 | 平台 |
|------|------|------|------|
| xhs | 小红书 | wb | 微博 |
| dy | 抖音 | tieba | 贴吧 |
| ks | 快手 | zhihu | 知乎 |
| bili | B站 | | |

**测试单个平台（首次使用需扫码登录）：**

```bash
# 测试知乎爬取
uv run --extra crawler python MindSpider/mindspider_topic_search.py \
  --keywords "核电站" --platform zhihu --max-notes 5 \
  --login-type cookie --headless false

# 测试 B 站爬取
uv run --extra crawler python MindSpider/mindspider_topic_search.py \
  --keywords "核电站" --platform bili --max-notes 5 \
  --login-type cookie --headless false

# 测试小红书（需扫码，如果 cookie 失效会自动弹出浏览器窗口）
uv run --extra crawler python MindSpider/mindspider_topic_search.py \
  --keywords "核电站" --platform xhs --max-notes 5 \
  --login-type cookie --headless false

# 使用 QR 码登录模式（强制弹出扫码窗口）
uv run --extra crawler python MindSpider/mindspider_topic_search.py \
  --keywords "核电站" --platform zhihu --max-notes 5 \
  --login-type qrcode --headless false
```

**测试适配器调用：**

```bash
uv run --extra crawler python -c "
from app.data.mindspider_adapter import MindSpiderAdapter
adapter = MindSpiderAdapter()
docs = adapter.search(keywords=['核电站'], platforms=['zhihu'], max_notes=3)
print(f'结果: {len(docs)} 条')
print(adapter.last_log)
"
```

**后台积累语料（MindSpider 完整工作流）：**

```bash
# 测试模式（小数据量验证流程）
uv run --extra crawler python MindSpider/DeepSentimentCrawling/main.py --complete --test

# 正式积累：话题提取 + 深度爬取
uv run --extra crawler python MindSpider/DeepSentimentCrawling/main.py --complete

# 指定平台和数量
uv run --extra crawler python MindSpider/DeepSentimentCrawling/main.py --complete \
  --platforms xhs,dy,ks,bili,wb,tieba,zhihu \
  --max-keywords 50 --max-notes 30

# 只提取话题（不爬取）
uv run --extra crawler python MindSpider/DeepSentimentCrawling/main.py --broad-topic

# 只爬取（基于已有话题）
uv run --extra crawler python MindSpider/DeepSentimentCrawling/main.py --deep-sentiment --test

# 运行定时循环爬虫
uv run --extra crawler python MindSpider/DeepSentimentCrawling/main.py --loop
```

**轮换式爬虫（低风控、持续积累）：**

每轮每个平台只抓 1 篇笔记，平台间冷却间隔，循环切换以分散风控压力，覆盖全部 7 个平台，适合长期后台运行积累语料。

```bash
bash scripts/rotating_crawler.sh
```

**登录问题排除：**

```bash
# 二维码不显示 → 确认 HEADLESS=false
# 登录状态丢失 → 删除浏览器数据重新登录
rm -rf MindSpider/DeepSentimentCrawling/MediaCrawler/browser_data/cdp_*

# 如果 Chrome 窗口弹不出，清理残留锁文件
find /var/folders -name "Singleton*" -path "*/mc_*" -delete 2>/dev/null
```

### 数据库操作

```bash
# 查看各平台数据量
uv run python -c "
from app.storage.db import session_scope
from sqlalchemy import text
with session_scope() as s:
    for t in ['bilibili_video','zhihu_content','weibo_note','kuaishou_video','xhs_note']:
        r = s.execute(text(f'SELECT count(1) FROM {t}')).scalar()
        print(f'{t}: {r}')
"
```

### 调试与测试

```bash
# 运行测试
uv run --all-extras pytest tests/ -v

# 单文件测试
uv run --all-extras pytest tests/test_evidence_chain.py -v

# 检查导入是否正常
uv run python -c "from app.workflow.pipeline import TopicAnalysisPipeline; print('OK')"

# 查看 Streamlit 日志
tail -f /tmp/claude-501/*/tasks/*.output 2>/dev/null

# 清理残留进程
pkill -f "mindspider_topic_search" 2>/dev/null
pkill -f "main.py.*platform" 2>/dev/null
lsof -ti :8501 | xargs kill -9 2>/dev/null
```

### 环境变量参考

| 变量 | 说明 | 必填 |
|------|------|------|
| `PG_HOST` / `PG_PORT` / `PG_USER` / `PG_PASSWORD` / `PG_DB` | PostgreSQL 连接 | 是 |
| `LLM_MODEL` / `LLM_BASE_URL` / `LLM_API_KEY` | LLM API 配置 | 是 |
| `LLM_TIMEOUT` / `LLM_MAX_RETRIES` | LLM 超时与重试 | 否 |
| `BOCHA_ENABLED` / `BOCHA_API_KEY` / `BOCHA_BASE_URL` | 博查外部检索 | 否 |
| `TAVILY_ENABLED` / `TAVILY_API_KEY` | Tavily 外部检索 | 否 |
| `MINDSPIDER_ENABLED` / `MINDSPIDER_MODULE_PATH` | 实时爬取 | 否 |

---

## API 接口

| 方法 | 路径 | 说明 |
|------|------|------|
| `GET` | `/health` | 健康检查，返回服务状态与依赖组件连通性 |
| `POST` | `/analysis/topic` | 创建话题分析任务（异步后台执行，立即返回 task_id） |
| `GET` | `/analysis/{task_id}` | 查询任务实时状态、当前阶段、各模块日志与告警 |
| `GET` | `/report/{task_id}` | 获取已完成任务的完整结构化报告 |
| `POST` | `/mindspider/run` | 手动触发 MindSpider 后台爬取工作流 |

### 请求示例

```json
POST /analysis/topic
{
    "topic_id": "核电站",
    "enable_forecast": true,
    "use_external": true,
    "use_mindspider": true,
    "mindspider_platforms": ["bili", "zhihu"]
}
```

### 任务生命周期

创建（created）→ 采集中（collecting）→ 分析中（analyzing）→ 已完成（completed）/ 失败（failed）

---

## 项目结构

```
├── app/
│   ├── agents/          # 6 个分析 Agent（preprocess / sentiment / opinion / risk / forecast / report）
│   ├── api/             # FastAPI 路由与入口（main.py）
│   ├── common/          # 共享模块（constants.py / utils.py / config.py / logging_config.py）
│   ├── data/            # 数据源适配层（pg_repository / external_bocha / external_tavily / mindspider_adapter / fusion）
│   ├── llm/             # LLM 调用网关（OpenAI 兼容接口 + 指数退避重试）
│   ├── schemas/         # Pydantic 数据模型（analysis.py / doc.py / report.py / task.py）
│   ├── storage/         # 存储层（task_repo / history / db）
│   ├── ui/              # Streamlit WebUI（streamlit_app.py）
│   └── workflow/        # 核心编排器（pipeline.py — 8 步流水线）
├── MindSpider/          # 独立嵌入式爬虫子模块
├── diagrams/            # 系统架构图（PlantUML 源文件）
├── scripts/             # 辅助脚本（rotating_crawler 等）
├── tests/               # 单元测试
├── pyproject.toml          # 依赖声明（uv 管理）
├── uv.lock                 # 依赖锁定文件
├── requirements/           # pip 兼容格式（由 pyproject.toml 同步生成，非手动维护）
├── pytest.ini
└── .env.example
```

---

## LLM 降级策略

系统采用三层降级，确保 LLM 不可用时流水线不会中断：

| 层级 | 触发条件 | 行为 |
|------|---------|------|
| 网络层重试 | API 调用失败 | 最多 3 次指数退避重试（含随机抖动） |
| 模块级回退 | 重试耗尽仍失败 | 该模块填入确定性默认值（如情感分析全部标 neutral） |
| 流水线级保底 | 全链路 LLM 不可用 | 仅依赖确定性规则完成流程（如风险研判仅用基线扫描） |

| Agent | 降级时行为 |
|-------|-----------|
| Sentiment | 全部标记为 neutral（置信度 0.5） |
| Opinion | 返回占位观点阵营 |
| Risk | 仅使用触发词基线扫描，风险等级基于命中数判定 |
| Forecast | 返回保守默认值（趋势平稳，不确定性高） |
| Report（模块总结） | 返回格式化模板文本 |
| Report（综合叙述） | 返回数据填充模板 |

---

## 设计要点

### 已实现
- **证据可追溯**：所有 Agent 输出均携带 `evidence_ids`，第 7 步自动校验完整性并移除断链引用
- **LLM 降级**：三层降级策略，LLM 不可用时流水线仍可完整输出
- **风险时间敏感性**：风险研判包含时间维度（即刻/短期/长期），着眼短期舆情爆发点
- **话题相关性过滤**：预处理阶段自动识别并移除与话题无关的噪声文档
- **模块解耦**：MindSpider 通过适配器模式隔离，Agent 与数据源解耦
- **安全限额**：实时爬取限制 3 关键词 × 每平台 5 条，超时 5 分钟，关闭评论递归
- **实时计时**：WebUI 中每步显示已用时间与处理规模
- **分析历史**：侧边栏保留最近 20 次分析记录，点击可恢复查看
- **Markdown 报告导出**：支持下载完整 Markdown 格式分析报告
- **结构化日志**：所有步骤产生 AgentStepLog，含耗时、证据量、告警数量

### 当前限制
- 任务存储为内存模式（重启丢失），生产环境需替换为持久化后端
- API 不支持任务取消/删除/分页
- 趋势预测基于 LLM 推理推断而非统计建模，仅供辅助参考

---

## 致谢

本项目参考引用了 [BettaFish](https://github.com/666ghj/BettaFish) 开源项目，其 MindSpider 子模块（`MindSpider/DeepSentimentCrawling/MediaCrawler`）作为本系统数据采集基础设施的核心组件，在此表示感谢。
