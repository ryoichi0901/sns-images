#!/bin/bash
# 毎朝9時の自動投稿スクリプト
# claude -p で sns-orchestrator を起動し Instagram・Threads に投稿する

set -euo pipefail

PROJ="/Users/watanaberyouichi/Documents/ryo-sns-auto"
CLAUDE="/Users/watanaberyouichi/.npm-global/bin/claude"
LOG_DIR="${PROJ}/logs"
LOG_FILE="${LOG_DIR}/cron_$(date +%Y%m%d).log"

# cron 環境では PATH が限定的なため明示設定
export PATH="/Users/watanaberyouichi/.npm-global/bin:/usr/local/bin:/usr/bin:/bin:$PATH"

cd "$PROJ"

echo "" >> "$LOG_FILE"
echo "========================================" >> "$LOG_FILE"
echo "  自動投稿開始: $(date '+%Y-%m-%d %H:%M:%S')" >> "$LOG_FILE"
echo "========================================" >> "$LOG_FILE"

"$CLAUDE" \
  --agent sns-orchestrator \
  -p "今日のInstagramとThreadsへの投稿を自動実行してください。python3 scripts/run.py --platforms ig th を実行して投稿を完了させてください。" \
  --dangerously-skip-permissions \
  >> "$LOG_FILE" 2>&1

EXIT_CODE=$?

echo "" >> "$LOG_FILE"
if [ $EXIT_CODE -eq 0 ]; then
  echo "  完了: $(date '+%Y-%m-%d %H:%M:%S') (exit: 0)" >> "$LOG_FILE"
else
  echo "  エラー: $(date '+%Y-%m-%d %H:%M:%S') (exit: $EXIT_CODE)" >> "$LOG_FILE"
fi
echo "========================================" >> "$LOG_FILE"

exit $EXIT_CODE
