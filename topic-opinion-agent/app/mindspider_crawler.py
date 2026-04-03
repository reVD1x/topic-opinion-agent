from __future__ import annotations

import time
from datetime import date

from app.common.config import settings
from app.data.mindspider_adapter import MindSpiderAdapter


def main() -> None:
    adapter = MindSpiderAdapter()
    if not adapter.enabled:
        print("[crawler] MINDSPIDER_ENABLED=false, crawler exits.")
        return

    run_count = 0
    interval = max(settings.mindspider_crawler_interval_seconds, 60)
    should_run_now = settings.mindspider_run_on_start

    while True:
        if should_run_now:
            run_count += 1
            print(f"[crawler] run #{run_count} started")
            ok, message = adapter.run_complete_workflow(target_date=date.today())
            state = "success" if ok else "failed"
            print(f"[crawler] run #{run_count} {state}: {message}")
            should_run_now = False
        else:
            should_run_now = True

        if not settings.mindspider_crawler_loop:
            break

        print(f"[crawler] sleeping {interval}s before next run")
        time.sleep(interval)


if __name__ == "__main__":
    main()
