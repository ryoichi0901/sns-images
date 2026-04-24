"""
Threads 下書き投稿スクリプト（補足コメント自動投稿機能付き）

Usage:
  python3 scripts/post_threads_drafts.py                       # 全投稿プレビュー
  python3 scripts/post_threads_drafts.py --post                # 全投稿＋5分後に補足コメント
  python3 scripts/post_threads_drafts.py --id 1                # 投稿①プレビュー
  python3 scripts/post_threads_drafts.py --id 1 --post         # 投稿①＋補足コメント
  python3 scripts/post_threads_drafts.py --id 1 --post --no-followup  # 投稿①のみ（コメントなし）
  python3 scripts/post_threads_drafts.py --add-comments        # 今日の投稿済み全件に補足コメント追加
  python3 scripts/post_threads_drafts.py --add-comments --id 1 # 投稿①だけ補足コメント追加
  python3 scripts/post_threads_drafts.py --list                # 一覧表示
"""
import argparse
import datetime
import json
import os
import sys
import time
from pathlib import Path

import anthropic
import requests
from dotenv import load_dotenv
from typing import Optional

load_dotenv(os.path.expanduser("~/Documents/Obsidian Vault/.env"))

TH_USER_ID   = os.getenv("THREADS_USER_ID")
TH_TOKEN     = os.getenv("THREADS_ACCESS_TOKEN")
ANTHROPIC_KEY= os.getenv("ANTHROPIC_API_KEY")

POSTS_PATH    = Path(__file__).parent.parent / "templates" / "threads_posts.json"
LOGS_DIR      = Path(__file__).parent.parent / "logs"
LOG_PATH      = LOGS_DIR / "threads_drafts_log.jsonl"
LOGS_DIR.mkdir(exist_ok=True)

FOLLOWUP_DELAY = 300  # 5分（秒）

# テーマ別 補足コメント生成方針
FOLLOWUP_POLICY = {
    "banking_secrets": "現場での具体的なエピソードを1つ追加する。銀行員として実際に見聞きしたこと。",
    "side_job":        "実際に使ったツールや手順を1つ具体化する。副業で実際にやったことの詳細。",
    "investment":      "銀行員目線の補足知識を1つ追加する。投資に関する実務経験や裏側の知識。",
}


# ── ユーティリティ ───────────────────────────────────────────────────────────────

def load_posts() -> list[dict]:
    with open(POSTS_PATH, encoding="utf-8") as f:
        return json.load(f)["posts"]


def build_text(post: dict) -> str:
    tags = " ".join(post.get("hashtags", []))
    return f"{post['text']}\n\n{tags}"


def preview_post(post: dict) -> None:
    print(f"\n{'─'*52}")
    print(f"  投稿 #{post['id']}  [{post['theme_group']}]  {post['title']}")
    print(f"{'─'*52}")
    print(build_text(post))
    print(f"{'─'*52}\n")


# ── メイン投稿 ────────────────────────────────────────────────────────────────────

def post_to_threads(post: dict) -> str:
    """Threads にテキスト投稿して投稿IDを返す"""
    r1 = requests.post(
        f"https://graph.threads.net/v1.0/{TH_USER_ID}/threads",
        data={"media_type": "TEXT", "text": build_text(post), "access_token": TH_TOKEN},
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
    print(f"✓ 投稿 #{post['id']} 完了: {post_id}")
    return post_id


# ── 補足コメント ──────────────────────────────────────────────────────────────────

def generate_followup_comment(post: dict) -> str:
    """Claude Haiku で補足コメントを自動生成する"""
    policy = FOLLOWUP_POLICY.get(post.get("theme_group", "side_job"),
                                  FOLLOWUP_POLICY["side_job"])

    prompt = f"""以下のThreads投稿に対する補足コメントを生成してください。

【元の投稿】
{post['text']}

【補足方針】
{policy}

【補足コメントの型】
「補足：〇〇（具体的なエピソードや数字）
〜という経験から、□□だと気づきました。」

【制約】
- 100〜150字以内
- ハッシュタグなし
- 一人称・体験談ベースで書く
- 捏造統計・根拠不明の数字は使わない（自分の体験のみ）
- 元の投稿内容と重複しない新しい視点を1つ加える

補足コメントの本文のみ出力してください。前置き・説明不要。"""

    client = anthropic.Anthropic(api_key=ANTHROPIC_KEY)
    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=300,
        messages=[{"role": "user", "content": prompt}],
    )
    comment = response.content[0].text.strip()
    char_count = len(comment)
    print(f"[Claude] 補足コメント生成完了: {char_count}字")
    if char_count > 150:
        print(f"  ※ 150字超のため末尾をトリム（{char_count}字→150字）")
        comment = comment[:150]
    return comment


def add_followup_comment(post_id: str, comment_text: str) -> str:
    """reply_to_id を使って補足コメントをリプライ投稿し、コメントIDを返す"""
    # Step1: コンテナ作成（reply_to_id 付き）
    r1 = requests.post(
        f"https://graph.threads.net/v1.0/{TH_USER_ID}/threads",
        data={
            "media_type":   "TEXT",
            "text":         comment_text,
            "reply_to_id":  post_id,
            "access_token": TH_TOKEN,
        },
        timeout=30,
    )
    r1.raise_for_status()
    container_id = r1.json()["id"]
    time.sleep(3)

    # Step2: 公開
    r2 = requests.post(
        f"https://graph.threads.net/v1.0/{TH_USER_ID}/threads_publish",
        data={"creation_id": container_id, "access_token": TH_TOKEN},
        timeout=30,
    )
    r2.raise_for_status()
    comment_id = r2.json()["id"]
    print(f"✓ 補足コメント投稿完了: {comment_id}")
    return comment_id


def run_followup(post: dict, post_id: str, delay: int = FOLLOWUP_DELAY) -> "Optional[str]":
    """補足コメントを生成・待機・投稿する。コメントIDを返す"""
    print(f"\n[補足コメント] {delay}秒後（{delay//60}分後）に投稿します...")
    for remaining in range(delay, 0, -30):
        print(f"  あと {remaining}秒...", end="\r")
        time.sleep(min(30, remaining))
    print()

    print("[補足コメント] コメント生成中...")
    comment_text = generate_followup_comment(post)
    print(f"\n{'·'*52}")
    print(comment_text)
    print(f"{'·'*52}\n")

    comment_id = add_followup_comment(post_id, comment_text)
    return comment_id


# ── ログ ──────────────────────────────────────────────────────────────────────────

def log_result(post: dict, post_id: str, comment_id: "Optional[str]" = None) -> None:
    entry = {
        "date":       datetime.date.today().isoformat(),
        "post_id":    post_id,
        "draft_id":   post["id"],
        "theme_group":post["theme_group"],
        "title":      post["title"],
        "comment_id": comment_id,
    }
    with open(LOG_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def load_today_logs() -> list[dict]:
    """今日の投稿ログを返す"""
    today = datetime.date.today().isoformat()
    if not LOG_PATH.exists():
        return []
    entries = []
    with open(LOG_PATH, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    e = json.loads(line)
                    if e.get("date") == today:
                        entries.append(e)
                except json.JSONDecodeError:
                    pass
    return entries


# ── メイン ────────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Threads 下書き投稿（補足コメント自動付与）")
    parser.add_argument("--id",           type=int, default=None,
                        help="投稿番号（省略時は全件）")
    parser.add_argument("--post",         action="store_true",
                        help="実際に投稿する（省略時はプレビューのみ）")
    parser.add_argument("--no-followup",  action="store_true",
                        help="補足コメントをスキップする")
    parser.add_argument("--add-comments", action="store_true",
                        help="今日投稿済みの件に補足コメントを追加する")
    parser.add_argument("--list",         action="store_true",
                        help="投稿一覧を表示して終了")
    args = parser.parse_args()

    posts = load_posts()

    # ── 一覧表示 ──
    if args.list:
        print(f"\n{'='*52}")
        print(f"  Threads 下書き一覧 ({len(posts)}件)")
        print(f"{'='*52}")
        for p in posts:
            print(f"  #{p['id']:2d}  [{p['theme_group']:18s}]  {p['title']}")
        print(f"{'='*52}\n")
        return

    # ── 今日の投稿済みに補足コメント追加 ──
    if args.add_comments:
        if not TH_USER_ID or not TH_TOKEN:
            print("エラー: THREADS_USER_ID / THREADS_ACCESS_TOKEN が未設定です", file=sys.stderr)
            sys.exit(1)

        today_logs = load_today_logs()
        if not today_logs:
            print("今日の投稿ログが見つかりません。")
            return

        targets_log = [e for e in today_logs
                       if args.id is None or e.get("draft_id") == args.id]
        if not targets_log:
            print(f"投稿 #{args.id} の今日のログが見つかりません。")
            return

        posts_by_id = {p["id"]: p for p in posts}

        print(f"\n{len(targets_log)}件に補足コメントを追加します...\n")
        for i, entry in enumerate(targets_log):
            draft_id = entry.get("draft_id")
            post_id  = entry["post_id"]
            post     = posts_by_id.get(draft_id, {
                "id": draft_id, "theme_group": entry.get("theme_group", "side_job"),
                "title": entry.get("title", ""), "text": entry.get("title", ""),
            })
            print(f"▶ 投稿 #{draft_id}「{entry['title']}」 (post_id: {post_id})")

            comment_text = generate_followup_comment(post)
            print(f"\n{'·'*52}")
            print(comment_text)
            print(f"{'·'*52}\n")

            comment_id = add_followup_comment(post_id, comment_text)

            # ログに comment_id を追記
            log_result(post, post_id, comment_id)

            if i < len(targets_log) - 1:
                print("次のコメントまで5秒待機...")
                time.sleep(5)

        print(f"\n✓ 全{len(targets_log)}件の補足コメント投稿完了。")
        return

    # ── 通常投稿フロー ──
    targets = [p for p in posts if args.id is None or p["id"] == args.id]
    if not targets:
        print(f"投稿 #{args.id} が見つかりません", file=sys.stderr)
        sys.exit(1)

    if not args.post:
        print(f"\n{'='*52}")
        followup_note = "（--no-followup なし → 5分後に補足コメント自動投稿）" if not args.no_followup else "（--no-followup あり → 補足コメントなし）"
        print(f"  プレビューモード  --post を付けると投稿 {followup_note}")
        print(f"{'='*52}")
        for p in targets:
            preview_post(p)
        return

    if not TH_USER_ID or not TH_TOKEN:
        print("エラー: THREADS_USER_ID / THREADS_ACCESS_TOKEN が未設定です", file=sys.stderr)
        sys.exit(1)

    print(f"\n{len(targets)}件を投稿します（補足コメント: {'なし' if args.no_followup else '5分後に自動投稿'}）...\n")

    for i, p in enumerate(targets):
        preview_post(p)
        post_id = post_to_threads(p)
        comment_id = None

        if not args.no_followup:
            comment_id = run_followup(p, post_id)

        log_result(p, post_id, comment_id)

        if i < len(targets) - 1:
            print("次の投稿まで10秒待機...")
            time.sleep(10)

    print(f"\n✓ 全{len(targets)}件の投稿が完了しました。")


if __name__ == "__main__":
    main()
