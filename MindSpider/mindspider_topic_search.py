#!/usr/bin/env python3
"""
Targeted keyword crawl helper for TopicOpinionAgent.
Accepts keywords via CLI, crawls a single platform with strict limits.

Limits (anti-crawl by design):
  - Single platform only (default xhs)
  - Max 5 notes per keyword
  - Comments disabled
  - Default: cookie login, headless

Two-phase login support:
  - --login-type cookie (default): uses saved Playwright login state
  - --login-type qrcode: shows QR code for user to scan
  - --headless false: shows browser window (needed for QR code login)
"""

import argparse
import json
import sys
from pathlib import Path

project_root = Path(__file__).resolve().parent
sys.path.insert(0, str(project_root))

from DeepSentimentCrawling.platform_crawler import PlatformCrawler


def main() -> None:
    parser = argparse.ArgumentParser(description="MindSpider targeted topic search")
    parser.add_argument(
        "--keywords", required=True,
        help="Comma-separated search keywords (max 3 will be used)",
    )
    parser.add_argument("--platform", default="xhs")
    parser.add_argument("--max-notes", type=int, default=5)
    parser.add_argument("--login-type", default="cookie",
                        choices=["cookie", "qrcode"])
    parser.add_argument("--headless", default="true",
                        choices=["true", "false"])
    parser.add_argument("--mediacrawler-path", default="",
                        help="Optional isolated MediaCrawler dir for parallel crawling")
    args = parser.parse_args()

    keywords = [k.strip() for k in args.keywords.split(",") if k.strip()]
    if not keywords:
        print(json.dumps({"success": False, "error": "no_keywords"}))
        sys.exit(1)

    keywords = keywords[:3]
    headless = args.headless.lower() == "true"

    mc_path = args.mediacrawler_path.strip() or None
    crawler = PlatformCrawler(mediacrawler_path=mc_path)
    try:
        result = crawler.run_crawler(
            platform=args.platform,
            keywords=keywords,
            login_type=args.login_type,
            max_notes=max(args.max_notes, 1),
            enable_comments=False,
            headless=headless,
        )
        print(json.dumps({"success": result.get("success", False)}))
    except Exception as exc:
        print(json.dumps({"success": False, "error": str(exc)}))
        sys.exit(1)


if __name__ == "__main__":
    main()
