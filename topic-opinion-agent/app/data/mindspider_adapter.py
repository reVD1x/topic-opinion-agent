from __future__ import annotations

import json
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

    # Anti-crawl safety limits
    MAX_KEYWORDS = 3
    MAX_NOTES_PER_KEYWORD = 5
    CRAWL_TIMEOUT_SECONDS = 300  # 5 minutes

    def __init__(self) -> None:
        project_root = Path(__file__).resolve().parents[2]
        module_path = Path(settings.mindspider_module_path)
        self._module_root = module_path if module_path.is_absolute() else (project_root / module_path)
        self.last_log: str = ""  # Latest subprocess stdout/stderr for debugging

    @property
    def enabled(self) -> bool:
        return settings.mindspider_enabled

    def is_ready(self) -> bool:
        return self.enabled and (self._module_root / "main.py").exists()

    # ------------------------------------------------------------------
    # Real-time topic search (replaces the old DB-pass-through search)
    # ------------------------------------------------------------------

    def search(
        self,
        keywords: list[str],
        platforms: list[str] | None = None,
        max_notes: int = MAX_NOTES_PER_KEYWORD,
    ) -> list[UnifiedDoc]:
        """
        Crawl platforms in real-time for *keywords* and return UnifiedDoc results.

        Safety: max 3 keywords, 5 notes/keyword, comments disabled, 5-min timeout.
        On any failure, returns [] so the pipeline can continue with other sources.
        """
        if not self.enabled:
            return []
        if not keywords:
            return []

        keywords = keywords[: self.MAX_KEYWORDS]
        if not platforms:
            platforms = ["xhs"]
        max_notes = max(min(max_notes, self.MAX_NOTES_PER_KEYWORD), 1)

        ok, msg = self._run_topic_search(keywords, platforms[0], max_notes)
        if not ok:
            self.last_log += f"\n[search failed] {msg}\n"
            return []

        return self._read_crawled_docs(keywords, max_notes)

    def _run_topic_search(self, keywords: list[str], platform: str, max_notes: int) -> tuple[bool, str]:
        """Call MindSpider helper script with strict limits.
        Phase 1: cookie login (headless). If auth fails, Phase 2: qrcode (visible browser)."""
        helper = self._module_root / "mindspider_topic_search.py"
        if not helper.exists():
            return False, f"helper script not found: {helper}"

        env = self._build_mindspider_env()
        base_cmd = [
            sys.executable, str(helper),
            "--keywords", ",".join(keywords),
            "--platform", platform,
            "--max-notes", str(max_notes),
        ]

        # Phase 1: cookie login, headless
        self.last_log = "[Phase 1] Cookie login (headless)...\n"
        ok, err = self._exec_crawl(base_cmd + ["--login-type", "cookie", "--headless", "true"], env)
        if ok:
            return True, "ok"

        # Check if it's an auth failure
        err_lower = err.lower()
        is_auth_error = any(
            tag in err_lower
            for tag in ["datafetcherror", "pong", "login", "auth", "cookie"]
        )
        if not is_auth_error:
            return False, err

        # Phase 2: QR code login with visible browser
        self.last_log += (
            "\n[Phase 2] Cookie login failed, opening browser for QR code login.\n"
            "请在弹出的浏览器窗口中用小红书 App 扫描二维码登录。\n"
        )
        return self._exec_crawl(
            base_cmd + ["--login-type", "qrcode", "--headless", "false"],
            env,
            timeout=180,  # 3 min for QR scan
        )

    def _exec_crawl(
        self, cmd: list[str], env: dict[str, str], timeout: int | None = None
    ) -> tuple[bool, str]:
        """Execute crawl subprocess and parse result."""
        if timeout is None:
            timeout = self.CRAWL_TIMEOUT_SECONDS
        try:
            result = subprocess.run(
                cmd,
                cwd=self._module_root,
                env=env,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
        except subprocess.TimeoutExpired:
            self.last_log += "\n[timeout] Crawl exceeded time limit\n"
            return False, "爬取超时"

        self.last_log += f"--- stdout ---\n{result.stdout}\n--- stderr ---\n{result.stderr}\n"

        # Parse the last JSON line from stdout
        for line in reversed(result.stdout.strip().splitlines()):
            line = line.strip()
            if line.startswith("{"):
                try:
                    parsed = json.loads(line)
                    if parsed.get("success"):
                        return True, "ok"
                    err = parsed.get("error", "爬取失败")
                    return False, err
                except json.JSONDecodeError:
                    pass

        # Extract a meaningful error from stderr
        stderr = result.stderr or ""
        for line in reversed(stderr.splitlines()):
            line = line.strip()
            if line and "Error" in line:
                return False, line[-120:]
        stderr_tail = stderr.strip()[-200:] if stderr.strip() else ""
        return False, stderr_tail or "爬取失败（无输出）"

    def _read_crawled_docs(self, keywords: list[str], limit: int) -> list[UnifiedDoc]:
        """After a successful crawl, read matching docs from platform tables."""
        with session_scope() as session:
            from app.data.pg_repository import PgRepository
            repo = PgRepository(session)
            return repo._load_platform_docs_by_keywords(keywords, limit=limit * len(keywords))

    # ------------------------------------------------------------------
    # Full workflow (daily cron / background use)
    # ------------------------------------------------------------------

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
