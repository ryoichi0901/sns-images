"""
週次まとめ投稿スクリプト
今週の投稿実績をログから集計し、Claude Haiku で週次まとめを生成して
Threads に投稿する。

Usage:
  python3 scripts/weekly_summary.py              # 今週のまとめをプレビュー
  python3 scripts/weekly_summary.py --post       # Threads に投稿
  python3 scripts/weekly_summary.py --week -1    # 先週分（-1=先週, 0=今週）
  python3 scripts/weekly_summary.py --dry-run    # 生成のみ・投稿しない
"""
import argparse
import datetime
import json
import os
import sys
import time
from pathlib import Path
from typing import Optional

import anthropic
import requests
from dotenv import load_dotenv

load_dotenv(os.path.expanduser("~/Documents/Obsidian Vault/.env"))

TH_USER_ID    = os.getenv("THREADS_USER_ID")
TH_TOKEN      = os.getenv("THREADS_ACCESS_TOKEN")
ANTHROPIC_KEY = os.getenv("ANTHROPIC_API_KEY")

ROOT      = Path(__file__).parent.parent
LOGS_DIR  = ROOT / "logs"
LOGS_DIR.mkdir(exist_ok=True)

THEME_LABELS = {
    "investment":      "💰 お金を増やす",
    "side_job":        "🤖 お金を稼ぐ",
    "banking_secrets": "🏦 銀行員の裏話",
}


# ── ログ集計 ──────────────────────────────────────────────────────────────────────

def get_week_range(week_offset: int = 0):
    """week_offset=0:今週, -1:先週 の月〜日を返す"""
    today = datetime.date.today()
    monday = today - datetime.timedelta(days=today.weekday()) + datetime.timedelta(weeks=week_offset)
    sunday = monday + datetime.timedelta(days=6)
    return monday, sunday


def load_threads_logs(start: datetime.date, end: datetime.date) -> list[dict]:
    path = LOGS_DIR / "threads_drafts_log.jsonl"
    if not path.exists():
        return []
    entries = []
    seen_post_ids = set()
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                e = json.loads(line)
                d = datetime.date.fromisoformat(e.get("date", "2000-01-01"))
                pid = e.get("post_id", "")
                # 重複除去（同一post_idは最新1件だけ）
                if start <= d <= end and pid not in seen_post_ids:
                    seen_post_ids.add(pid)
                    entries.append(e)
            except (json.JSONDecodeError, ValueError):
                pass
    return entries


def load_ig_logs(start: datetime.date, end: datetime.date) -> list[dict]:
    path = LOGS_DIR / "post_log.jsonl"
    if not path.exists():
        return []
    entries = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                e = json.loads(line)
                raw = e.get("date") or e.get("datetime", "")[:10]
                d = datetime.date.fromisoformat(raw)
                if start <= d <= end:
                    entries.append(e)
            except (json.JSONDecodeError, ValueError):
                pass
    return entries


def collect_week_stats(week_offset: int = 0) -> dict:
    """週次投稿データを集計して返す"""
    start, end = get_week_range(week_offset)
    th_logs = load_threads_logs(start, end)
    ig_logs = load_ig_logs(start, end)

    # テーマ別カウント
    theme_counts: dict[str, int] = {}
    for e in th_logs:
        group = e.get("theme_group", "side_job")
        theme_counts[group] = theme_counts.get(group, 0) + 1

    # コメント付き投稿数
    with_comment = sum(1 for e in th_logs if e.get("comment_id"))

    # 投稿タイトル一覧
    titles = [e.get("title", "") for e in th_logs if e.get("title")]

    return {
        "start":         start.isoformat(),
        "end":           end.isoformat(),
        "threads_total": len(th_logs),
        "ig_total":      len(ig_logs),
        "with_comment":  with_comment,
        "theme_counts":  theme_counts,
        "titles":        titles,
    }


# ── コンテンツ生成 ─────────────────────────────────────────────────────────────────

def generate_summary(stats: dict) -> str:
    """Claude Haiku で週次まとめ投稿文を生成する"""
    theme_breakdown = "\n".join(
        f"  {THEME_LABELS.get(k, k)}: {v}件"
        for k, v in stats["theme_counts"].items()
    ) or "  データなし"

    titles_list = "\n".join(f"  ・{t}" for t in stats["titles"]) or "  データなし"

    prompt = f"""元銀行員インフルエンサーとして、今週のSNS投稿の週次まとめをThreadsに投稿します。

【今週の実績データ】
期間: {stats['start']} 〜 {stats['end']}
Threads投稿数: {stats['threads_total']}件
Instagram投稿数: {stats['ig_total']}件
補足コメント付き: {stats['with_comment']}件

【テーマ別内訳】
{theme_breakdown}

【今週の投稿タイトル】
{titles_list}

【まとめ投稿の条件】
- 冒頭は「今週の振り返り（日付範囲）」から始める
- 投稿数・テーマを自然に盛り込む
- 「副業解禁○ヶ月、月7万稼ぎながら」を自然に入れる
- 来週も発信を続ける意志を示す一言
- 読者への感謝・問いかけで締める
- 300字以内
- ハッシュタグは末尾に3個（#AI副業 #元銀行員 #週次報告）
- 捏造統計・根拠不明の数字を使わない

投稿文のみ出力してください。"""

    client = anthropic.Anthropic(api_key=ANTHROPIC_KEY)
    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=600,
        messages=[{"role": "user", "content": prompt}],
    )
    return response.content[0].text.strip()


# ── Threads 投稿 ──────────────────────────────────────────────────────────────────

def post_summary_to_threads(text: str) -> str:
    """週次まとめを Threads に投稿して投稿IDを返す"""
    r1 = requests.post(
        f"https://graph.threads.net/v1.0/{TH_USER_ID}/threads",
        data={"media_type": "TEXT", "text": text, "access_token": TH_TOKEN},
        timeout=30,
    )
    r1.raise_for_status()
    container_id = r1.json()["id"]
    time.sleep(3)

    r2 = requests.post(
        f"https://graph.threads.net/v1.0/{TH_USER_ID}/threads_publish",
        data={"creation_id": container_id, "access_token": TH_TOKEN},
        timeout=30,
    )
    r2.raise_for_status()
    post_id = r2.json()["id"]
    print(f"✓ 週次まとめ投稿完了: {post_id}")
    return post_id


def log_summary(stats: dict, text: str, post_id: Optional[str]) -> None:
    entry = {
        "date":     datetime.date.today().isoformat(),
        "type":     "weekly_summary",
        "week":     f"{stats['start']} 〜 {stats['end']}",
        "stats":    stats,
        "post_id":  post_id,
        "text":     text[:100],
    }
    log_path = LOGS_DIR / "weekly_summary_log.jsonl"
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


# ── メイン ────────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="週次まとめ投稿")
    parser.add_argument("--post",    action="store_true", help="Threads に投稿する")
    parser.add_argument("--week",    type=int, default=0,
                        help="対象週のオフセット（0=今週, -1=先週）")
    parser.add_argument("--dry-run", action="store_true",
                        help="生成のみ・Threads 投稿しない")
    args = parser.parse_args()

    # 1. 集計
    stats = collect_week_stats(args.week)
    start, end = get_week_range(args.week)
    print(f"\n{'='*54}")
    print(f"  週次まとめ生成: {stats['start']} 〜 {stats['end']}")
    print(f"{'='*54}")
    print(f"  Threads: {stats['threads_total']}件  Instagram: {stats['ig_total']}件  補足コメント: {stats['with_comment']}件")
    print("  テーマ内訳:")
    for k, v in stats["theme_counts"].items():
        print(f"    {THEME_LABELS.get(k, k)}: {v}件")
    print(f"{'='*54}\n")

    if stats["threads_total"] == 0 and stats["ig_total"] == 0:
        print("この週の投稿ログが見つかりませんでした。")
        sys.exit(0)

    # 2. コンテンツ生成
    print("Claude Haiku でまとめ文を生成中...")
    summary_text = generate_summary(stats)

    print(f"\n{'─'*54}")
    print(summary_text)
    print(f"{'─'*54}")
    print(f"（{len(summary_text)}字）\n")

    # 3. 投稿
    post_id = None
    if args.post and not args.dry_run:
        if not TH_USER_ID or not TH_TOKEN:
            print("エラー: THREADS_USER_ID / THREADS_ACCESS_TOKEN が未設定です", file=sys.stderr)
            sys.exit(1)
        post_id = post_summary_to_threads(summary_text)
    elif not args.post:
        print("プレビューモード。--post を付けると Threads に投稿します。")

    # 4. ログ
    log_summary(stats, summary_text, post_id)


if __name__ == "__main__":
    main()
