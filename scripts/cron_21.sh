#!/bin/bash
# 21:00 自動投稿
# Instagram カルーセル + Threads テキスト + 5分後に補足コメント
# ※ Reels は 07:00 の GitHub Actions が予約生成し、Instagram サーバーが自動公開するため不要

PROJ="/Users/watanaberyouichi/Documents/ryo-sns-auto"
LOG="${PROJ}/logs/cron_$(date +%Y%m%d).log"

export PATH="/Users/watanaberyouichi/.npm-global/bin:/usr/local/bin:/usr/bin:/bin:$PATH"

cd "$PROJ"

echo "" >> "$LOG"
echo "========================================" >> "$LOG"
echo "  21:00 投稿開始: $(date '+%Y-%m-%d %H:%M:%S')" >> "$LOG"
echo "========================================" >> "$LOG"

echo "" >> "$LOG"
echo "  Instagram + Threads + 補足コメント(5分後)" >> "$LOG"
echo "  開始: $(date '+%H:%M:%S')" >> "$LOG"

python3 scripts/run.py --platforms ig th --followup >> "$LOG" 2>&1
EXIT_CODE=$?

echo "  完了: $(date '+%H:%M:%S') (exit: $EXIT_CODE)" >> "$LOG"
echo "========================================" >> "$LOG"

exit $EXIT_CODE
