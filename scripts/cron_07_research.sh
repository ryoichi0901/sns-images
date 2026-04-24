#!/bin/bash
# 07:05 毎朝リサーチ + コメント文案生成
# DuckDuckGo で金融・副業系の Instagram/Threads 投稿を検索し、
# 銀行員目線のコメント文案を logs/comment_targets_YYYYMMDD.md に出力する。
# 実際のコメント投稿は人間が確認してから手動で行う。

PROJ="/Users/watanaberyouichi/Documents/ryo-sns-auto"
LOG="${PROJ}/logs/cron_$(date +%Y%m%d).log"

export PATH="/Users/watanaberyouichi/.npm-global/bin:/usr/local/bin:/usr/bin:/bin:$PATH"

cd "$PROJ"

echo "" >> "$LOG"
echo "--- 07:05 コメントリサーチ開始: $(date '+%Y-%m-%d %H:%M:%S') ---" >> "$LOG"

python3 scripts/research_comments.py >> "$LOG" 2>&1
EXIT_CODE=$?

if [ $EXIT_CODE -eq 0 ]; then
    echo "--- 07:05 リサーチ完了: $(date '+%H:%M:%S') ---" >> "$LOG"
else
    echo "--- 07:05 リサーチエラー (exit: $EXIT_CODE): $(date '+%H:%M:%S') ---" >> "$LOG"
fi

exit $EXIT_CODE
