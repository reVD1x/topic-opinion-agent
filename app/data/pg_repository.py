from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from difflib import SequenceMatcher
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.common.config import settings
from app.common.constants import SIMILARITY_EXACT_MIN, SIMILARITY_PARTIAL_MIN
from app.schemas.doc import UnifiedDoc


@dataclass(frozen=True)
class TopicResolution:
    query: str
    topic_id: str
    topic_name: str | None
    matched_value: str
    score: float
    matched_by: str

    @property
    def resolved_key(self) -> str:
        return self.topic_id or (self.topic_name or self.query)


class PgRepository:
    def __init__(self, session: Session) -> None:
        self._session = session
        self._platform_content_table = settings.table_platform_content.strip()
        self._platform_tables = [
            t.strip() for t in settings.table_platforms_csv.split(",") if t.strip()
        ]

    def topic_exists(self, topic_key: str, target_date: date | None) -> bool:
        return self.resolve_topic_key(topic_key, target_date) is not None

    def resolve_topic_key(self, topic_key: str, target_date: date | None) -> TopicResolution | None:
        query = (topic_key or "").strip()
        if not query:
            return None

        exact_row = self._query_exact_topic(query, target_date)
        if exact_row:
            return self._to_resolution(query, exact_row, score=1.0, matched_by="exact")

        partial_rows = self._query_partial_topics(query, target_date, limit=120)
        if partial_rows:
            best = self._pick_best_candidate(query, partial_rows)
            if best:
                return best

        keyword_rows = self._query_topics_by_keyword(query, target_date, limit=30)
        if keyword_rows:
            kw_match = self._pick_keyword_match(query, keyword_rows)
            if kw_match:
                return kw_match

        fallback_rows = self._query_recent_topics(target_date, limit=240)
        best = self._pick_best_candidate(query, fallback_rows)
        if best and best.score >= 0.45:
            return best

        # If a date filter is enabled, retry globally to avoid missing valid topics
        # that exist on other dates.
        if target_date is not None:
            exact_row = self._query_exact_topic(query, None)
            if exact_row:
                return self._to_resolution(query, exact_row, score=0.95, matched_by="exact_any_date")

            partial_rows = self._query_partial_topics(query, None, limit=180)
            if partial_rows:
                best = self._pick_best_candidate(query, partial_rows)
                if best:
                    return best

            global_rows = self._query_recent_topics(None, limit=320)
            best = self._pick_best_candidate(query, global_rows)
            if best and best.score >= 0.42:
                return best
        return None

    def load_topic_evidence(
        self,
        topic_key: str,
        target_date: date | None,
        fallback_keywords: list[str] | None = None,
    ) -> list[UnifiedDoc]:
        news_docs = self._load_news_docs(topic_key, target_date)
        platform_docs = self._load_platform_docs(topic_key, target_date)

        # Always try keyword fallback for platform data when exact topic match
        # yields nothing — platform tables store source_keyword not topic_id.
        if not platform_docs and fallback_keywords:
            platform_docs = self._load_platform_docs_by_keywords(fallback_keywords, limit=200)

        docs = news_docs + platform_docs

        # Fallback for news: only when nothing found at all
        if not news_docs and fallback_keywords:
            docs += self._load_news_docs_by_keywords(fallback_keywords, limit=200)

        return docs

    def get_topic_keywords(self, topic_id: str) -> list[str]:
        """Extract keywords from a topic's keywords JSON field."""
        import json as _json

        sql = text(
            f"""
            SELECT to_jsonb(t) ->> 'keywords' AS keywords
            FROM {settings.table_daily_topics} t
            WHERE to_jsonb(t) ->> :topic_id_col = :topic_id
            LIMIT 1
            """
        )
        row = self._session.execute(
            sql,
            {
                "topic_id_col": settings.topic_id_column,
                "topic_id": topic_id,
            },
        ).mappings().first()
        if not row or not row.get("keywords"):
            return []
        try:
            parsed = _json.loads(row["keywords"])
            if isinstance(parsed, list):
                return [str(k).strip() for k in parsed if str(k).strip()]
        except (ValueError, TypeError):
            pass
        return []

    def load_crawling_tasks_snapshot(self) -> dict[str, int]:
        sql = text(
            f"""
            SELECT COALESCE(to_jsonb(c) ->> 'status', 'unknown') AS status, COUNT(*) AS cnt
            FROM {settings.table_crawling_tasks} c
            GROUP BY 1
            """
        )
        rows = self._session.execute(sql).mappings()
        return {str(row["status"]): int(row["cnt"]) for row in rows}

    def _query_exact_topic(self, topic_key: str, target_date: date | None) -> dict[str, Any] | None:
        date_filter = (
            f"AND (to_jsonb(t) ->> '{settings.topic_date_column}')::date = :target_date"
            if target_date
            else ""
        )
        sql = text(
            f"""
            SELECT
                to_jsonb(t) ->> :topic_id_col AS topic_id,
                to_jsonb(t) ->> :topic_name_col AS topic_name
            FROM {settings.table_daily_topics} t
            WHERE (
                to_jsonb(t) ->> :topic_id_col = :topic_key
                OR to_jsonb(t) ->> :topic_name_col = :topic_key
            )
            {date_filter}
            LIMIT 1
            """
        )
        row = self._session.execute(
            sql,
            {
                "topic_key": topic_key,
                "target_date": target_date,
                "topic_id_col": settings.topic_id_column,
                "topic_name_col": settings.topic_name_column,
            },
        ).mappings().first()
        return dict(row) if row else None

    def _query_partial_topics(self, topic_key: str, target_date: date | None, limit: int) -> list[dict[str, Any]]:
        date_filter = (
            f"AND (to_jsonb(t) ->> '{settings.topic_date_column}')::date = :target_date"
            if target_date
            else ""
        )
        sql = text(
            f"""
            SELECT DISTINCT
                to_jsonb(t) ->> :topic_id_col AS topic_id,
                to_jsonb(t) ->> :topic_name_col AS topic_name
            FROM {settings.table_daily_topics} t
            WHERE (
                LOWER(COALESCE(to_jsonb(t) ->> :topic_id_col, '')) LIKE :like_pattern
                OR LOWER(COALESCE(to_jsonb(t) ->> :topic_name_col, '')) LIKE :like_pattern
            )
            {date_filter}
            LIMIT :limit
            """
        )
        rows = self._session.execute(
            sql,
            {
                "target_date": target_date,
                "topic_id_col": settings.topic_id_column,
                "topic_name_col": settings.topic_name_column,
                "like_pattern": f"%{topic_key.lower()}%",
                "limit": limit,
            },
        ).mappings()
        return [dict(row) for row in rows]

    def _query_topics_by_keyword(
        self, topic_key: str, target_date: date | None, limit: int
    ) -> list[dict[str, Any]]:
        date_filter = (
            f"AND (to_jsonb(t) ->> '{settings.topic_date_column}')::date = :target_date"
            if target_date
            else ""
        )
        sql = text(
            f"""
            SELECT DISTINCT
                to_jsonb(t) ->> :topic_id_col AS topic_id,
                to_jsonb(t) ->> :topic_name_col AS topic_name
            FROM {settings.table_daily_topics} t
            WHERE (
                LOWER(COALESCE(to_jsonb(t) ->> 'keywords', '')) LIKE :like_pattern
                OR LOWER(COALESCE(to_jsonb(t) ->> 'topic_description', '')) LIKE :like_pattern
            )
            {date_filter}
            LIMIT :limit
            """
        )
        rows = self._session.execute(
            sql,
            {
                "target_date": target_date,
                "topic_id_col": settings.topic_id_column,
                "topic_name_col": settings.topic_name_column,
                "like_pattern": f"%{topic_key.lower()}%",
                "limit": limit,
            },
        ).mappings()
        return [dict(row) for row in rows]

    def _query_recent_topics(self, target_date: date | None, limit: int) -> list[dict[str, Any]]:
        date_filter = (
            f"WHERE (to_jsonb(t) ->> '{settings.topic_date_column}')::date = :target_date"
            if target_date
            else ""
        )
        sql = text(
            f"""
            SELECT DISTINCT
                to_jsonb(t) ->> :topic_id_col AS topic_id,
                to_jsonb(t) ->> :topic_name_col AS topic_name
            FROM {settings.table_daily_topics} t
            {date_filter}
            LIMIT :limit
            """
        )
        rows = self._session.execute(
            sql,
            {
                "target_date": target_date,
                "topic_id_col": settings.topic_id_column,
                "topic_name_col": settings.topic_name_column,
                "limit": limit,
            },
        ).mappings()
        return [dict(row) for row in rows]

    def _pick_best_candidate(self, query: str, rows: list[dict[str, Any]]) -> TopicResolution | None:
        best: TopicResolution | None = None
        for row in rows:
            topic_id = str(row.get("topic_id") or "").strip()
            topic_name_raw = row.get("topic_name")
            topic_name = str(topic_name_raw).strip() if topic_name_raw else None
            if not topic_id and not topic_name:
                continue

            id_score = self._similarity_score(query, topic_id)
            name_score = self._similarity_score(query, topic_name or "")
            if id_score >= name_score:
                matched_value = topic_id
                score = id_score
            else:
                matched_value = topic_name or topic_id
                score = name_score

            if score < SIMILARITY_PARTIAL_MIN:
                continue

            resolution = TopicResolution(
                query=query,
                topic_id=topic_id or (topic_name or query),
                topic_name=topic_name,
                matched_value=matched_value,
                score=score,
                matched_by="partial" if score >= SIMILARITY_EXACT_MIN else "similarity",
            )
            if not best or resolution.score > best.score:
                best = resolution
        return best

    @staticmethod
    def _pick_keyword_match(query: str, rows: list[dict[str, Any]]) -> TopicResolution | None:
        """Pick the first keyword-matched row with a fixed score, since
        the match was on content (keywords/description), not on topic_id/name
        string similarity."""
        if not rows:
            return None
        row = rows[0]
        topic_id = str(row.get("topic_id") or "").strip()
        topic_name_raw = row.get("topic_name")
        topic_name = str(topic_name_raw).strip() if topic_name_raw else None
        if not topic_id and not topic_name:
            return None
        return TopicResolution(
            query=query,
            topic_id=topic_id or (topic_name or query),
            topic_name=topic_name,
            matched_value=query,
            score=0.50,
            matched_by="keyword",
        )

    @staticmethod
    def _similarity_score(query: str, candidate: str) -> float:
        q = "".join(query.lower().split())
        c = "".join(candidate.lower().split())
        if not q or not c:
            return 0.0
        if q == c:
            return 1.0
        if q in c or c in q:
            return 0.9
        return SequenceMatcher(None, q, c).ratio()

    @staticmethod
    def _to_resolution(
        query: str,
        row: dict[str, Any],
        score: float,
        matched_by: str,
    ) -> TopicResolution:
        topic_id = str(row.get("topic_id") or "").strip()
        topic_name_raw = row.get("topic_name")
        topic_name = str(topic_name_raw).strip() if topic_name_raw else None
        if not topic_id and topic_name:
            topic_id = topic_name
        return TopicResolution(
            query=query,
            topic_id=topic_id,
            topic_name=topic_name,
            matched_value=topic_name or topic_id,
            score=score,
            matched_by=matched_by,
        )

    def _load_news_docs(self, topic_key: str, target_date: date | None) -> list[UnifiedDoc]:
        date_filter = (
            f"AND (to_jsonb(t) ->> '{settings.topic_date_column}')::date = :target_date"
            if target_date
            else ""
        )
        sql = text(
            f"""
            SELECT
                COALESCE(to_jsonb(n) ->> 'news_id', to_jsonb(n) ->> 'id') AS raw_id,
                to_jsonb(n) ->> 'title' AS title,
                COALESCE(to_jsonb(n) ->> 'content', to_jsonb(n) ->> 'description', '') AS content,
                COALESCE(to_jsonb(n) ->> 'publish_time', to_jsonb(n) ->> 'created_at') AS publish_time,
                COALESCE(to_jsonb(n) ->> 'url', to_jsonb(n) ->> 'link') AS url,
                to_jsonb(n) ->> 'author' AS author,
                COALESCE(to_jsonb(n) ->> 'source_name', to_jsonb(n) ->> 'platform') AS source_name,
                COALESCE(to_jsonb(r) ->> 'relevance_score', to_jsonb(r) ->> 'score') AS relevance_score,
                COALESCE(to_jsonb(n) ->> 'rank', '0') AS rank_no
            FROM {settings.table_daily_topics} t
            JOIN {settings.table_topic_news_relation} r
                ON to_jsonb(t) ->> :topic_id_col = to_jsonb(r) ->> 'topic_id'
            JOIN {settings.table_daily_news} n
                ON to_jsonb(r) ->> 'news_id' = COALESCE(to_jsonb(n) ->> 'news_id', to_jsonb(n) ->> 'id')
            WHERE (
                to_jsonb(t) ->> :topic_id_col = :topic_key
                OR to_jsonb(t) ->> :topic_name_col = :topic_key
            )
            {date_filter}
            """
        )
        rows = self._session.execute(
            sql,
            {
                "topic_key": topic_key,
                "target_date": target_date,
                "topic_id_col": settings.topic_id_column,
                "topic_name_col": settings.topic_name_column,
            },
        ).mappings()
        return [self._to_news_doc(topic_key, row) for row in rows]

    def _load_platform_docs(self, topic_key: str, target_date: date | None) -> list[UnifiedDoc]:
        if self._platform_content_table and self._table_exists(self._platform_content_table):
            return self._load_platform_docs_from_single_table(topic_key, target_date)

        return self._load_platform_docs_from_legacy_tables(topic_key, target_date)

    def _load_platform_docs_from_single_table(
        self,
        topic_key: str,
        target_date: date | None,
    ) -> list[UnifiedDoc]:
        date_filter = ""
        if target_date:
            date_filter = (
                "AND (COALESCE("
                f"j ->> '{settings.topic_date_column}', "
                "j ->> 'topic_date', "
                "j ->> 'crawl_date', "
                "j ->> 'publish_time', "
                "j ->> 'created_at'"
                "))::date = :target_date"
            )

        sql = text(
            f"""
            SELECT
                COALESCE(
                    j ->> 'platform',
                    j ->> 'platform_name',
                    j ->> 'source_name',
                    '{self._platform_content_table}'
                ) AS platform_name,
                j
            FROM (
                SELECT to_jsonb(p) AS j
                FROM {self._platform_content_table} p
            ) src
            WHERE (
                COALESCE(
                    j ->> 'topic_id',
                    j ->> 'topic',
                    j ->> 'topic_name',
                    j ->> 'topic_title'
                ) = :topic_key
                OR COALESCE(j ->> 'topic_name', j ->> 'topic', j ->> 'topic_title') = :topic_key
            )
            {date_filter}
            """
        )
        rows = self._session.execute(
            sql,
            {
                "topic_key": topic_key,
                "target_date": target_date,
            },
        ).mappings()
        return [self._to_platform_doc(topic_key, row) for row in rows]

    def _load_platform_docs_from_legacy_tables(
        self,
        topic_key: str,
        target_date: date | None,
    ) -> list[UnifiedDoc]:
        if not self._platform_tables:
            return []

        legacy_tables = [t for t in self._platform_tables if self._table_exists(t)]
        if not legacy_tables:
            return []

        date_filter = ""
        if target_date:
            date_filter = (
                "AND (COALESCE(j ->> 'topic_date', j ->> 'crawl_date', j ->> 'created_at'))::date = :target_date"
            )

        unions: list[str] = []
        for table_name in legacy_tables:
            unions.append(
                f"""
                SELECT
                    '{table_name}' AS platform_name,
                    j,
                    COALESCE(j ->> 'topic_id', j ->> 'topic', j ->> 'topic_name') AS raw_topic
                FROM (
                    SELECT to_jsonb(p) AS j
                    FROM {table_name} p
                ) src
                WHERE (
                    COALESCE(j ->> 'topic_id', j ->> 'topic', j ->> 'topic_name') = :topic_key
                    OR COALESCE(j ->> 'topic_name', j ->> 'topic') = :topic_key
                    OR COALESCE(j ->> 'source_keyword', j ->> 'keyword') = :topic_key
                )
                {date_filter}
                """
            )

        sql = text(" UNION ALL ".join(unions))
        rows = self._session.execute(
            sql,
            {"topic_key": topic_key, "target_date": target_date},
        ).mappings()
        return [self._to_platform_doc(topic_key, row) for row in rows]

    def _table_exists(self, table_name: str) -> bool:
        sql = text(
            """
            SELECT EXISTS (
                SELECT 1
                FROM information_schema.tables
                WHERE table_schema = ANY(current_schemas(false))
                  AND table_name = :table_name
            ) AS present
            """
        )
        row = self._session.execute(sql, {"table_name": table_name}).mappings().first()
        return bool(row and row.get("present"))

    def _load_news_docs_by_keywords(self, keywords: list[str], limit: int = 30) -> list[UnifiedDoc]:
        """Search daily_news directly by keyword matching on title/description."""
        if not keywords:
            return []
        conditions = " OR ".join(
            [
                "LOWER(COALESCE(to_jsonb(n) ->> 'title', '')) LIKE :kw" + str(i)
                + " OR LOWER(COALESCE(to_jsonb(n) ->> 'description', '')) LIKE :kw" + str(i)
                for i in range(len(keywords))
            ]
        )
        params = {f"kw{i}": f"%{kw.lower()}%" for i, kw in enumerate(keywords)}
        params["limit"] = limit

        sql = text(
            f"""
            SELECT
                COALESCE(to_jsonb(n) ->> 'news_id', to_jsonb(n) ->> 'id') AS raw_id,
                to_jsonb(n) ->> 'title' AS title,
                COALESCE(to_jsonb(n) ->> 'description', '') AS content,
                to_jsonb(n) ->> 'url' AS url,
                to_jsonb(n) ->> 'source_platform' AS source_name,
                NULL AS author,
                to_jsonb(n) ->> 'crawl_date' AS publish_time
            FROM {settings.table_daily_news} n
            WHERE {conditions}
            LIMIT :limit
            """
        )
        rows = self._session.execute(sql, params).mappings()
        return [self._to_news_doc_by_kw(row) for row in rows]

    def _load_platform_docs_by_keywords(self, keywords: list[str], limit: int = 30, platform_table: str = "") -> list[UnifiedDoc]:
        """Search platform tables directly by keyword matching on content fields.

        When *platform_table* is given, only that specific table is queried.
        """
        if not keywords:
            return []
        if platform_table:
            if not self._table_exists(platform_table):
                return []
            legacy_tables = [platform_table]
        else:
            legacy_tables = [t for t in self._platform_tables if self._table_exists(t)]
            if not legacy_tables:
                return []

        conditions = " OR ".join(
            [
                "LOWER(COALESCE(j ->> 'title', '')) LIKE :kw" + str(i)
                + " OR LOWER(COALESCE(j ->> 'desc', '')) LIKE :kw" + str(i)
                + " OR LOWER(COALESCE(j ->> 'content', '')) LIKE :kw" + str(i)
                + " OR LOWER(COALESCE(j ->> 'source_keyword', '')) LIKE :kw" + str(i)
                for i in range(len(keywords))
            ]
        )
        params = {f"kw{i}": f"%{kw.lower()}%" for i, kw in enumerate(keywords)}
        params["limit"] = limit

        results: list[UnifiedDoc] = []
        seen_ids: set[str] = set()
        per_table = max(limit, 10)

        for table_name in legacy_tables:
            sql = text(
                f"""
                SELECT
                    '{table_name}' AS platform_name,
                    j
                FROM (
                    SELECT to_jsonb(p) AS j
                    FROM {table_name} p
                ) src
                WHERE {conditions}
                LIMIT :per_table
                """
            )
            params["per_table"] = per_table
            rows = self._session.execute(sql, params).mappings()
            for row in rows:
                doc = self._to_platform_doc("keyword_search", row)
                if doc.doc_id not in seen_ids:
                    seen_ids.add(doc.doc_id)
                    results.append(doc)

        return results[:limit]

    @staticmethod
    def _to_news_doc_by_kw(row: Any) -> UnifiedDoc:
        return UnifiedDoc(
            doc_id=f"news:{row.get('raw_id') or 'unknown'}",
            topic_id="keyword_search",
            source_type="news",
            source_name=row.get("source_name"),
            title=row.get("title"),
            content=row.get("content") or "",
            publish_time=row.get("publish_time"),
            url=row.get("url"),
            author=row.get("author"),
            credibility_hint="high",
        )

    @staticmethod
    def _to_news_doc(topic_key: str, row: Any) -> UnifiedDoc:
        return UnifiedDoc(
            doc_id=f"news:{row.get('raw_id') or 'unknown'}",
            topic_id=topic_key,
            source_type="news",
            source_name=row.get("source_name"),
            title=row.get("title"),
            content=row.get("content") or "",
            publish_time=row.get("publish_time"),
            url=row.get("url"),
            author=row.get("author"),
            credibility_hint="high",
        )

    @staticmethod
    def _to_platform_doc(topic_key: str, row: Any) -> UnifiedDoc:
        payload = row.get("j", {})
        raw_id = (
            payload.get("note_id")
            or payload.get("aweme_id")
            or payload.get("video_id")
            or payload.get("post_id")
            or payload.get("id")
            or payload.get("url")
            or "unknown"
        )
        return UnifiedDoc(
            doc_id=f"platform:{row.get('platform_name')}:{raw_id}",
            topic_id=topic_key,
            source_type="platform",
            source_name=row.get("platform_name"),
            title=payload.get("title") or payload.get("desc"),
            content=payload.get("content") or payload.get("desc") or payload.get("title") or "",
            publish_time=payload.get("publish_time") or payload.get("create_time") or payload.get("created_at"),
            url=payload.get("url") or payload.get("note_url") or payload.get("jump_url"),
            author=payload.get("author") or payload.get("nickname") or payload.get("user_name"),
            credibility_hint="medium",
        )

    def insert_platform_content(
        self,
        docs: list[UnifiedDoc],
        topic_id: str,
        topic_name: str,
        keywords: list[str],
    ) -> int:
        """Insert crawled platform docs into platform_content table with topic tags.

        Uses ON CONFLICT DO NOTHING to skip duplicates (by platform + url).
        Returns number of newly inserted rows.
        """
        import json as _json

        if not self._platform_content_table or not self._table_exists(self._platform_content_table):
            return 0

        inserted = 0
        for doc in docs:
            try:
                sql = text(
                    f"""
                    INSERT INTO {self._platform_content_table}
                        (platform, note_id, title, content, url, author, publish_time,
                         topic_id, topic_name, keywords)
                    VALUES
                        (:platform, :note_id, :title, :content, :url, :author, :publish_time,
                         :topic_id, :topic_name, :keywords)
                    ON CONFLICT (platform, url) DO NOTHING
                    """
                )
                result = self._session.execute(
                    sql,
                    {
                        "platform": doc.source_name or doc.source_type,
                        "note_id": doc.doc_id,
                        "title": doc.title,
                        "content": doc.content,
                        "url": doc.url,
                        "author": doc.author,
                        "publish_time": doc.publish_time,
                        "topic_id": topic_id,
                        "topic_name": topic_name,
                        "keywords": _json.dumps(keywords, ensure_ascii=False),
                    },
                )
                if result.rowcount and result.rowcount > 0:
                    inserted += 1
            except Exception:
                continue

        return inserted
