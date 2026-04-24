#!/bin/bash
# 21:00 自動投稿
# Phase 1: Instagram画像カルーセル + Threadsテキスト + 5分後に補足コメント
# Phase 2: sns-orchestrator → competitor-researcher → trend-analyzer
#           → short-video-scripter → FFmpeg動画 → Reels投稿 → 補足コメント

PROJ="/Users/watanaberyouichi/Documents/ryo-sns-auto"
CLAUDE="/Users/watanaberyouichi/.npm-global/bin/claude"
LOG="${PROJ}/logs/cron_$(date +%Y%m%d).log"
TODAY=$(date +%Y%m%d)

export PATH="/Users/watanaberyouichi/.npm-global/bin:/usr/local/bin:/usr/bin:/bin:$PATH"

cd "$PROJ"

echo "" >> "$LOG"
echo "========================================" >> "$LOG"
echo "  21:00 フル投稿開始: $(date '+%Y-%m-%d %H:%M:%S')" >> "$LOG"
echo "========================================" >> "$LOG"

# ── Phase 1: メイン投稿（Instagram カルーセル + Threads + 5分後補足コメント） ──
echo "" >> "$LOG"
echo "  [Phase 1] Instagram + Threads + 補足コメント(5分後)" >> "$LOG"
echo "  開始: $(date '+%H:%M:%S')" >> "$LOG"

python3 scripts/run.py --platforms ig th --followup >> "$LOG" 2>&1
P1_EXIT=$?

echo "  [Phase 1] 完了: $(date '+%H:%M:%S') (exit: $P1_EXIT)" >> "$LOG"

# ── Phase 2: sns-orchestrator経由でReels生成・投稿 ────────────────────────────
echo "" >> "$LOG"
echo "  [Phase 2] sns-orchestrator → Reels生成・投稿" >> "$LOG"
echo "  開始: $(date '+%H:%M:%S')" >> "$LOG"

"$CLAUDE" \
  --agent sns-orchestrator \
  -p "今日のInstagram Reels投稿を以下の順序で実行してください。

【ステップ1】competitor-researcherサブエージェントを起動してください。
AI副業×資産形成ジャンルの直近7日間のバズ投稿を10件以上分析し、
logs/research_context_${TODAY}.json に保存してください。

【ステップ2】trend-analyzerサブエージェントを起動してください。
今週のトレンドキーワード・アルゴリズム傾向を分析し、
logs/research_context_${TODAY}.json にマージ保存してください。

【ステップ3】以下のコマンドを実行してください。
リサーチ結果が short-video-scripter の台本生成に自動反映されます。
python3 scripts/post_reels.py

完了後、Reels IDと補足コメントIDを報告してください。" \
  --dangerously-skip-permissions \
  >> "$LOG" 2>&1

P2_EXIT=$?

echo "  [Phase 2] 完了: $(date '+%H:%M:%S') (exit: $P2_EXIT)" >> "$LOG"
echo "========================================" >> "$LOG"

[ $P1_EXIT -eq 0 ] && [ $P2_EXIT -eq 0 ] && exit 0 || exit 1
