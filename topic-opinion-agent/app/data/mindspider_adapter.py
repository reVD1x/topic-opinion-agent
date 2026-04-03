from __future__ import annotations

import os
import subprocess
import sys
from datetime import date
from pathlib import Path

from app.common.config import settings
from app.schemas.doc import UnifiedDoc
from app.storage.db import session_scope


class MindSpiderAdapter:
    """Single integration boundary for TopicOpinionAgent to call MindSpider."""

    def __init__(self) -> None:
        project_root = Path(__file__).resolve().parents[2]
        module_path = Path(settings.mindspider_module_path)
        self._module_root = module_path if module_path.is_absolute() else (project_root / module_path)

    @property
    def enabled(self) -> bool:
        return settings.mindspider_enabled

    def is_ready(self) -> bool:
        return self.enabled and (self._module_root / "main.py").exists()

    def run_complete_workflow(self, target_date: date | None = None) -> tuple[bool, str]:
        if not self.is_ready():
            return False, "mindspider_not_ready"

        cmd = [sys.executable, "main.py", "--complete"]
        if target_date:
            cmd.extend(["--date", target_date.strftime("%Y-%m-%d")])

        if settings.mindspider_platforms:
            cmd.append("--platforms")
            cmd.extend(settings.mindspider_platforms)

        cmd.extend(
            [
                "--keywords-count",
                str(settings.mindspider_keywords_count),
                "--max-keywords",
                str(settings.mindspider_max_keywords),
                "--max-notes",
                str(settings.mindspider_max_notes),
            ]
        )
        if settings.mindspider_test_mode:
            cmd.append("--test")

        env = self._build_mindspider_env()
        result = subprocess.run(
            cmd,
            cwd=self._module_root,
            env=env,
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            return True, (result.stdout or "mindspider_completed").strip()

        err_text = (result.stderr or result.stdout or "mindspider_failed").strip()
        return False, err_text

    def search(self, topic_id: str, query: str, limit: int = 10) -> list[UnifiedDoc]:
        if not self.enabled:
            return []

        with session_scope() as session:
            from app.data.pg_repository import PgRepository

            repo = PgRepository(session)
            resolved = repo.resolve_topic_key(query or topic_id, None)
            if not resolved:
                return []
            docs = repo.load_topic_evidence(resolved.resolved_key, None)

        return docs[: max(limit, 0)]

    def _build_mindspider_env(self) -> dict[str, str]:
        env = dict(os.environ)
        env.setdefault("DB_DIALECT", "postgresql")
        env.setdefault("DB_HOST", settings.pg_host)
        env.setdefault("DB_PORT", str(settings.pg_port))
        env.setdefault("DB_USER", settings.pg_user)
        env.setdefault("DB_PASSWORD", settings.pg_password)
        env.setdefault("DB_NAME", settings.pg_db)
        env.setdefault("MINDSPIDER_API_KEY", settings.mindspider_api_key)
        env.setdefault("MINDSPIDER_BASE_URL", settings.mindspider_base_url)
        env.setdefault("MINDSPIDER_MODEL_NAME", settings.mindspider_model_name)
        return env
