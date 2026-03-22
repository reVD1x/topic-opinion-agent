from __future__ import annotations

from app.data.pg_repository import PgRepository
from app.storage.db import session_scope


def main() -> None:
    topic_id = "demo_topic"
    with session_scope() as session:
        repo = PgRepository(session)
        rows = repo.load_topic_evidence(topic_key=topic_id, target_date=None)
        print(f"rows={len(rows)}")
        for item in rows[:5]:
            print(item.doc_id, item.title)


if __name__ == "__main__":
    main()
