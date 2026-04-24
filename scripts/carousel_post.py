"""
Instagram カルーセル投稿スクリプト
Cloudinaryへのアップロード → Instagram Graph API v25.0 へのカルーセル投稿

Usage (CLI):
  python3 scripts/carousel_post.py --images img1.jpg img2.jpg ... --caption "テキスト"
  python3 scripts/carousel_post.py --images img1.jpg img2.jpg ... --caption "テキスト" --out result.json
"""
import argparse
import hashlib
import json
import os
import sys
import time
from pathlib import Path

import requests
from dotenv import load_dotenv

load_dotenv(os.path.expanduser("~/Documents/Obsidian Vault/.env"))

IG_USER_ID    = os.getenv("INSTAGRAM_BUSINESS_ID", "17841433555586625")
ACCESS_TOKEN  = os.getenv("INSTAGRAM_ACCESS_TOKEN") or os.getenv("IG_ACCESS_TOKEN")
CLOUD_NAME    = os.getenv("CLOUDINARY_CLOUD_NAME",  "dw6iu8dn9")
CLOUD_KEY     = os.getenv("CLOUDINARY_API_KEY",     "751867497883922")
CLOUD_SECRET  = os.getenv("CLOUDINARY_API_SECRET")

IG_API  = "https://graph.facebook.com/v25.0"
CDN_API = f"https://api.cloudinary.com/v1_1/{CLOUD_NAME}/image/upload"

LOGS_DIR = Path(__file__).parent.parent / "logs"
LOGS_DIR.mkdir(exist_ok=True)


def upload_to_cloudinary(image_path: str) -> str:
    """Cloudinaryに画像をアップロードしてセキュアURLを返す"""
    timestamp = str(int(time.time()))
    signature = hashlib.sha256(
        f"timestamp={timestamp}{CLOUD_SECRET}".encode()
    ).hexdigest()

    with open(image_path, "rb") as f:
        r = requests.post(
            CDN_API,
            data={"api_key": CLOUD_KEY, "timestamp": timestamp, "signature": signature},
            files={"file": f},
            timeout=60,
        )
    r.raise_for_status()
    url = r.json()["secure_url"]
    print(f"[carousel_post] ✓ Cloudinary: {Path(image_path).name} → {url}")
    return url


def create_carousel_item(image_url: str) -> str:
    """カルーセル用子メディアコンテナを作成してIDを返す"""
    r = requests.post(
        f"{IG_API}/{IG_USER_ID}/media",
        data={
            "image_url":        image_url,
            "is_carousel_item": "true",
            "access_token":     ACCESS_TOKEN,
        },
        timeout=30,
    )
    r.raise_for_status()
    cid = r.json()["id"]
    print(f"[carousel_post] 子コンテナ作成: {cid}")
    return cid


def create_carousel_container(children_ids: list, caption: str) -> str:
    """カルーセルコンテナを作成してIDを返す"""
    r = requests.post(
        f"{IG_API}/{IG_USER_ID}/media",
        data={
            "media_type":   "CAROUSEL",
            "children":     ",".join(children_ids),
            "caption":      caption,
            "access_token": ACCESS_TOKEN,
        },
        timeout=30,
    )
    if not r.ok:
        raise RuntimeError(
            f"カルーセルコンテナ作成失敗 ({r.status_code}): {r.text}"
        )
    cid = r.json()["id"]
    print(f"[carousel_post] カルーセルコンテナ作成: {cid}")
    return cid


def publish_carousel(container_id: str) -> str:
    """カルーセルコンテナを公開して投稿IDを返す"""
    r = requests.post(
        f"{IG_API}/{IG_USER_ID}/media_publish",
        data={"creation_id": container_id, "access_token": ACCESS_TOKEN},
        timeout=30,
    )
    if not r.ok:
        raise RuntimeError(
            f"カルーセル公開失敗 ({r.status_code}): {r.text}"
        )
    post_id = r.json()["id"]
    print(f"[carousel_post] ✓ 投稿完了: post_id={post_id}")
    return post_id


def post_carousel(image_paths: list, caption: str) -> str:
    """
    メイン関数。
    image_paths: ローカル画像パスのリスト（2〜10枚）
    caption:     投稿キャプション
    returns:     Instagram投稿ID
    """
    if not 2 <= len(image_paths) <= 10:
        raise ValueError(
            f"カルーセルは2〜10枚が必要です（指定: {len(image_paths)}枚）"
        )

    print(f"\n[carousel_post] 開始: {len(image_paths)}枚のカルーセル投稿")

    # Step1: Cloudinaryに全画像をアップロード
    print("\n--- Step1: Cloudinaryアップロード ---")
    image_urls = [upload_to_cloudinary(p) for p in image_paths]

    # Step2: 子コンテナを順番に作成
    print("\n--- Step2: 子コンテナ作成 ---")
    children_ids = []
    for i, url in enumerate(image_urls, 1):
        cid = create_carousel_item(url)
        children_ids.append(cid)
        if i < len(image_urls):
            time.sleep(2)

    print(f"\n[carousel_post] 子コンテナ処理待ち（15秒）...")
    time.sleep(15)

    # Step3: カルーセルコンテナ作成
    print("\n--- Step3: カルーセルコンテナ作成 ---")
    carousel_id = create_carousel_container(children_ids, caption)
    time.sleep(8)

    # Step4: 公開
    print("\n--- Step4: 公開 ---")
    post_id = publish_carousel(carousel_id)

    return post_id


def _log(post_id: str, image_paths: list, caption: str) -> None:
    """投稿結果をJSONLに追記"""
    import datetime
    entry = {
        "date":        datetime.date.today().isoformat(),
        "post_id":     post_id,
        "slide_count": len(image_paths),
        "caption":     caption[:80],
        "images":      [Path(p).name for p in image_paths],
    }
    log_path = LOGS_DIR / "carousel_log.jsonl"
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    print(f"[carousel_post] ログ記録: {log_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Instagram カルーセル投稿")
    parser.add_argument(
        "--images", nargs="+", required=True,
        help="画像ファイルパスのリスト（スペース区切り、2〜10枚）"
    )
    parser.add_argument(
        "--caption", required=True,
        help="Instagramキャプション"
    )
    parser.add_argument(
        "--out", default=None,
        help="結果JSONの出力先ファイルパス（省略可）"
    )
    args = parser.parse_args()

    try:
        post_id = post_carousel(args.images, args.caption)
        _log(post_id, args.images, args.caption)
        result = {
            "status":      "success",
            "post_id":     post_id,
            "slide_count": len(args.images),
        }
    except Exception as e:
        result = {"status": "error", "message": str(e)}
        print(f"\n[carousel_post] エラー: {e}", file=sys.stderr)
        sys.exit(1)

    print("\n" + json.dumps(result, ensure_ascii=False, indent=2))
    if args.out:
        Path(args.out).write_text(
            json.dumps(result, ensure_ascii=False, indent=2),
            encoding="utf-8"
        )
