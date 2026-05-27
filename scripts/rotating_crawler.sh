#!/bin/bash
# 轮换式多平台爬虫 — 每轮每平台限时 120 秒，统一关键词
# 用法: bash scripts/rotating_crawler.sh

PLATFORMS=("xhs" "dy" "wb" "zhihu" "ks" "tieba" "bili")
# 统一关键词（适合本科毕业论文展示）
KEYWORDS="AI"
MAX_NOTES=1
MAX_COMMENTS=10
TIMEOUT_SEC=120
COOLDOWN=5

MINDSPIDER_DIR="$(cd "$(dirname "$0")/../MindSpider" && pwd)"
PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"

echo "========================================="
echo "轮换式多平台爬虫启动"
echo "平台: ${PLATFORMS[*]}"
echo "关键词: ${KEYWORDS}"
echo "每轮每平台: ${MAX_NOTES} 篇笔记, 每篇最多 ${MAX_COMMENTS} 条评论"
echo "单平台超时: ${TIMEOUT_SEC}s, 冷却: ${COOLDOWN}s"
echo "========================================="

round=0

while true; do
    round=$((round + 1))
    echo ""
    echo "#########################################"
    echo "### 第 ${round} 轮 $(date '+%H:%M:%S')"
    echo "#########################################"

    for platform in "${PLATFORMS[@]}"; do
        echo ""
        echo "========================================="
        echo "=== [Round ${round}] [${platform}] 开始 $(date '+%H:%M:%S')"
        echo "========================================="

        # perl 实现超时 + 进程组清理
        # - fork 子进程，子进程 setpgrp(0,0) 创建新进程组后 exec python
        # - 父进程 alarm 定时，超时后 kill 进程组 (先 TERM 再 KILL)
        (cd "${PROJECT_DIR}" && perl -e '
            $timeout = shift;
            $pid = fork();
            if (!defined $pid) { exit 1; }
            if ($pid == 0) {
                setpgrp(0, 0);
                exec @ARGV;
                exit 127;
            }
            eval {
                local $SIG{ALRM} = sub {
                    kill 15, -$pid;
                    sleep 1;
                    kill 9, -$pid;
                    die "TIMEOUT\n";
                };
                alarm $timeout;
                waitpid $pid, 0;
                alarm 0;
            };
            if ($@ eq "TIMEOUT\n") { exit 142; }
            exit $? >> 8;
        ' "${TIMEOUT_SEC}" \
            uv run --extra crawler python -u \
            "${MINDSPIDER_DIR}/DeepSentimentCrawling/main.py" \
            --platform "${platform}" \
            --keywords "${KEYWORDS}" \
            --max-notes "${MAX_NOTES}" \
            --max-comments "${MAX_COMMENTS}" \
            --headless false 2>&1)

        exit_code=$?
        if [ $exit_code -eq 0 ]; then
            echo "=== [${platform}] 完成 $(date '+%H:%M:%S')"
        elif [ $exit_code -eq 142 ]; then
            echo "=== [${platform}] 超时 ${TIMEOUT_SEC}s $(date '+%H:%M:%S')"
        else
            echo "=== [${platform}] 异常退出 (exit=$exit_code) $(date '+%H:%M:%S')"
        fi

        echo "--- 冷却 ${COOLDOWN}s ---"
        sleep ${COOLDOWN}
    done

    echo ""
    echo "=== 第 ${round} 轮完成 $(date '+%H:%M:%S') ==="
done
