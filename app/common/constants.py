from __future__ import annotations

# ── Label / display mappings ──────────────────────────────────────────
RISK_LEVEL_MAP = {"high": "高", "medium": "中", "low": "低"}
TREND_MAP = {"rise": "上升", "flat": "平稳", "fall": "下降"}
UNCERTAINTY_MAP = {"high": "高", "medium": "中", "low": "低"}
TIME_HORIZON_MAP = {"24h": "24 小时", "72h": "72 小时"}
MODULE_NAME_MAP = {
    "collect": "数据采集",
    "preprocess": "数据预处理",
    "sentiment": "情感分析",
    "opinion": "观点抽取",
    "risk": "风险研判",
    "forecast": "趋势预测",
    "evidence_chain": "证据链校验",
    "report": "报告生成",
}


def to_cn(mapping: dict[str, str], value: str) -> str:
    return mapping.get(value, value)


# ── Pipeline parameter constants ──────────────────────────────────────
CONTENT_TRUNCATE_LEN = 2000
DEDUP_KEY_LEN = 120
SENTIMENT_SNIPPET_LEN = 300
SENTIMENT_MAX_DOCS = 200
OPINION_MAX_DOCS = 200
OPINION_SNIPPET_LEN = 200
RISK_SAMPLE_DOCS = 200
RISK_SNIPPET_LEN = 120
FORECAST_MAX_DOCS = 200
FORECAST_SNIPPET_LEN = 200
EVIDENCE_MAX_ITEMS = 200
EXTERNAL_SEARCH_LIMIT = 8

# ── Risk analysis ─────────────────────────────────────────────────────
TRIGGER_WORDS = ["谣言", "冲突", "抵制", "维权", "事故", "违法", "伤亡"]
RISK_HIGH_THRESHOLD = 8
RISK_MEDIUM_THRESHOLD = 3

# ── PG topic matching ─────────────────────────────────────────────────
SIMILARITY_EXACT_MIN = 0.75
SIMILARITY_PARTIAL_MIN = 0.52
