from __future__ import annotations


import json
import os
import shutil
import subprocess
import sys
import tempfile
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
    CRAWL_TIMEOUT_SECONDS = 600  # 10 minutes

    # Platform code → DB table name
    PLATFORM_TABLE_MAP: dict[str, str] = {
        "xhs": "xhs_note",
        "dy": "douyin_aweme",
        "ks": "kuaishou_video",
        "bili": "bilibili_video",
        "wb": "weibo_note",
        "tieba": "tieba_note",
        "zhihu": "zhihu_content",
    }
    # Platform code → display name
    PLATFORM_CN_MAP: dict[str, str] = {
        "xhs": "小红书", "dy": "抖音", "ks": "快手",
        "bili": "B站", "wb": "微博", "tieba": "贴吧", "zhihu": "知乎",
    }

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

        Platforms are crawled sequentially to avoid Chrome process interference.
        Safety: max 3 keywords, 5 notes/keyword, comments disabled, 5-min timeout.
        Individual platform failures are logged but do not block other platforms.
        """
        if not self.enabled:
            return []
        if not keywords:
            return []

        keywords = keywords[: self.MAX_KEYWORDS]
        if not platforms:
            platforms = ["xhs"]
        max_notes = max(min(max_notes, self.MAX_NOTES_PER_KEYWORD), 1)

        all_docs: list[UnifiedDoc] = []
        platform_counts: list[str] = []
        log_parts: list[str] = []

        # Run platforms sequentially to avoid Chrome process interference
        # (port conflicts, Singleton locks, CDP signal handlers).
        for platform in platforms:
            try:
                docs, plog = self._crawl_one_platform(keywords, platform, max_notes)
            except Exception as exc:
                log_parts.append(f"\n[search failed · {platform}] {exc}\n")
                continue
            log_parts.extend(plog)
            cn = self.PLATFORM_CN_MAP.get(platform, platform)
            platform_counts.append(f"{cn}:{len(docs)}条")
            all_docs.extend(docs)

        if platform_counts:
            log_parts.append(f"\n爬取结果: {' | '.join(platform_counts)}\n")
        self.last_log = "".join(log_parts)
        return all_docs

    def _create_isolated_mediacrawler(self, platform: str) -> tuple[Path, str]:
        """Create a temp MediaCrawler tree with an isolated config/ dir.

        Symlinks all files/dirs from the original except config/ (copied to
        avoid race conditions). browser_data/ is symlinked so Playwright login
        state (cookies) persists across sessions.
        Returns (temp_mediacrawler_path, cleanup_root_dir).
        """
        src = self._module_root / "DeepSentimentCrawling" / "MediaCrawler"
        tmp_root = Path(tempfile.mkdtemp(prefix=f"mc_{platform}_"))
        dest = tmp_root / "MediaCrawler"
        dest.mkdir()

        for item in src.iterdir():
            if item.name == "config":
                shutil.copytree(item, dest / "config")
            elif item.name == "browser_data":
                (dest / item.name).symlink_to(item)
            else:
                (dest / item.name).symlink_to(item)

        return dest, str(tmp_root)

    @staticmethod
    def _cleanup_singleton_locks(browser_data_dir: Path) -> None:
        """Remove stale Chrome singleton files that prevent browser launch."""
        for lock_file in browser_data_dir.rglob("Singleton*"):
            try:
                lock_file.unlink(missing_ok=True)
            except OSError:
                pass

    def _crawl_one_platform(
        self, keywords: list[str], platform: str, max_notes: int
    ) -> tuple[list[UnifiedDoc], list[str]]:
        """Run topic search + read docs for a single platform. Fully thread-safe.

        Creates an isolated MediaCrawler copy so parallel runs do not race on
        shared config files (base_config.py / db_config.py).
        """
        cn = self.PLATFORM_CN_MAP.get(platform, platform)
        log_parts: list[str] = [f"[{cn}] Phase 1: Cookie login...\n"]

        # Clean stale Chrome SingletonLock files from symlinked browser_data
        orig_browser_data = self._module_root / "DeepSentimentCrawling" / "MediaCrawler" / "browser_data"
        self._cleanup_singleton_locks(orig_browser_data)

        mc_path, cleanup_root = self._create_isolated_mediacrawler(platform)
        try:
            ok, err = self._run_topic_search_isolated(
                keywords, platform, max_notes, log_parts, mc_path, cn,
            )
            if not ok:
                log_parts.append(f"[{cn} search failed] {err}\n")
                return [], log_parts
            docs = self._read_crawled_docs(keywords, max_notes, platform=platform)
            log_parts.append(f"[{cn}] 爬取完成: {len(docs)}条\n")
            return docs, log_parts
        finally:
            shutil.rmtree(cleanup_root, ignore_errors=True)

    def _run_topic_search_isolated(
        self, keywords: list[str], platform: str, max_notes: int,
        log_parts: list[str], mediacrawler_path: Path, cn: str,
    ) -> tuple[bool, str]:
        """Run topic search against an isolated MediaCrawler copy."""
        helper = self._module_root / "mindspider_topic_search.py"
        if not helper.exists():
            return False, f"helper script not found: {helper}"

        env = self._build_mindspider_env()
        base_cmd = [
            sys.executable, str(helper),
            "--keywords", ",".join(keywords),
            "--platform", platform,
            "--max-notes", str(max_notes),
            "--mediacrawler-path", str(mediacrawler_path),
        ]

        # Phase 1: cookie login, visible browser
        ok, err = self._exec_crawl_to_log(
            base_cmd + ["--login-type", "cookie", "--headless", "false"], env, log_parts,
        )
        if ok:
            return True, "ok"

        # Check if it's an auth failure — inspect both the parsed error and
        # the full subprocess log (stdout + stderr), because the parsed err
        # string may fall back to a generic "爬取失败" when the JSON response
        # lacks an "error" field.
        err_lower = err.lower()
        log_joined = "".join(log_parts).lower()
        is_auth_error = any(
            tag in err_lower or tag in log_joined
            for tag in ["datafetcherror", "pong", "login", "auth", "cookie", "没有权限"]
        )
        if not is_auth_error:
            return False, err

        # Phase 2: QR code login with visible browser
        # Clean stale SingletonLock in case Phase 1 Chrome was killed
        self._cleanup_singleton_locks(mediacrawler_path / "browser_data")
        log_parts.append(
            f"\n[Phase 2] Cookie login failed, opening browser for {cn} QR code login.\n"
            "请在弹出的浏览器窗口中扫描二维码登录。\n"
        )
        return self._exec_crawl_to_log(
            base_cmd + ["--login-type", "qrcode", "--headless", "false"],
            env,
            log_parts,
            timeout=180,
        )

    def _exec_crawl_to_log(
        self, cmd: list[str], env: dict[str, str], log_parts: list[str],
        timeout: int | None = None,
    ) -> tuple[bool, str]:
        """Execute crawl subprocess, writing output to *log_parts* (thread-safe)."""
        if timeout is None:
            timeout = self.CRAWL_TIMEOUT_SECONDS
        try:
            result = subprocess.run(
                cmd,
                cwd=self._module_root,
                env=env,
                capture_output=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout,
            )
        except subprocess.TimeoutExpired as exc:
            log_parts.append("\n[timeout] Crawl exceeded time limit\n")
            if exc.stdout:
                log_parts.append(f"--- partial stdout ---\n{exc.stdout}\n")
            if exc.stderr:
                log_parts.append(f"--- partial stderr ---\n{exc.stderr}\n")
            return False, "爬取超时"

        log_parts.append(f"--- stdout ---\n{result.stdout}\n--- stderr ---\n{result.stderr}\n")

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

    def _read_crawled_docs(self, keywords: list[str], limit: int, platform: str = "") -> list[UnifiedDoc]:
        """After a successful crawl, read matching docs from platform tables.

        When *platform* is given, only the corresponding DB table is queried.
        """
        table = self.PLATFORM_TABLE_MAP.get(platform, "")
        with session_scope() as session:
            from app.data.pg_repository import PgRepository
            repo = PgRepository(session)
            return repo._load_platform_docs_by_keywords(keywords, limit=limit * len(keywords), platform_table=table)

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
            encoding="utf-8",
            errors="replace",
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
