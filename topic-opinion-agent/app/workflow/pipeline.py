from __future__ import annotations

from datetime import date

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
from app.schemas.report import TopicReport
from app.storage.db import session_scope


class TopicAnalysisPipeline:
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

    def run(
        self,
        topic_id: str,
        target_date: date | None,
        enable_forecast: bool,
        use_external: bool,
    ) -> tuple[TopicReport, list[str]]:
        # Date filtering is intentionally disabled: always search across all time ranges.
        target_date = None
        warnings: list[str] = []
        analysis_topic_id = topic_id
        external_query = topic_id
        docs = []

        with session_scope() as session:
            repo = PgRepository(session)
            resolved = repo.resolve_topic_key(topic_id, target_date)
            if not resolved:
                if not use_external:
                    raise ValueError(f"未找到与输入关键词匹配的话题: {topic_id}")
                warnings.append(f"auto_matched: 输入[{topic_id}]未命中数据库话题，切换为外部检索直连模式")
            else:
                analysis_topic_id = resolved.resolved_key
                external_query = resolved.topic_name or resolved.matched_value or topic_id
                docs = repo.load_topic_evidence(analysis_topic_id, target_date)

                if resolved.matched_by != "exact" or resolved.matched_value != topic_id:
                    warnings.append(
                        f"auto_matched: 输入[{topic_id}] -> 匹配[{resolved.matched_value}] (score={resolved.score:.2f})"
                    )

        if use_external:
            try:
                docs.extend(self.bocha.search(analysis_topic_id, query=external_query, limit=8))
            except Exception as exc:
                warnings.append(f"bocha_failed:{exc}")
            try:
                docs.extend(self.tavily.search(analysis_topic_id, query=external_query, limit=8))
            except Exception as exc:
                warnings.append(f"tavily_failed:{exc}")

        if not docs:
            raise ValueError(f"未找到可用于分析的证据数据: {topic_id}")

        docs = self.fusion.merge_and_dedup(docs)
        docs = self.preprocess_agent.run(docs)

        sentiments = self.sentiment_agent.run(docs)
        opinions = self.opinion_agent.run(analysis_topic_id, docs)
        risk = self.risk_agent.run(docs, opinions)
        forecast = self.forecast_agent.run(docs) if enable_forecast else None

        report = self.report_agent.run(
            topic_id=analysis_topic_id,
            docs=docs,
            source_distribution=self.fusion.source_distribution(docs),
            sentiments=sentiments,
            opinions=opinions,
            risk=risk,
            forecast=forecast,
        )

        return report, warnings
