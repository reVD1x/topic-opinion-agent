from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path
from typing import Callable

import streamlit as st

# Ensure `app.*` imports resolve when Streamlit runs this file as a script.
PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.common.constants import (
    MODULE_NAME_MAP,
    RISK_LEVEL_MAP,
    TIME_HORIZON_MAP,
    TREND_MAP,
    UNCERTAINTY_MAP,
    to_cn,
)
from app.schemas.report import AgentStepLog, TopicReport
from app.storage.history import clear_history, delete_history_entry, load_history, save_to_history
from app.workflow.pipeline import TopicAnalysisPipeline


st.set_page_config(
    page_title="单话题舆情分析与预测",
    page_icon="🧭",
    layout="wide",
)


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


EVIDENCE_WARNING_KEYWORDS = ["doc_id无法回溯", "证据ID无法回溯"]


def _is_evidence_warning(message: str) -> bool:
    return any(kw in message for kw in EVIDENCE_WARNING_KEYWORDS)


def _render_agent_panel(agent_logs: list[AgentStepLog]) -> None:
    """Render pipeline step cards as a compact vertical panel."""
    st.subheader("运行流水线")

    for log in agent_logs:
        icon = "⏭️" if log.status == "skipped" else "✅"
        module_cn = to_cn(MODULE_NAME_MAP, log.module)
        duration_s = f"{log.duration_ms / 1000:.1f}s" if log.duration_ms > 0 else "-"

        c_left, c_mid, c_right = st.columns([0.6, 5, 1.4], gap="small")
        with c_left:
            st.markdown(f"**{log.step}** {icon}")
        with c_mid:
            st.markdown(f"**{module_cn}** — {log.output_summary}")
        with c_right:
            st.caption(f"{duration_s} · 证据 {log.evidence_count}")

        # Show detail logs inside an expander when available
        if log.logs:
            with st.expander(f"详情 · {module_cn}", expanded=False):
                for entry in log.logs:
                    ts = entry.get("ts", "")
                    msg = entry.get("msg", "")
                    if ts:
                        st.caption(f"`{ts}` {msg}")
                    else:
                        st.caption(msg)


def _render_evidence_chain_block(warnings: list[str]) -> None:
    """Render the evidence chain verification block."""
    evidence_warnings = [w for w in warnings if _is_evidence_warning(w)]

    st.subheader("证据链校验")
    if evidence_warnings:
        st.warning(f"发现 {len(evidence_warnings)} 个证据断链")
        for w in evidence_warnings:
            st.markdown(f"- {w}")
    else:
        nodes = ["情感分析", "观点抽取", "风险研判", "趋势预测"]
        st.success("全部校验通过 — " + "、".join(nodes) + " 节点证据链完整")


def _render_risk(level: str, triggers: list[str], evidence_ids: list[str]) -> None:
    level_cn = to_cn(RISK_LEVEL_MAP, level)
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
    col1.metric("趋势判断", to_cn(TREND_MAP, fc.trend_judgement))
    col2.metric("时间窗", to_cn(TIME_HORIZON_MAP, fc.time_horizon))
    col3.metric("不确定性", to_cn(UNCERTAINTY_MAP, fc.uncertainty))

    st.write("关键假设")
    for item in fc.assumptions:
        st.markdown(f"- {item}")

    st.write("反事实")
    for item in fc.counterfactuals:
        st.markdown(f"- {item}")

    st.write("关键证据ID")
    if fc.evidence_ids:
        for doc_id in fc.evidence_ids[:10]:
            st.code(doc_id)
    else:
        st.write("- 无")

    if fc.reasoning:
        with st.expander("推理过程", expanded=False):
            st.markdown(fc.reasoning)

    st.caption(fc.disclaimer)


def _render_report(report: TopicReport, warnings: list[str]) -> None:
    st.subheader("分析结果")

    if report.narrative_summary:
        st.markdown("### 综合总结")
        st.markdown(report.narrative_summary)
        st.divider()

    st.write(report.overview)

    for w in warnings:
        if _is_evidence_warning(w):
            continue  # evidence warnings rendered in dedicated block
        st.warning(f"提示: {_format_warning(w)}")

    c1, c2, c3 = st.columns(3)
    c1.metric("正向", report.sentiment_summary.get("positive", 0))
    c2.metric("中性", report.sentiment_summary.get("neutral", 0))
    c3.metric("负向", report.sentiment_summary.get("negative", 0))

    tab_summary, tab_overview, tab_opinion, tab_risk, tab_forecast, tab_module, tab_evidence, tab_raw = st.tabs(
        ["综合总结", "来源与情感", "观点阵营", "风险判断", "趋势预测", "模块总结", "证据列表", "原始数据"]
    )

    with tab_summary:
        if report.narrative_summary:
            st.markdown(report.narrative_summary)
        else:
            st.info("暂无综合总结。")

    with tab_overview:
        st.markdown("### 来源分布")
        st.bar_chart(report.source_distribution)
        st.markdown("### 情感明细（前 200 条）")
        st.dataframe([s.model_dump() for s in report.sentiment_items[:200]], use_container_width=True)

    with tab_opinion:
        def _render_opinion_block(title: str, items) -> None:
            st.markdown(f"### {title}")
            if not items:
                st.write("- 无")
                return
            for i, op in enumerate(items):
                ids = ", ".join(op.evidence_ids[:3])
                st.markdown(f"- {op.content}  `[{ids}]`")
                if getattr(op, "reasoning", ""):
                    with st.expander(f"推理过程", expanded=False):
                        st.caption(op.reasoning)

        _render_opinion_block("支持观点", report.opinion_blocks.supports)
        _render_opinion_block("反对观点", report.opinion_blocks.opposes)
        _render_opinion_block("中立观察", report.opinion_blocks.neutrals)
        _render_opinion_block("争议焦点", report.opinion_blocks.controversy_points)

    with tab_risk:
        _render_risk(
            level=report.risk.risk_level,
            triggers=report.risk.triggers,
            evidence_ids=report.risk.evidence_ids,
        )

    with tab_forecast:
        _render_forecast(report)

    with tab_module:
        if report.module_summaries:
            for module_name, module_summary in report.module_summaries.items():
                st.markdown(f"### {to_cn(MODULE_NAME_MAP, module_name)}")
                st.write(module_summary)
        else:
            st.info("暂无模块总结。")

    with tab_evidence:
        st.dataframe([e.model_dump() for e in report.evidence_list], use_container_width=True)

    with tab_raw:
        st.download_button(
            label="下载 Markdown 报告",
            data=report.markdown,
            file_name=f"report_{report.topic_id}.md",
            mime="text/markdown",
        )
        with st.expander("Markdown 报告", expanded=True):
            st.markdown(report.markdown)
        with st.expander("结构化数据（JSON）", expanded=False):
            st.code(json.dumps(report.model_dump(), ensure_ascii=False, indent=2), language="json")


def _run_analysis(
    topic_id: str,
    target_date: date | None,
    enable_forecast: bool,
    use_external: bool,
    use_mindspider: bool,
    progress_callback: Callable[[str], None] | None = None,
) -> tuple[TopicReport, list[str], str, list[AgentStepLog]]:
    pipeline = TopicAnalysisPipeline()
    return pipeline.run(
        topic_id=topic_id,
        target_date=target_date,
        enable_forecast=enable_forecast,
        use_external=use_external,
        use_mindspider=use_mindspider,
        progress_callback=progress_callback,
    )


def _sanitize_input(value: str) -> str:
    """Remove SQL special characters for safety. Not a full sanitizer."""
    for ch in ("'", '"', ";", "--", "/*", "*/", "\\"):
        value = value.replace(ch, "")
    return value


def main() -> None:
    st.title("单一话题舆情分析预测台")
    st.caption("输入话题关键词；若数据库无精确命中，系统会自动匹配最接近话题。")

    with st.sidebar:
        st.header("分析参数")
        topic_id = st.text_input(
            "话题关键词",
            max_chars=200,
            placeholder="例如：某品牌新品发布",
        )
        enable_forecast = st.checkbox("启用趋势预测", value=True)
        use_external = st.checkbox("启用外部检索（博查/Tavily）", value=True)
        use_mindspider = st.checkbox(
            "启用实时爬取（MindSpider · 小红书）",
            value=False,
            help="实时搜索小红书获取相关帖文。限制：最多 3 个关键词 × 5 条笔记，不抓评论，预计 2-3 分钟。",
        )
        if "analysis_triggered" not in st.session_state:
            st.session_state["analysis_triggered"] = False

        run_clicked = st.button(
            "开始分析",
            type="primary",
            use_container_width=True,
            disabled=st.session_state["analysis_triggered"],
        )

        if run_clicked:
            cleaned = _sanitize_input(topic_id.strip())
            if not cleaned:
                st.error("请先输入话题关键词。")
            else:
                st.session_state["analysis_triggered"] = True
                st.rerun()

        # ── History ────────────────────────────────────────────────
        st.divider()
        st.subheader("最近分析记录")
        history = load_history()
        if history:
            if st.button("清空全部记录", type="secondary", use_container_width=True):
                clear_history()
                st.rerun()
            for i, entry in enumerate(history[:10]):
                ts = entry.get("timestamp", "")[:16]
                tid = entry.get("topic_id", "?")
                risk_lvl = entry.get("risk_level", "?")
                risk_cn = to_cn(RISK_LEVEL_MAP, risk_lvl)
                col_btn, col_del = st.columns([9, 1], gap="small")
                with col_btn:
                    if st.button(f"{ts} — {tid} (风险:{risk_cn})", key=f"hist_{i}"):
                        rpt_data = entry.get("report", {})
                        if rpt_data:
                            try:
                                restored_report = TopicReport(**rpt_data)
                                st.session_state["report"] = restored_report
                                st.session_state["warnings"] = entry.get("warnings", [])
                                st.session_state["agent_logs"] = []
                                st.rerun()
                            except Exception:
                                st.warning("恢复历史记录失败，数据格式已变更。")
                with col_del:
                    if st.button("✕", key=f"del_{i}", help="删除此记录"):
                        delete_history_entry(i)
                        st.rerun()
        else:
            st.caption("暂无历史记录")

    if "report" not in st.session_state:
        st.session_state["report"] = None
        st.session_state["warnings"] = []
        st.session_state["agent_logs"] = []
        st.session_state["mindspider_log"] = ""

    if st.session_state.get("analysis_triggered"):
        with st.status("准备分析…", expanded=True) as status:
            try:
                def _update_progress(msg: str) -> None:
                    status.update(label=msg)

                cleaned = _sanitize_input(topic_id.strip())
                report, warnings, mindspider_log, agent_logs = _run_analysis(
                    topic_id=cleaned,
                    target_date=None,
                    enable_forecast=enable_forecast,
                    use_external=use_external,
                    use_mindspider=use_mindspider,
                    progress_callback=_update_progress,
                )
                st.session_state["report"] = report
                st.session_state["warnings"] = warnings
                st.session_state["agent_logs"] = agent_logs
                st.session_state["mindspider_log"] = mindspider_log
                save_to_history(report, agent_logs)
                status.update(label="分析完成", state="complete", expanded=False)
            except Exception as exc:
                st.session_state["report"] = None
                st.session_state["warnings"] = []
                st.session_state["agent_logs"] = []
                st.session_state["mindspider_log"] = ""
                status.update(label="分析失败", state="error")
                st.exception(exc)
            finally:
                st.session_state["analysis_triggered"] = False
                st.rerun()

    if st.session_state["report"] is not None:
        if st.session_state["agent_logs"]:
            _render_agent_panel(st.session_state["agent_logs"])
            _render_evidence_chain_block(st.session_state["warnings"])
            st.divider()
        if st.session_state.get("mindspider_log"):
            with st.expander("MindSpider 爬取日志", expanded=False):
                st.code(st.session_state["mindspider_log"], language="text")
        _render_report(st.session_state["report"], st.session_state["warnings"])
    else:
        st.info("请在左侧设置参数并点击'开始分析'。")


if __name__ == "__main__":
    main()
