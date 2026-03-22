from __future__ import annotations

from datetime import date

from langgraph.graph import END, StateGraph

from app.agents.forecast_agent import ForecastAgent
from app.agents.opinion_agent import OpinionAgent
from app.agents.preprocess_agent import PreprocessAgent
from app.agents.report_agent import ReportAgent
from app.agents.risk_agent import RiskAgent
from app.agents.sentiment_agent import SentimentAgent
from app.data.external_bocha import ExternalBocha
from app.data.external_tavily import ExternalTavily
from app.data.fusion import DataFusionService
from app.data.pg_repository import PgRepository
from app.llm.gateway import LLMGateway
from app.schemas.task import TopicAnalysisRequest
from app.storage.db import session_scope
from app.workflow.state import AgentResult, GraphState


class TopicWorkflowGraph:
    def __init__(self) -> None:
        self.llm = LLMGateway()
        self.preprocess_agent = PreprocessAgent()
        self.sentiment_agent = SentimentAgent(self.llm)
        self.opinion_agent = OpinionAgent(self.llm)
        self.risk_agent = RiskAgent(self.llm)
        self.forecast_agent = ForecastAgent(self.llm)
        self.report_agent = ReportAgent(self.llm)

        self.bocha = ExternalBocha()
        self.tavily = ExternalTavily()
        self.fusion = DataFusionService()

    def compile(self):
        graph = StateGraph(GraphState)
        graph.add_node("collect", self.collect)
        graph.add_node("preprocess", self.preprocess)
        graph.add_node("analyze", self.analyze)
        graph.add_node("report", self.report)

        graph.set_entry_point("collect")
        graph.add_edge("collect", "preprocess")
        graph.add_edge("preprocess", "analyze")
        graph.add_edge("analyze", "report")
        graph.add_edge("report", END)
        return graph.compile()

    def collect(self, state: GraphState) -> GraphState:
        # Date filtering is intentionally disabled: always search across all time ranges.
        state.target_date = None
        search_query = state.topic_id
        with session_scope() as session:
            repo = PgRepository(session)
            resolved = repo.resolve_topic_key(state.topic_id, state.target_date)
            if resolved:
                if resolved.matched_by != "exact" or resolved.matched_value != state.topic_id:
                    state.warnings.append(
                        f"auto_matched: 输入[{state.topic_id}] -> 匹配[{resolved.matched_value}] (score={resolved.score:.2f})"
                    )

                state.topic_id = resolved.resolved_key
                search_query = resolved.topic_name or resolved.matched_value or state.topic_id
                state.docs = repo.load_topic_evidence(state.topic_id, state.target_date)
            else:
                state.warnings.append(f"auto_matched: 输入[{state.topic_id}]未命中数据库话题，切换为外部检索直连模式")

        try:
            state.docs.extend(self.bocha.search(state.topic_id, query=search_query, limit=8))
        except Exception as exc:
            state.warnings.append(f"bocha_failed:{exc}")
        try:
            state.docs.extend(self.tavily.search(state.topic_id, query=search_query, limit=8))
        except Exception as exc:
            state.warnings.append(f"tavily_failed:{exc}")

        if not state.docs:
            state.errors.append(f"未找到可用于分析的证据数据: {state.topic_id}")
            return state

        state.docs = self.fusion.merge_and_dedup(state.docs)
        state.results.append(AgentResult(name="collect", success=True, payload={"docs": len(state.docs)}))
        return state

    def preprocess(self, state: GraphState) -> GraphState:
        state.docs = self.preprocess_agent.run(state.docs)
        state.results.append(AgentResult(name="preprocess", success=True, payload={"docs": len(state.docs)}))
        return state

    def analyze(self, state: GraphState) -> GraphState:
        sentiments = self.sentiment_agent.run(state.docs)
        opinions = self.opinion_agent.run(state.topic_id, state.docs)
        risk = self.risk_agent.run(state.docs, opinions)
        state.results.append(
            AgentResult(
                name="analyze",
                success=True,
                payload={
                    "sentiment_count": len(sentiments),
                    "risk_level": risk.risk_level,
                },
            )
        )
        return state

    def report(self, state: GraphState) -> GraphState:
        state.results.append(AgentResult(name="report", success=True))
        return state


def build_initial_state(task_id: str, request: TopicAnalysisRequest) -> GraphState:
    return GraphState(
        task_id=task_id,
        topic_id=request.topic_id,
        target_date=request.target_date if isinstance(request.target_date, date) else None,
    )
