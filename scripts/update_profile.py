"""
Instagram / Threads プロフィール更新スクリプト
両プラットフォームのバイオを同一内容に統一する。

Usage:
  python3 scripts/update_profile.py              # Instagram + Threads 両方更新
  python3 scripts/update_profile.py --platform ig  # Instagram のみ
  python3 scripts/update_profile.py --platform th  # Threads のみ
  python3 scripts/update_profile.py --biography "テキスト"
  python3 scripts/update_profile.py --dry-run
"""
import argparse
import os
import sys
from dotenv import load_dotenv
import requests

load_dotenv(os.path.expanduser("~/Documents/Obsidian Vault/.env"))

# Instagram
IG_USER_ID    = os.getenv("INSTAGRAM_BUSINESS_ID") or os.getenv("IG_USER_ID")
IG_TOKEN      = os.getenv("INSTAGRAM_ACCESS_TOKEN") or os.getenv("IG_ACCESS_TOKEN")

# Threads
TH_USER_ID    = os.getenv("THREADS_USER_ID")
TH_TOKEN      = os.getenv("THREADS_ACCESS_TOKEN")

DEFAULT_BIOGRAPHY = (
    "副業で稼いで、NISAで増やす\n"
    "元銀行員が本音で教えます\n\n"
    "副業解禁3ヶ月→月5万 / 6ヶ月→月7万"
)


def update_instagram(biography: str, dry_run: bool = False) -> dict:
    """Instagram Business アカウントのバイオを更新する"""
    if not IG_USER_ID or not IG_TOKEN:
        print("[Instagram] スキップ: INSTAGRAM_BUSINESS_ID / INSTAGRAM_ACCESS_TOKEN 未設定")
        return {"status": "skipped"}

    if dry_run:
        print(f"[DRY RUN][Instagram] ユーザーID: {IG_USER_ID}")
        print(f"  バイオ:\n{biography}")
        return {"status": "dry_run"}

    r = requests.post(
        f"https://graph.facebook.com/v25.0/{IG_USER_ID}",
        data={"biography": biography, "access_token": IG_TOKEN},
        timeout=30,
    )
    if not r.ok:
        raise RuntimeError(f"[Instagram] 更新失敗 ({r.status_code}): {r.text}")

    print(f"✓ [Instagram] プロフィール更新完了")
    return r.json()


def update_threads(biography: str, dry_run: bool = False) -> dict:
    """Threads アカウントのバイオを更新する"""
    if not TH_USER_ID or not TH_TOKEN:
        print("[Threads] スキップ: THREADS_USER_ID / THREADS_ACCESS_TOKEN 未設定")
        return {"status": "skipped"}

    if dry_run:
        print(f"[DRY RUN][Threads] ユーザーID: {TH_USER_ID}")
        print(f"  バイオ:\n{biography}")
        return {"status": "dry_run"}

    r = requests.post(
        f"https://graph.threads.net/v1.0/{TH_USER_ID}",
        data={"biography": biography, "access_token": TH_TOKEN},
        timeout=30,
    )
    if not r.ok:
        raise RuntimeError(f"[Threads] 更新失敗 ({r.status_code}): {r.text}")

    print(f"✓ [Threads] プロフィール更新完了")
    return r.json()


def update_all(biography: str, platform: str = "both", dry_run: bool = False) -> None:
    """Instagram / Threads 両方（または片方）を更新する"""
    print(f"\n{'[DRY RUN] ' if dry_run else ''}プロフィール更新開始\n")
    print(f"{'='*50}")
    print(biography)
    print(f"{'='*50}\n")

    results = {}
    if platform in ("both", "ig"):
        results["instagram"] = update_instagram(biography, dry_run)
    if platform in ("both", "th"):
        results["threads"]   = update_threads(biography, dry_run)

    print("\n--- 結果 ---")
    for name, res in results.items():
        print(f"  {name}: {res.get('status', 'success')}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Instagram / Threads プロフィール更新")
    parser.add_argument(
        "--platform", choices=["both", "ig", "th"], default="both",
        help="更新対象: both（両方）/ ig（Instagram のみ）/ th（Threads のみ）"
    )
    parser.add_argument("--biography", default=DEFAULT_BIOGRAPHY, help="更新後のバイオ文")
    parser.add_argument("--dry-run", action="store_true", help="APIを呼ばずに内容確認のみ")
    args = parser.parse_args()

    update_all(args.biography, platform=args.platform, dry_run=args.dry_run)
