"""
Instagram Reels 生成・予約投稿スクリプト
07:00 JST の GitHub Actions ワークフローから呼ばれる。
当日 21:00 JST（12:00 UTC）に Instagram が自動公開する予約投稿を作成する。

フロー:
  1. Claude Haiku で台本生成（research_context_YYYYMMDD.json を自動読込）
  2. Pillow + FFmpeg で動画生成（1080x1920 / 30fps）
  3. Cloudinary に動画アップロード
  4. Instagram Graph API で scheduled_publish_time=21:00 JST の予約投稿
     → published=false のため media_publish 後も即時公開されない

Usage:
  python3 scripts/schedule_reels.py           # 本番実行
  python3 scripts/schedule_reels.py --dry-run # 台本・動画生成のみ（予約なし）
"""
import argparse
import datetime
import os
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

import anthropic
from dotenv import load_dotenv

from agents.short_video_agent import generate_short_video_script, save_script
from agents.video_agent import render_reel_local
from agents.post_agent import upload_video_to_cloudinary, schedule_reels_to_instagram
from agents.reels_agent import build_caption
from agents.buzz_analyzer import run_weekly_analysis, is_analysis_fresh

ENV_PATH = os.path.expanduser("~/Documents/Obsidian Vault/.env")
JST = datetime.timezone(datetime.timedelta(hours=9))
SCHEDULE_HOUR_JST = 21


def _scheduled_unix(today_jst: datetime.date) -> int:
    """当日 21:00 JST の Unix タイムスタンプを返す"""
    target = datetime.datetime(
        today_jst.year, today_jst.month, today_jst.day,
        SCHEDULE_HOUR_JST, 0, 0,
        tzinfo=JST,
    )
    now_jst = datetime.datetime.now(JST)
    if target <= now_jst:
        target += datetime.timedelta(days=1)
    return int(target.timestamp())


def main() -> None:
    parser = argparse.ArgumentParser(description="Instagram Reels 予約投稿（21:00 JST）")
    parser.add_argument("--dry-run", action="store_true", help="台本・動画生成のみ（Cloudinary・予約はスキップ）")
    args = parser.parse_args()

    load_dotenv(ENV_PATH)

    api_key = os.getenv("ANTHROPIC_API_KEY", "")
    if not api_key:
        print("エラー: ANTHROPIC_API_KEY 未設定", file=sys.stderr)
        sys.exit(1)

    client = anthropic.Anthropic(api_key=api_key)

    # GitHub Actions は UTC で動くため JST 日付を明示的に取得する
    now_jst = datetime.datetime.now(JST)
    today_jst = now_jst.date()
    date_str = today_jst.strftime("%Y%m%d")
    wd = today_jst.weekday()
    day_names = ["月", "火", "水", "木", "金", "土", "日"]

    scheduled_unix = _scheduled_unix(today_jst)
    scheduled_jst = datetime.datetime.fromtimestamp(scheduled_unix, tz=JST)

    print("\n=== Instagram Reels 予約投稿 ===")
    print(f"実行日時: {now_jst.strftime('%Y-%m-%d %H:%M JST')}（{day_names[wd]}曜日）")
    print(f"公開予定: {scheduled_jst.strftime('%Y-%m-%d %H:%M JST')} (Unix: {scheduled_unix})\n")

    # Step 0: バズ投稿分析（週1回・古い場合のみ実行）
    if not is_analysis_fresh():
        print("[Step 0] バズ投稿週次分析実行中...")
        threads_token = os.getenv("THREADS_ACCESS_TOKEN", "")
        threads_uid = os.getenv("THREADS_USER_ID", "")
        try:
            run_weekly_analysis(client, access_token=threads_token, user_id=threads_uid)
        except Exception as e:
            print(f"[Step 0] バズ分析失敗（続行）: {e}")
    else:
        print("[Step 0] バズ分析は最新（スキップ）")

    # Step 1: 台本生成（research_context_YYYYMMDD.json / buzz_analysis.json を自動読込）
    print("[Step 1] ショート動画台本生成...")
    script = generate_short_video_script(wd, client)
    script_path = save_script(script, date=today_jst)
    print(f"  タイトル : {script['title']}")
    print(f"  シーン数 : {len(script.get('scenes', []))}シーン")
    print(f"  台本保存 : {script_path}")

    # Step 2: FFmpegで動画生成
    print(f"\n[Step 2] FFmpegでリール動画生成（1080×1920 / 30fps）...")
    out_mp4 = ROOT / "output" / f"short_{date_str}.mp4"
    render_reel_local(script, out_mp4)
    print(f"  出力: {out_mp4}")

    if args.dry_run:
        print("\n[DRY RUN] Cloudinaryアップロード・予約投稿はスキップします。")
        return

    # Step 3: Cloudinaryに動画アップロード
    cloud_name = os.getenv("CLOUDINARY_CLOUD_NAME", "")
    cloud_key = os.getenv("CLOUDINARY_API_KEY", "")
    cloud_secret = os.getenv("CLOUDINARY_API_SECRET", "")
    if not all([cloud_name, cloud_key, cloud_secret]):
        print("エラー: Cloudinary環境変数が未設定", file=sys.stderr)
        sys.exit(1)

    print("\n[Step 3] Cloudinaryに動画アップロード...")
    video_url = upload_video_to_cloudinary(out_mp4, cloud_name, cloud_key, cloud_secret)

    # Step 4: 21:00 JST に予約投稿
    ig_token = os.getenv("INSTAGRAM_ACCESS_TOKEN", "")
    ig_id = os.getenv("INSTAGRAM_BUSINESS_ID", "")
    if not all([ig_token, ig_id]):
        print("エラー: Instagram環境変数が未設定", file=sys.stderr)
        sys.exit(1)

    print(f"\n[Step 4] Reels予約投稿（公開予定: {scheduled_jst.strftime('%Y-%m-%d %H:%M JST')}）...")
    caption = build_caption(script)
    try:
    except Exception as e:
        import sys
        print(f"[警告] Reels投稿スキップ: {e}", file=sys.stderr)
    post_id = schedule_reels_to_instagram(
        video_url=video_url,
        caption=caption,
        ig_user_id=ig_id,
        access_token=ig_token,
        scheduled_publish_time=scheduled_unix,
    )
    print(f"  予約ID  : {post_id}")
    print(f"  公開予定: {scheduled_jst.strftime('%Y-%m-%d %H:%M JST')}")
    print("\n=== Reels予約完了 ===\n")


if __name__ == "__main__":
    main()
