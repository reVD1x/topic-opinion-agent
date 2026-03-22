from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

import streamlit as st

# Ensure `app.*` imports resolve when Streamlit runs this file as a script.
PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.schemas.report import TopicReport
from app.workflow.pipeline import TopicAnalysisPipeline


st.set_page_config(
    page_title="单话题舆情分析与预测",
    page_icon="🧭",
    layout="wide",
)


RISK_LEVEL_MAP = {
    "high": "高",
    "medium": "中",
    "low": "低",
}

TREND_MAP = {
    "rise": "上升",
    "flat": "平稳",
    "fall": "下降",
}

UNCERTAINTY_MAP = {
    "high": "高",
    "medium": "中",
    "low": "低",
}

TIME_HORIZON_MAP = {
    "24h": "24 小时",
    "72h": "72 小时",
}

MODULE_NAME_MAP = {
    "collect": "数据采集",
    "preprocess": "数据预处理",
    "sentiment": "情感分析",
    "opinion": "观点抽取",
    "risk": "风险研判",
    "forecast": "趋势预测",
    "report": "报告生成",
}


def _to_cn(mapping: dict[str, str], value: str) -> str:
    return mapping.get(value, value)


def _format_warning(message: str) -> str:
    if message.startswith("auto_matched:"):
        detail = message.split(":", 1)[1].strip()
        return f"自动匹配提示：{detail}"
    if message.startswith("bocha_failed:"):
        detail = message.split(":", 1)[1].strip()
        return f"博查检索失败：{detail}"
    if message.startswith("tavily_failed:"):
        detail = message.split(":", 1)[1].strip()
        return f"Tavily 检索失败：{detail}"
    return message


def _render_risk(level: str, triggers: list[str], evidence_ids: list[str]) -> None:
    level_cn = _to_cn(RISK_LEVEL_MAP, level)
    if level == "high":
        st.error(f"风险等级: {level_cn}")
    elif level == "medium":
        st.warning(f"风险等级: {level_cn}")
    else:
        st.success(f"风险等级: {level_cn}")

    st.write("触发因素")
    if triggers:
        for item in triggers:
            st.markdown(f"- {item}")
    else:
        st.write("- 无")

    with st.expander("证据ID（风险判断追溯）", expanded=False):
        if evidence_ids:
            for doc_id in evidence_ids:
                st.code(doc_id)
        else:
            st.write("暂无")


def _render_forecast(report: TopicReport) -> None:
    if not report.forecast:
        st.info("未启用预测，或暂无可用预测结果。")
        return

    fc = report.forecast
    col1, col2, col3 = st.columns(3)
    col1.metric("趋势判断", _to_cn(TREND_MAP, fc.trend_judgement))
    col2.metric("时间窗", _to_cn(TIME_HORIZON_MAP, fc.time_horizon))
    col3.metric("不确定性", _to_cn(UNCERTAINTY_MAP, fc.uncertainty))

    st.write("关键假设")
    for item in fc.assumptions:
        st.markdown(f"- {item}")

    st.write("反事实")
    for item in fc.counterfactuals:
        st.markdown(f"- {item}")

    st.caption(fc.disclaimer)


def _render_report(report: TopicReport, warnings: list[str]) -> None:
    st.subheader("分析结果")
    st.write(report.overview)

    if warnings:
        st.warning("\n".join([f"提示: {_format_warning(w)}" for w in warnings]))

    c1, c2, c3 = st.columns(3)
    c1.metric("正向", report.sentiment_summary.get("positive", 0))
    c2.metric("中性", report.sentiment_summary.get("neutral", 0))
    c3.metric("负向", report.sentiment_summary.get("negative", 0))

    tab_overview, tab_opinion, tab_risk, tab_forecast, tab_summary, tab_evidence, tab_raw = st.tabs(
        ["来源与情感", "观点阵营", "风险判断", "趋势预测", "模块总结", "证据列表", "原始数据"]
    )

    with tab_overview:
        st.markdown("### 来源分布")
        st.bar_chart(report.source_distribution)
        st.markdown("### 情感明细（前 200 条）")
        st.dataframe([s.model_dump() for s in report.sentiment_items[:200]], use_container_width=True)

    with tab_opinion:
        st.markdown("### 支持观点")
        for item in report.opinion_blocks.supports:
            st.markdown(f"- {item}")

        st.markdown("### 反对观点")
        for item in report.opinion_blocks.opposes:
            st.markdown(f"- {item}")

        st.markdown("### 中立观察")
        for item in report.opinion_blocks.neutrals:
            st.markdown(f"- {item}")

        st.markdown("### 争议焦点")
        for item in report.opinion_blocks.controversy_points:
            st.markdown(f"- {item}")

    with tab_risk:
        _render_risk(
            level=report.risk.risk_level,
            triggers=report.risk.triggers,
            evidence_ids=report.risk.evidence_ids,
        )

    with tab_forecast:
        _render_forecast(report)

    with tab_summary:
        if report.module_summaries:
            for module_name, module_summary in report.module_summaries.items():
                st.markdown(f"### {_to_cn(MODULE_NAME_MAP, module_name)}")
                st.write(module_summary)
        else:
            st.info("暂无模块总结。")

    with tab_evidence:
        st.dataframe([e.model_dump() for e in report.evidence_list], use_container_width=True)

    with tab_raw:
        with st.expander("Markdown 报告", expanded=True):
            st.markdown(report.markdown)
        with st.expander("结构化数据（JSON）", expanded=False):
            st.code(json.dumps(report.model_dump(), ensure_ascii=False, indent=2), language="json")


def _run_analysis(
    topic_id: str,
    target_date: date | None,
    enable_forecast: bool,
    use_external: bool,
) -> tuple[TopicReport, list[str]]:
    pipeline = TopicAnalysisPipeline()
    return pipeline.run(
        topic_id=topic_id,
        target_date=target_date,
        enable_forecast=enable_forecast,
        use_external=use_external,
    )


def main() -> None:
    st.title("单一话题舆情分析预测台")
    st.caption("输入话题关键词；若数据库无精确命中，系统会自动匹配最接近话题。")

    with st.sidebar:
        st.header("分析参数")
        topic_id = st.text_input("话题关键词", placeholder="例如：某品牌新品发布")
        enable_forecast = st.checkbox("启用趋势预测", value=True)
        use_external = st.checkbox("启用外部检索（博查/Tavily）", value=True)
        run_clicked = st.button("开始分析", type="primary", use_container_width=True)

    if "report" not in st.session_state:
        st.session_state["report"] = None
        st.session_state["warnings"] = []

    if run_clicked:
        if not topic_id.strip():
            st.error("请先输入话题关键词。")
        else:
            with st.spinner("正在分析中，请稍候..."):
                try:
                    report, warnings = _run_analysis(
                        topic_id=topic_id.strip(),
                        target_date=None,
                        enable_forecast=enable_forecast,
                        use_external=use_external,
                    )
                    st.session_state["report"] = report
                    st.session_state["warnings"] = warnings
                except Exception as exc:
                    st.session_state["report"] = None
                    st.session_state["warnings"] = []
                    st.exception(exc)

    if st.session_state["report"] is not None:
        _render_report(st.session_state["report"], st.session_state["warnings"])
    else:
        st.info("请在左侧设置参数并点击'开始分析'。")


if __name__ == "__main__":
    main()
