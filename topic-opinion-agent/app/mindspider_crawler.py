"""MindSpider 后台爬虫 — 定时循环爬取社交媒体内容。"""

from __future__ import annotations

import logging
import time
from datetime import date

from app.common.config import settings
from app.common.logging_config import setup_logging
from app.data.mindspider_adapter import MindSpiderAdapter

logger = logging.getLogger(__name__)


def main() -> None:
    setup_logging()
    adapter = MindSpiderAdapter()
    if not adapter.enabled:
        logger.info("MINDSPIDER_ENABLED=false, crawler exits.")
        return

    run_count = 0
    interval = max(settings.mindspider_crawler_interval_seconds, 60)
    should_run_now = settings.mindspider_run_on_start

    while True:
        if should_run_now:
            run_count += 1
            logger.info("run #%d started", run_count)
            ok, message = adapter.run_complete_workflow(target_date=date.today())
            state = "success" if ok else "failed"
            logger.info("run #%d %s: %s", run_count, state, message)
            should_run_now = False
        else:
            should_run_now = True

        if not settings.mindspider_crawler_loop:
            break

        logger.info("sleeping %ds before next run", interval)
        time.sleep(interval)


if __name__ == "__main__":
    main()
