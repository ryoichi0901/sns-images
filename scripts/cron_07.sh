#!/bin/bash
# 07:00 自動投稿 - Threadsテキストのみ + 5分後に補足コメント

PROJ="/Users/watanaberyouichi/Documents/ryo-sns-auto"
LOG="${PROJ}/logs/cron_$(date +%Y%m%d).log"

export PATH="/Users/watanaberyouichi/.npm-global/bin:/usr/local/bin:/usr/bin:/bin:$PATH"

cd "$PROJ"

echo "" >> "$LOG"
echo "--- 07:00 Threads投稿開始: $(date '+%Y-%m-%d %H:%M:%S') ---" >> "$LOG"

python3 scripts/run.py --platforms th --followup >> "$LOG" 2>&1
EXIT_CODE=$?

if [ $EXIT_CODE -eq 0 ]; then
  echo "--- 07:00 完了（補足コメント含む）: $(date '+%H:%M:%S') (exit: 0) ---" >> "$LOG"
else
  echo "--- 07:00 エラー: $(date '+%H:%M:%S') (exit: $EXIT_CODE) ---" >> "$LOG"
fi

exit $EXIT_CODE
