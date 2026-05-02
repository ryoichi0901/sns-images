"""
いいね対象リスト生成スクリプト
毎日 20:00 JST に GitHub Actions から実行される。

フロー:
  1. Instagram Graph API でハッシュタグ検索（最大5件/キーワード）
  2. Threads 公式 API でハッシュタグ検索（最大5件/キーワード）
  3. 副業単体のみの低品質投稿を除外
  4. logs/like_targets_YYYYMMDD.md に出力（手動でいいね）

Usage:
  python3 scripts/generate_like_targets.py           # 本番実行
  python3 scripts/generate_like_targets.py --dry-run # 検索のみ（Markdown出力なし）
"""
import argparse
import datetime
import json
import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

import requests
from dotenv import load_dotenv

ENV_PATH = os.path.expanduser("~/Documents/Obsidian Vault/.env")
LOGS_DIR = ROOT / "logs"
IG_HASHTAG_CACHE = LOGS_DIR / "ig_hashtag_ids.json"
JST = datetime.timezone(datetime.timedelta(hours=9))

# Instagram Graph API のユニークハッシュタグ検索は週30件まで。
# キャッシュ（ig_hashtag_ids.json）にIDを保存し ig_hashtag_search の消費を抑える。
KEYWORDS: list[str] = [
    "AI副業", "AI自動化", "AIビジネス", "生成AI副業",
    "NISA副業", "積立NISA", "資産形成", "資産運用",
    "お金の勉強", "会社員副業", "副業初心者", "複業",
    "ダブルワーク", "稼ぐ力",
]

MAX_PER_KEYWORD = 5
IG_API = "https://graph.facebook.com/v25.0"
TH_API = "https://graph.threads.net/v1.0"


@dataclass
class LikeTarget:
    platform: str
    keyword: str
    username: str
    url: str
    caption_head: str  # キャプション冒頭150文字
    format_type: str = "フィード"  # フィード / 動画・リール / カルーセル


def _is_quality_post(caption: str) -> bool:
    """副業単体のみ含む投稿を除外する。KEYWORDS のいずれかが含まれれば有効。"""
    if not caption:
        return True
    return any(kw in caption for kw in KEYWORDS)


# ---------- Instagram ----------

def _load_ig_hashtag_cache() -> dict[str, str]:
    if IG_HASHTAG_CACHE.exists():
        return json.loads(IG_HASHTAG_CACHE.read_text(encoding="utf-8"))
    return {}


def _save_ig_hashtag_cache(cache: dict[str, str]) -> None:
    LOGS_DIR.mkdir(exist_ok=True)
    IG_HASHTAG_CACHE.write_text(
        json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def _get_ig_hashtag_id(
    keyword: str, ig_user_id: str, access_token: str, cache: dict[str, str]
) -> str | None:
    if keyword in cache:
        return cache[keyword]
    r = requests.get(
        f"{IG_API}/ig_hashtag_search",
        params={"user_id": ig_user_id, "q": keyword, "access_token": access_token},
        timeout=15,
    )
    if not r.ok:
        print(f"  [IG] ハッシュタグID取得失敗 #{keyword}: {r.text[:120]}")
        return None
    data = r.json().get("data", [])
    if not data:
        return None
    hashtag_id = data[0]["id"]
    cache[keyword] = hashtag_id
    return hashtag_id


def fetch_ig_targets(ig_user_id: str, access_token: str) -> list[LikeTarget]:
    cache = _load_ig_hashtag_cache()
    targets: list[LikeTarget] = []
    seen_urls: set[str] = set()

    for keyword in KEYWORDS:
        print(f"[IG] #{keyword} 検索中...")
        hashtag_id = _get_ig_hashtag_id(keyword, ig_user_id, access_token, cache)
        if not hashtag_id:
            time.sleep(1)
            continue

        r = requests.get(
            f"{IG_API}/{hashtag_id}/recent_media",
            params={
                "user_id": ig_user_id,
                "fields": "id,caption,permalink,timestamp,media_type",
                "access_token": access_token,
            },
            timeout=15,
        )
        if not r.ok:
            print(f"  [IG] recent_media 失敗 #{keyword}: {r.text[:120]}")
            time.sleep(1)
            continue

        count = 0
        for post in r.json().get("data", []):
            if count >= MAX_PER_KEYWORD:
                break
            url = post.get("permalink", "")
            caption = post.get("caption", "") or ""
            if url in seen_urls or not _is_quality_post(caption):
                continue
            seen_urls.add(url)
            media_type = post.get("media_type", "IMAGE")
            format_type = (
                "動画・リール" if media_type == "VIDEO"
                else "カルーセル" if media_type == "CAROUSEL_ALBUM"
                else "フィード"
            )
            targets.append(LikeTarget(
                platform="Instagram",
                keyword=keyword,
                username="",  # recent_media は username を返さない
                url=url,
                caption_head=caption[:150],
                format_type=format_type,
            ))
            count += 1

        print(f"  → {count} 件取得")
        time.sleep(1)

    _save_ig_hashtag_cache(cache)
    return targets


# ---------- Threads ----------

def fetch_threads_targets(threads_user_id: str, access_token: str) -> list[LikeTarget]:
    targets: list[LikeTarget] = []
    seen_urls: set[str] = set()

    for keyword in KEYWORDS:
        print(f"[Threads] #{keyword} 検索中...")
        r = requests.get(
            f"{TH_API}/threads/search",
            params={
                "q": keyword,
                "search_type": "HASHTAG",
                "fields": "id,text,permalink,timestamp,username",
                "access_token": access_token,
            },
            timeout=15,
        )
        if not r.ok:
            print(f"  [Threads] 検索失敗 #{keyword}: {r.text[:120]}")
            time.sleep(1)
            continue

        count = 0
        for post in r.json().get("data", []):
            if count >= MAX_PER_KEYWORD:
                break
            url = post.get("permalink", "")
            text = post.get("text", "") or ""
            username = post.get("username", "")
            if url in seen_urls or not _is_quality_post(text):
                continue
            seen_urls.add(url)
            targets.append(LikeTarget(
                platform="Threads",
                keyword=keyword,
                username=f"@{username}" if username else "",
                url=url,
                caption_head=text[:150],
            ))
            count += 1

        print(f"  → {count} 件取得")
        time.sleep(1)

    return targets


# ---------- Markdown出力 ----------

def write_markdown(targets: list[LikeTarget], today: datetime.date) -> Path:
    LOGS_DIR.mkdir(exist_ok=True)
    out = LOGS_DIR / f"like_targets_{today.strftime('%Y%m%d')}.md"
    now_jst = datetime.datetime.now(JST)

    ig_targets = [t for t in targets if t.platform == "Instagram"]
    th_targets = [t for t in targets if t.platform == "Threads"]

    lines: list[str] = [
        f"# いいね対象リスト {today.strftime('%Y-%m-%d')}",
        "",
        (
            f"生成: {now_jst.strftime('%Y-%m-%d %H:%M JST')}"
            f" / Instagram {len(ig_targets)}件・Threads {len(th_targets)}件"
        ),
        "",
        "> **手順:** 各投稿を確認 → いいねしたらチェックボックスをつける",
        "",
        "---",
        "",
    ]

    for platform, group in [("Instagram", ig_targets), ("Threads", th_targets)]:
        if not group:
            continue
        lines += [f"## {platform} ({len(group)}件)", ""]
        for i, t in enumerate(group, 1):
            author_str = f" &nbsp; `{t.username}`" if t.username else ""
            lines += [
                f"### {i}. #{t.keyword} `{t.format_type}`{author_str}",
                "",
                f"🔗 {t.url}",
                "",
                f"> {t.caption_head or '（キャプションなし）'}",
                "",
                "- [ ] いいね済み",
                "",
            ]
        lines += ["---", ""]

    out.write_text("\n".join(lines), encoding="utf-8")
    return out


# ---------- Slack通知 ----------

def _send_slack_notification(targets: list[LikeTarget], today: datetime.date) -> None:
    webhook_url = os.getenv("SLACK_WEBHOOK_URL", "")
    if not webhook_url:
        print("[Slack] SLACK_WEBHOOK_URL 未設定 → スキップ")
        return

    ig_count = sum(1 for t in targets if t.platform == "Instagram")
    th_count = sum(1 for t in targets if t.platform == "Threads")
    reels_count = sum(1 for t in targets if t.format_type == "動画・リール")

    repo = "ryoichi0901/sns-images"
    date_str = today.strftime("%Y%m%d")
    file_url = f"https://github.com/{repo}/blob/main/logs/like_targets_{date_str}.md"

    text = (
        f"👍 *いいね対象リスト {today.strftime('%Y-%m-%d')}*\n"
        f"Instagram {ig_count}件（うちリール {reels_count}件）/ Threads {th_count}件\n"
        f"<{file_url}|リストを開く>"
    )
    try:
        r = requests.post(webhook_url, json={"text": text}, timeout=10)
        if r.ok:
            print(f"[Slack] 通知送信完了")
        else:
            print(f"[Slack] 通知失敗: {r.status_code} {r.text[:80]}")
    except Exception as e:
        print(f"[Slack] 通知エラー: {e}")


# ---------- エントリポイント ----------

def main() -> None:
    parser = argparse.ArgumentParser(description="いいね対象リスト生成（Instagram + Threads）")
    parser.add_argument("--dry-run", action="store_true", help="検索のみ（Markdown出力なし）")
    args = parser.parse_args()

    load_dotenv(ENV_PATH)

    ig_token = os.getenv("INSTAGRAM_ACCESS_TOKEN", "")
    ig_id = os.getenv("INSTAGRAM_BUSINESS_ID", "")
    th_token = os.getenv("THREADS_ACCESS_TOKEN", "")
    th_uid = os.getenv("THREADS_USER_ID", "")

    today = datetime.datetime.now(JST).date()
    print(f"\n=== いいね対象リスト生成 {today} ===\n")

    targets: list[LikeTarget] = []

    if ig_token and ig_id:
        print("--- Instagram ---")
        ig_results = fetch_ig_targets(ig_id, ig_token)
        targets.extend(ig_results)
        print(f"Instagram 合計: {len(ig_results)} 件\n")
    else:
        print("[IG] INSTAGRAM_ACCESS_TOKEN / INSTAGRAM_BUSINESS_ID 未設定 → スキップ\n")

    if th_token and th_uid:
        print("--- Threads ---")
        th_results = fetch_threads_targets(th_uid, th_token)
        targets.extend(th_results)
        print(f"Threads 合計: {len(th_results)} 件\n")
    else:
        print("[Threads] THREADS_ACCESS_TOKEN / THREADS_USER_ID 未設定 → スキップ\n")

    if not targets:
        print("対象投稿が見つかりませんでした。終了します。")
        sys.exit(0)

    if args.dry_run:
        print("[DRY RUN] Markdown出力をスキップします")
        return

    out = write_markdown(targets, today)
    print(f"=== 出力完了: {out} ({len(targets)} 件) ===\n")
    _send_slack_notification(targets, today)


if __name__ == "__main__":
    main()
