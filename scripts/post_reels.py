"""
Instagram Reels 生成・投稿スクリプト
sns-orchestrator から呼ばれることを想定。
logs/research_context_YYYYMMDD.json が存在すれば自動読み込みして台本に反映する。

Usage:
  python3 scripts/post_reels.py             # 本番実行
  python3 scripts/post_reels.py --dry-run   # 台本生成のみ（動画・投稿なし）
  python3 scripts/post_reels.py --no-followup  # 補足コメントをスキップ
"""
import argparse
import datetime
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

import anthropic
from dotenv import load_dotenv

from agents.short_video_agent import generate_short_video_script, save_script
from agents.video_agent import render_reel_local
from agents.post_agent import upload_video_to_cloudinary, publish_reels_to_instagram
from agents.threads_agent import post_followup_comment

ENV_PATH = os.path.expanduser("~/Documents/Obsidian Vault/.env")
POST_LOG  = ROOT / "logs" / "post_log.jsonl"


def _get_today_threads_id() -> "str | None":
    """今日のThreads投稿IDを post_log.jsonl の最新エントリから取得する"""
    if not POST_LOG.exists():
        return None
    today = datetime.date.today().isoformat()
    latest: "str | None" = None
    with open(POST_LOG, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
                dt = entry.get("datetime", "")
                th = entry.get("platforms", {}).get("threads")
                if dt.startswith(today) and th:
                    latest = th
            except json.JSONDecodeError:
                pass
    return latest


def main() -> None:
    parser = argparse.ArgumentParser(description="Instagram Reels 生成・投稿")
    parser.add_argument("--dry-run",      action="store_true", help="台本生成のみ（動画・投稿なし）")
    parser.add_argument("--no-followup",  action="store_true", help="Threads補足コメントをスキップ")
    args = parser.parse_args()

    load_dotenv(ENV_PATH)

    api_key = os.getenv("ANTHROPIC_API_KEY", "")
    if not api_key:
        print("エラー: ANTHROPIC_API_KEY 未設定", file=sys.stderr)
        sys.exit(1)

    client = anthropic.Anthropic(api_key=api_key)
    today    = datetime.date.today()
    date_str = today.strftime("%Y%m%d")
    wd       = today.weekday()
    day_names = ["月", "火", "水", "木", "金", "土", "日"]

    print("\n=== Instagram Reels 生成・投稿 ===")
    print(f"実行日: {today}（{day_names[wd]}曜日）\n")

    # Step 1: 台本生成（research_context_YYYYMMDD.json を自動読み込み）
    print("[Step 1] ショート動画台本生成...")
    script = generate_short_video_script(wd, client)
    script_path = save_script(script, date=today)
    print(f"  タイトル : {script['title']}")
    print(f"  hook_sub : {script.get('hook_sub', '-')}")
    print(f"  シーン数 : {len(script.get('scenes', []))}シーン")
    print(f"  台本保存 : {script_path}")

    if args.dry_run:
        print("\n[DRY RUN] 動画生成・投稿はスキップします。")
        return

    # Step 2: FFmpegで動画生成（紺×金デザイン）
    print(f"\n[Step 2] FFmpegでリール動画生成（1080×1920 / 30fps）...")
    out_mp4 = ROOT / "output" / f"short_{date_str}.mp4"
    render_reel_local(script, out_mp4)

    # Step 3: Cloudinaryに動画アップロード
    cloud_name   = os.getenv("CLOUDINARY_CLOUD_NAME", "")
    cloud_key    = os.getenv("CLOUDINARY_API_KEY", "")
    cloud_secret = os.getenv("CLOUDINARY_API_SECRET", "")
    if not all([cloud_name, cloud_key, cloud_secret]):
        print("エラー: Cloudinary環境変数が未設定", file=sys.stderr)
        sys.exit(1)

    print("\n[Step 3] Cloudinaryに動画アップロード...")
    video_url = upload_video_to_cloudinary(out_mp4, cloud_name, cloud_key, cloud_secret)

    # Step 4: Instagram Reels投稿
    ig_token = os.getenv("INSTAGRAM_ACCESS_TOKEN", "")
    ig_id    = os.getenv("INSTAGRAM_BUSINESS_ID", "")
    if not all([ig_token, ig_id]):
        print("エラー: Instagram環境変数が未設定", file=sys.stderr)
        sys.exit(1)

    print("\n[Step 4] Instagram Reels投稿...")
    reels_id = publish_reels_to_instagram(
        video_url=video_url,
        caption=script["title"],
        ig_user_id=ig_id,
        access_token=ig_token,
    )
    print(f"  Reels ID: {reels_id}")

    # Step 5: 今日のThreads投稿に補足コメント（5分後）
    if not args.no_followup:
        threads_id = _get_today_threads_id()
        th_user    = os.getenv("THREADS_USER_ID", "")
        th_token   = os.getenv("THREADS_ACCESS_TOKEN", "")
        if threads_id and th_user and th_token:
            print(f"\n[Step 5] Threads補足コメント（対象: {threads_id}）...")
            post_followup_comment(
                post_id=threads_id,
                post_text=script["title"],
                user_id=th_user,
                access_token=th_token,
                client=client,
            )
        elif not threads_id:
            print("\n[Step 5] 今日のThreads投稿IDが未取得 → 補足コメントスキップ")
        else:
            print("\n[Step 5] Threads環境変数未設定 → 補足コメントスキップ")
    else:
        print("\n[Step 5] --no-followup → 補足コメントスキップ")

    print("\n=== Reels投稿完了 ===\n")


if __name__ == "__main__":
    main()
