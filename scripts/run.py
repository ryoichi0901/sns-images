"""
金融×AI副業 SNS自動化エージェントシステム
メインエントリポイント

使い方:
  python3 scripts/run.py                           # 全プラットフォームに単枚投稿
  python3 scripts/run.py --carousel                # Instagramをカルーセル投稿（5〜7枚）
  python3 scripts/run.py --dry-run                 # 投稿せずコンテンツ確認のみ
  python3 scripts/run.py --carousel --dry-run      # カルーセル内容をプレビュー
  python3 scripts/run.py --summary                 # 投稿ログサマリー表示
  python3 scripts/run.py --weekday 1               # 曜日を手動指定（0=月〜6=日）
  python3 scripts/run.py --platforms ig th         # 特定プラットフォームのみ（ig/th/tw）
  python3 scripts/run.py --template myth_busting   # テンプレートを手動指定
  python3 scripts/run.py --list-templates          # テンプレート一覧を表示
"""
import argparse
import datetime
import os
import sys
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

import anthropic
from dotenv import load_dotenv

from agents.content_agent import generate_content, generate_carousel_content, list_templates
from agents.image_agent import generate_image, generate_carousel_images
from agents.post_agent import upload_to_cloudinary, publish_to_instagram, publish_carousel_to_instagram
from agents.threads_agent import publish_to_threads
from agents.twitter_agent import publish_to_twitter
from agents.analytics_agent import log_post, print_summary
from agents.affiliate_resolver import validate_env as validate_affiliate_env

ENV_PATH = os.path.expanduser("~/Documents/Obsidian Vault/.env")

# 必須 / プラットフォーム別オプション環境変数
REQUIRED_KEYS = [
    "ANTHROPIC_API_KEY",
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


def load_env() -> dict:
    load_dotenv(ENV_PATH)
    env = {}

    missing_required = [k for k in REQUIRED_KEYS if not os.getenv(k)]
    if missing_required:
        raise EnvironmentError(f"必須環境変数が未設定: {', '.join(missing_required)}")

    for k in REQUIRED_KEYS:
        env[k] = os.getenv(k)

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
    carousel: bool = False,
) -> None:
    print("\n=== 金融×AI副業 SNS自動化エージェントシステム ===\n")
    mode_label = "カルーセル" if carousel else "単枚"
    print(f"投稿モード: {mode_label}")

    env = load_env()
    today = datetime.date.today()
    date_str = today.strftime("%Y%m%d")
    wd = weekday if weekday is not None else today.weekday()
    requested = platforms or ["ig", "th", "tw"]

    day_names = ["月", "火", "水", "木", "金", "土", "日"]
    print(f"\n実行日: {today}（{day_names[wd]}曜日）")

    # Step 1: コンテンツ生成
    client = anthropic.Anthropic(api_key=env["ANTHROPIC_API_KEY"])
    if carousel:
        print("\n[Step 1] カルーセルコンテンツ生成...")
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
            return

        if len(slides) < 2:
            raise RuntimeError(f"カルーセルには最低2枚のスライドが必要です（生成数: {len(slides)}）")

        # Step 2: 全スライド画像生成
        print(f"\n[Step 2] カルーセル画像生成（{len(slides)}枚）...")
        image_paths = generate_carousel_images(slides, date_str)

        # Step 3: 全画像をCloudinaryにアップロード
        print(f"\n[Step 3] Cloudinaryにアップロード（{len(image_paths)}枚）...")
        image_urls: list[str] = []
        for i, path in enumerate(image_paths, 1):
            url = upload_to_cloudinary(
                path,
                cloud_name=env["CLOUDINARY_CLOUD_NAME"],
                api_key=env["CLOUDINARY_API_KEY"],
                api_secret=env["CLOUDINARY_API_SECRET"],
            )
            image_urls.append(url)
            print(f"  スライド{i}: {url}")

        active = _active_platforms(env, requested)
        instagram_id = threads_id = twitter_id = None

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

        # Step 4b: Threads投稿（表紙画像を添付）
        if "th" in active:
            print("\n[Step 4b] Threads投稿...")
            try:
                threads_id = publish_to_threads(
                    text=content["threads_text"],
                    weekday=wd,
                    user_id=env["THREADS_USER_ID"],
                    access_token=env["THREADS_ACCESS_TOKEN"],
                    image_url=image_urls[0],
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
            image_url=image_urls[0],
            caption_length=len(content["caption"]),
            template_used=content.get("template_used"),
        )

    else:
        # ---- 単枚投稿フロー（既存） ----
        print("\n[Step 1] コンテンツ生成（Instagram / Threads / X）...")
        content = generate_content(wd, client, template_id=template, date=today)
        print(f"  トピック   : {content['topic_summary']}")
        print(f"  テンプレート: {content.get('template_used', '-')}")
        print(f"  Instagram  : {len(content['caption'])}字")
        print(f"  Threads    : {len(content['threads_text'])}字")
        print(f"  X          : {len(content['tweet'])}字")

        if dry_run:
            _print_dry_run(content, wd)
            return

        # Step 2: 画像生成
        print("\n[Step 2] 画像生成...")
        image_path = generate_image(content["image_prompt"], date_str)

        # Step 3: 画像アップロード（Cloudinary）
        print("\n[Step 3] Cloudinaryにアップロード...")
        image_url = upload_to_cloudinary(
            image_path,
            cloud_name=env["CLOUDINARY_CLOUD_NAME"],
            api_key=env["CLOUDINARY_API_KEY"],
            api_secret=env["CLOUDINARY_API_SECRET"],
        )

        active = _active_platforms(env, requested)
        instagram_id = threads_id = twitter_id = None

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

        # Step 4b: Threads投稿
        if "th" in active:
            print("\n[Step 4b] Threads投稿...")
            try:
                threads_id = publish_to_threads(
                    text=content["threads_text"],
                    weekday=wd,
                    user_id=env["THREADS_USER_ID"],
                    access_token=env["THREADS_ACCESS_TOKEN"],
                    image_url=image_url,
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

    print(f"\n【カルーセルスライド構成（{len(slides)}枚）】")
    for slide in slides:
        print(f"\n  ── スライド{slide['slide_num']} ──")
        print(f"  見出し : {slide['headline']}")
        print(f"  本文   : {slide['body']}")
        print(f"  画像PRM: {slide['image_prompt']}")

    print("\n【Threads テキスト（アフィリエイトリンク付き）】")
    print(build_threads_text(content["threads_text"], weekday))

    print("\n【X(Twitter) ツイート（アフィリエイトURL付き）】")
    full_tweet = build_tweet_text(content["tweet"], weekday)
    print(full_tweet)
    print(f"（{len(full_tweet)}字）")

    print("\n[DRY RUN] 投稿はスキップしました。")


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
    parser.add_argument("--carousel", action="store_true", help="Instagramをカルーセル投稿（複数枚）にする")
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
        carousel=args.carousel,
    )


if __name__ == "__main__":
    main()
