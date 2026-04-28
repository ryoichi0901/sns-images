"""
金融×AI副業 SNS自動化エージェントシステム
メインエントリポイント

使い方:
  python3 scripts/run.py                           # 全プラットフォームにカルーセル7枚投稿（デフォルト）
  python3 scripts/run.py --no-carousel             # 単枚投稿に切り替え
  python3 scripts/run.py --dry-run                 # 投稿せずコンテンツ確認のみ
  python3 scripts/run.py --summary                 # 投稿ログサマリー表示
  python3 scripts/run.py --weekday 1               # 曜日を手動指定（0=月〜6=日）
  python3 scripts/run.py --platforms ig th         # 特定プラットフォームのみ（ig/th/tw）
  python3 scripts/run.py --template myth_busting   # テンプレートを手動指定
  python3 scripts/run.py --list-templates          # テンプレート一覧を表示
"""
import argparse
import datetime
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

import anthropic
from dotenv import load_dotenv

from agents.content_agent import generate_content, generate_carousel_content, list_templates
from agents.image_agent import generate_image, generate_carousel_images
from agents.carousel_agent import capture_slides, capture_slides_dry_run
from agents.post_agent import (
    upload_to_cloudinary,
    upload_video_to_cloudinary,
    publish_to_instagram,
    publish_carousel_to_instagram,
    publish_reels_to_instagram,
)
from agents.short_video_agent import generate_short_video_script, save_script
from agents.threads_agent import publish_to_threads, post_followup_comment
# from agents.twitter_agent import publish_to_twitter
from agents.analytics_agent import log_post, print_summary
from agents.affiliate_resolver import validate_env as validate_affiliate_env

ENV_PATH = os.path.expanduser("~/Documents/Obsidian Vault/.env")
PREGENERATED_PATH = Path("/tmp/today_content.json")

# 必須 / プラットフォーム別オプション環境変数
REQUIRED_KEYS = [
    "ANTHROPIC_API_KEY",
]
CLOUDINARY_KEYS = [
    "CLOUDINARY_CLOUD_NAME",
    "CLOUDINARY_API_KEY",
    "CLOUDINARY_API_SECRET",
]
PLATFORM_KEYS = {
    "ig": [
        "INSTAGRAM_ACCESS_TOKEN",
        "INSTAGRAM_BUSINESS_ID",
    ],
    "th": [
        "THREADS_ACCESS_TOKEN",
        "THREADS_USER_ID",
    ],
    "tw": [
        "TWITTER_API_KEY",
        "TWITTER_API_SECRET",
        "TWITTER_ACCESS_TOKEN",
        "TWITTER_ACCESS_TOKEN_SECRET",
    ],
}
PLATFORM_NAMES = {"ig": "Instagram", "th": "Threads", "tw": "X(Twitter)"}


def load_env(dry_run: bool = False) -> dict:
    load_dotenv(ENV_PATH)
    env = {}

    missing_required = [k for k in REQUIRED_KEYS if not os.getenv(k)]
    if missing_required:
        raise EnvironmentError(f"必須環境変数が未設定: {', '.join(missing_required)}")

    for k in REQUIRED_KEYS:
        env[k] = os.getenv(k)

    if not dry_run:
        missing_cloudinary = [k for k in CLOUDINARY_KEYS if not os.getenv(k)]
        if missing_cloudinary:
            raise EnvironmentError(f"Cloudinary環境変数が未設定: {', '.join(missing_cloudinary)}")
        for k in CLOUDINARY_KEYS:
            env[k] = os.getenv(k)
    else:
        for k in CLOUDINARY_KEYS:
            env[k] = os.getenv(k) or ""

    for platform, keys in PLATFORM_KEYS.items():
        values = {k: os.getenv(k) for k in keys}
        if all(values.values()):
            env.update(values)
            print(f"[ENV] {PLATFORM_NAMES[platform]}: 設定済み ✓")
        else:
            missing = [k for k, v in values.items() if not v]
            print(f"[ENV] {PLATFORM_NAMES[platform]}: スキップ（未設定: {', '.join(missing)}）")

    # アフィリエイトリンクの設定状況を表示
    aff_status = validate_affiliate_env()
    aff_ok = [k for k, v in aff_status.items() if v]
    aff_ng = [k for k, v in aff_status.items() if not v]
    if aff_ng:
        print(f"[ENV] アフィリエイト: {len(aff_ok)}/{len(aff_status)}件設定済み（未設定: {', '.join(aff_ng)}）")
        print(f"      → 未設定のリンクは LINKTREE_URL にフォールバックします")
    else:
        print(f"[ENV] アフィリエイト: 全{len(aff_status)}件設定済み ✓")

    return env


def _load_pregenerated_content() -> "dict | None":
    """sns-orchestratorが /tmp/today_content.json に保存したコンテンツを読み込む。
    ファイルがない・必須フィールド不足の場合は None を返し独自生成にフォールバックする。"""
    if not PREGENERATED_PATH.exists():
        return None
    try:
        with open(PREGENERATED_PATH, encoding="utf-8") as f:
            content = json.load(f)
        required = {"caption", "threads_text", "tweet", "topic_summary"}
        missing = required - content.keys()
        if missing:
            print(f"[run] 事前生成ファイルにフィールド不足 {missing} → 独自生成にフォールバック")
            return None
        print(f"[run] 事前生成コンテンツを読み込み: {PREGENERATED_PATH}")
        print(f"  トピック   : {content.get('topic_summary', '-')}")
        print(f"  テンプレート: {content.get('template_used', '-')}")
        return content
    except Exception as e:
        print(f"[run] 事前生成ファイル読み込み失敗 → 独自生成にフォールバック: {e}")
        return None


def _active_platforms(env: dict, requested: "list[str]") -> "list[str]":
    """環境変数が揃っているプラットフォームのみ返す"""
    active = []
    for p in requested:
        if all(env.get(k) for k in PLATFORM_KEYS[p]):
            active.append(p)
    return active


def run(
    dry_run: bool = False,
    weekday: Optional[int] = None,
    platforms: "Optional[list[str]]" = None,
    template: Optional[str] = None,
    carousel: bool = True,
    short_video: bool = False,
    reels: bool = False,
    followup: bool = False,
) -> None:
    print("\n=== 金融×AI副業 SNS自動化エージェントシステム ===\n")
    mode_label = "カルーセル7枚" if carousel else "単枚"
    print(f"投稿モード: {mode_label}")

    env = load_env(dry_run=dry_run)
    today = datetime.date.today()
    date_str = today.strftime("%Y%m%d")
    wd = weekday if weekday is not None else today.weekday()
    requested = platforms or ["ig", "th", "tw"]

    day_names = ["月", "火", "水", "木", "金", "土", "日"]
    print(f"\n実行日: {today}（{day_names[wd]}曜日）")

    # Step 1: コンテンツ取得（事前生成ファイルを優先、なければ独自生成）
    client = anthropic.Anthropic(api_key=env["ANTHROPIC_API_KEY"])
    if carousel:
        print("\n[Step 1] カルーセルコンテンツ取得...")
        content = _load_pregenerated_content()
        if content is None:
            content = generate_carousel_content(wd, client, template_id=template, date=today)
        slides = content.get("carousel_slides", [])
        print(f"  トピック   : {content['topic_summary']}")
        print(f"  テンプレート: {content.get('template_used', '-')}")
        print(f"  スライド数 : {len(slides)}枚")
        print(f"  Instagram  : {len(content['caption'])}字")
        print(f"  Threads    : {len(content['threads_text'])}字")
        print(f"  X          : {len(content['tweet'])}字")

        if dry_run:
            _print_dry_run_carousel(content, wd)
            if short_video:
                _generate_and_print_short_video(wd, client, template, today)
            return

        if len(slides) < 2:
            raise RuntimeError(f"カルーセルには最低2枚のスライドが必要です（生成数: {len(slides)}）")

        active = _active_platforms(env, requested)
        instagram_id = threads_id = twitter_id = None
        image_urls: list[str] = []

        # Step 2 & 3: 画像が必要なプラットフォームがある場合のみ生成・アップロード
        if "ig" in active:
            print(f"\n[Step 2] カルーセル画像生成（{len(slides)}枚）— HTML→PNG変換...")
            image_paths = capture_slides(content, date_str)

            print(f"\n[Step 3] Cloudinaryにアップロード（{len(image_paths)}枚）...")
            for i, img_path in enumerate(image_paths, 1):
                url = upload_to_cloudinary(
                    img_path,
                    cloud_name=env["CLOUDINARY_CLOUD_NAME"],
                    api_key=env["CLOUDINARY_API_KEY"],
                    api_secret=env["CLOUDINARY_API_SECRET"],
                )
                image_urls.append(url)
                print(f"  スライド{i}: {url}")

        # Step 4a: Instagramカルーセル投稿
        if "ig" in active:
            print(f"\n[Step 4a] Instagramカルーセル投稿（{len(image_urls)}枚）...")
            try:
                instagram_id = publish_carousel_to_instagram(
                    image_urls=image_urls,
                    caption=content["caption"],
                    ig_user_id=env["INSTAGRAM_BUSINESS_ID"],
                    access_token=env["INSTAGRAM_ACCESS_TOKEN"],
                )
            except Exception as e:
                print(f"[Instagram] カルーセル投稿失敗: {e}")

        # Step 4b: Threadsテキストのみ投稿
        if "th" in active:
            print("\n[Step 4b] Threads投稿（テキストのみ）...")
            try:
                threads_id = publish_to_threads(
                    text=content["threads_text"],
                    weekday=wd,
                    user_id=env["THREADS_USER_ID"],
                    access_token=env["THREADS_ACCESS_TOKEN"],
                )
            except Exception as e:
                print(f"[Threads] 投稿失敗: {e}")

        # Step 4c: X(Twitter)投稿
        if "tw" in active:
            print("\n[Step 4c] X(Twitter)投稿...")
            try:
                twitter_id = publish_to_twitter(
                    tweet_text=content["tweet"],
                    weekday=wd,
                    api_key=env["TWITTER_API_KEY"],
                    api_secret=env["TWITTER_API_SECRET"],
                    access_token=env["TWITTER_ACCESS_TOKEN"],
                    access_token_secret=env["TWITTER_ACCESS_TOKEN_SECRET"],
                )
            except Exception as e:
                print(f"[Twitter] 投稿失敗: {e}")

        # Step 5: ログ記録
        log_post(
            topic_summary=content["topic_summary"],
            weekday=wd,
            instagram_id=instagram_id,
            threads_id=threads_id,
            twitter_id=twitter_id,
            image_url=image_urls[0] if image_urls else "",
            caption_length=len(content["caption"]),
            template_used=content.get("template_used"),
        )

        # Step 5.5: Threads補足コメント（投稿から5分後・--followup フラグ時）
        if followup and threads_id:
            try:
                post_followup_comment(
                    post_id=threads_id,
                    post_text=content["threads_text"],
                    user_id=env["THREADS_USER_ID"],
                    access_token=env["THREADS_ACCESS_TOKEN"],
                    client=client,
                )
            except Exception as e:
                print(f"[Followup] 補足コメント失敗（投稿は完了済み）: {e}")

        # Step 6: Pillow+FFmpegでリール動画生成 → Cloudinary → Instagram Reels投稿
        if reels and "ig" in active:
            print("\n[Step 6] リール動画生成（Pillow+FFmpeg）→ Instagram Reels投稿...")
            try:
                from agents.video_agent import render_reel_local
                reel_script = generate_short_video_script(
                    wd, client, template_id=template, date=today
                )
                script_path = save_script(reel_script, date=today)
                print(f"  台本保存: {script_path}")
                print(f"  タイトル: {reel_script.get('title', '-')}")
                print(f"  hook_sub: {reel_script.get('hook_sub', '-')}")

                out_mp4 = ROOT / "output" / f"short_{date_str}.mp4"
                render_reel_local(reel_script, out_mp4)

                video_url = upload_video_to_cloudinary(
                    out_mp4,
                    cloud_name=env["CLOUDINARY_CLOUD_NAME"],
                    api_key=env["CLOUDINARY_API_KEY"],
                    api_secret=env["CLOUDINARY_API_SECRET"],
                )
                publish_reels_to_instagram(
                    video_url=video_url,
                    caption=content["caption"],
                    ig_user_id=env["INSTAGRAM_BUSINESS_ID"],
                    access_token=env["INSTAGRAM_ACCESS_TOKEN"],
                )
            except Exception as e:
                print(f"[Reels] 失敗（メイン投稿は完了済み）: {e}")

    else:
        # ---- 単枚投稿フロー ----
        print("\n[Step 1] コンテンツ取得（Instagram / Threads / X）...")
        content = _load_pregenerated_content()
        if content is None:
            content = generate_content(wd, client, template_id=template, date=today)
        print(f"  トピック   : {content['topic_summary']}")
        print(f"  テンプレート: {content.get('template_used', '-')}")
        print(f"  Instagram  : {len(content['caption'])}字")
        print(f"  Threads    : {len(content['threads_text'])}字")
        print(f"  X          : {len(content['tweet'])}字")

        if dry_run:
            _print_dry_run(content, wd)
            if short_video:
                _generate_and_print_short_video(wd, client, template, today)
            return

        active = _active_platforms(env, requested)
        instagram_id = threads_id = twitter_id = None
        image_url = ""

        # Step 2 & 3: Instagramがある場合のみ画像生成・アップロード
        if "ig" in active:
            print("\n[Step 2] 画像生成...")
            image_path = generate_image(content["image_prompt"], date_str)

            print("\n[Step 3] Cloudinaryにアップロード...")
            image_url = upload_to_cloudinary(
                image_path,
                cloud_name=env["CLOUDINARY_CLOUD_NAME"],
                api_key=env["CLOUDINARY_API_KEY"],
                api_secret=env["CLOUDINARY_API_SECRET"],
            )

        # Step 4a: Instagram投稿
        if "ig" in active:
            print("\n[Step 4a] Instagram投稿...")
            try:
                instagram_id = publish_to_instagram(
                    image_url=image_url,
                    caption=content["caption"],
                    ig_user_id=env["INSTAGRAM_BUSINESS_ID"],
                    access_token=env["INSTAGRAM_ACCESS_TOKEN"],
                )
            except Exception as e:
                print(f"[Instagram] 投稿失敗: {e}")

        # Step 4b: Threadsテキストのみ投稿
        if "th" in active:
            print("\n[Step 4b] Threads投稿（テキストのみ）...")
            try:
                threads_id = publish_to_threads(
                    text=content["threads_text"],
                    weekday=wd,
                    user_id=env["THREADS_USER_ID"],
                    access_token=env["THREADS_ACCESS_TOKEN"],
                )
            except Exception as e:
                print(f"[Threads] 投稿失敗: {e}")

        # Step 4c: X(Twitter)投稿
        if "tw" in active:
            print("\n[Step 4c] X(Twitter)投稿...")
            try:
                twitter_id = publish_to_twitter(
                    tweet_text=content["tweet"],
                    weekday=wd,
                    api_key=env["TWITTER_API_KEY"],
                    api_secret=env["TWITTER_API_SECRET"],
                    access_token=env["TWITTER_ACCESS_TOKEN"],
                    access_token_secret=env["TWITTER_ACCESS_TOKEN_SECRET"],
                )
            except Exception as e:
                print(f"[Twitter] 投稿失敗: {e}")

        # Step 5: ログ記録
        log_post(
            topic_summary=content["topic_summary"],
            weekday=wd,
            instagram_id=instagram_id,
            threads_id=threads_id,
            twitter_id=twitter_id,
            image_url=image_url,
            caption_length=len(content["caption"]),
            template_used=content.get("template_used"),
        )

        # Step 5.5: Threads補足コメント（投稿から5分後・--followup フラグ時）
        if followup and threads_id:
            try:
                post_followup_comment(
                    post_id=threads_id,
                    post_text=content["threads_text"],
                    user_id=env["THREADS_USER_ID"],
                    access_token=env["THREADS_ACCESS_TOKEN"],
                    client=client,
                )
            except Exception as e:
                print(f"[Followup] 補足コメント失敗（投稿は完了済み）: {e}")

    # ショート動画台本生成（--short-video フラグ時）
    if short_video:
        print("\n[Step SV] ショート動画台本生成（共感→ストーリー→CTA）...")
        try:
            script = generate_short_video_script(wd, client, template_id=template, date=today)
            script_path = save_script(script, date=today)
            print(f"  タイトル: {script['title']}")
            print(f"  シーン数: {len(script['scenes'])}シーン")
            print(f"  台本保存: {script_path}")
            print(f"  レンダリング: node scripts/render-short.js --script {script_path}")
        except Exception as e:
            print(f"[ShortVideo] 台本生成失敗: {e}")

    print_summary()
    print("=== 完了 ===\n")


def _print_dry_run(content: dict, weekday: int) -> None:
    from agents.threads_agent import build_threads_text
    from agents.twitter_agent import build_tweet_text

    print("\n" + "="*55)
    print("  [DRY RUN] コンテンツプレビュー（単枚）")
    print(f"  テンプレート: {content.get('template_used', '-')}")
    print("="*55)

    print("\n【Instagram キャプション】")
    print(content["caption"])

    print("\n【Threads テキスト（アフィリエイトリンク付き）】")
    print(build_threads_text(content["threads_text"], weekday))

    print("\n【X(Twitter) ツイート（アフィリエイトURL付き）】")
    full_tweet = build_tweet_text(content["tweet"], weekday)
    print(full_tweet)
    print(f"（{len(full_tweet)}字）")

    print("\n【画像プロンプト】")
    print(content["image_prompt"])
    print("\n[DRY RUN] 投稿はスキップしました。")


def _print_dry_run_carousel(content: dict, weekday: int) -> None:
    from agents.threads_agent import build_threads_text
    from agents.twitter_agent import build_tweet_text

    slides = content.get("carousel_slides", [])
    print("\n" + "="*60)
    print(f"  [DRY RUN] カルーセルコンテンツプレビュー（{len(slides)}枚）")
    print(f"  テンプレート: {content.get('template_used', '-')}")
    print("="*60)

    print("\n【Instagram キャプション（全体）】")
    print(content["caption"])

    print(f"\n【カルーセルスライド構成（{len(slides)}枚）— HTML→PNG変換予定】")
    capture_slides_dry_run(content)
    for slide in slides:
        print(f"\n  ── スライド{slide['slide_num']} ──")
        print(f"  見出し : {slide['headline']}")
        print(f"  本文   : {slide['body']}")

    print("\n【Threads テキスト（アフィリエイトリンク付き）】")
    print(build_threads_text(content["threads_text"], weekday))

    print("\n【X(Twitter) ツイート（アフィリエイトURL付き）】")
    full_tweet = build_tweet_text(content["tweet"], weekday)
    print(full_tweet)
    print(f"（{len(full_tweet)}字）")

    print("\n[DRY RUN] 投稿はスキップしました。")


def _generate_and_print_short_video(
    weekday: int,
    client,
    template: "Optional[str]",
    today: datetime.date,
) -> None:
    """ドライラン・実行両用のショート動画台本生成ヘルパー"""
    print("\n" + "="*60)
    print("  [SHORT VIDEO] 台本生成（共感→ストーリー→CTA）")
    print("="*60)
    try:
        script = generate_short_video_script(weekday, client, template_id=template, date=today)
        script_path = save_script(script, date=today)
        print(f"\n  タイトル : {script['title']}")
        for scene in script["scenes"]:
            print(f"\n  ── {scene['id']} ({scene['start']}〜{scene['end']}秒) ──")
            print(f"  テロップ : {scene['telop']}")
            print(f"  ナレーション: {scene['voice']}")
        print(f"\n  台本保存: {script_path}")
        print(f"  レンダリング: node scripts/render-short.js --script {script_path}")
    except Exception as e:
        print(f"  [ShortVideo] 台本生成失敗: {e}")


TEMPLATE_CHOICES = ["banker_secret", "income_report", "step_guide", "comparison", "myth_busting"]


def main() -> None:
    parser = argparse.ArgumentParser(description="金融×AI副業 SNS自動化エージェントシステム")
    parser.add_argument("--dry-run", action="store_true", help="投稿せずコンテンツ確認のみ")
    parser.add_argument("--summary", action="store_true", help="投稿ログサマリーを表示")
    parser.add_argument("--weekday", type=int, choices=range(7), help="曜日を手動指定（0=月〜6=日）")
    parser.add_argument(
        "--platforms", nargs="+", choices=["ig", "th", "tw"],
        help="投稿先を限定（ig=Instagram / th=Threads / tw=X）",
    )
    parser.add_argument(
        "--template", choices=TEMPLATE_CHOICES,
        help="投稿テンプレートを手動指定（省略時は日付で自動ローテーション）",
    )
    parser.add_argument("--list-templates", action="store_true", help="テンプレート一覧を表示")
    parser.add_argument("--no-carousel", action="store_true", help="カルーセルを無効化して単枚投稿にする（デフォルトはカルーセル7枚）")
    parser.add_argument("--short-video", action="store_true", help="ショート動画台本も生成する（共感→ストーリー→CTA構成）")
    parser.add_argument("--reels", action="store_true", help="Remotionでリール生成→Instagram Reels投稿も行う")
    parser.add_argument("--followup", action="store_true", help="Threads投稿の5分後に補足コメントを自動投稿する")
    args = parser.parse_args()

    if args.summary:
        print_summary(recent=14)
        return

    if args.list_templates:
        list_templates()
        return

    run(
        dry_run=args.dry_run,
        weekday=args.weekday,
        platforms=args.platforms,
        template=args.template,
        carousel=not args.no_carousel,
        short_video=args.short_video,
        reels=args.reels,
        followup=args.followup,
    )


if __name__ == "__main__":
    main()
