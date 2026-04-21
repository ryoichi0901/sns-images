"""
Instagram投稿エージェント
Cloudinaryへの画像アップロード → Instagram Graph APIへの投稿を担当。
"""
import hashlib
import time
from pathlib import Path
import requests


def upload_to_cloudinary(image_path: Path, cloud_name: str, api_key: str, api_secret: str) -> str:
    """CloudinaryにJPEG画像をアップロードし、公開URLを返す"""
    timestamp = str(int(time.time()))
    sig_base = f"timestamp={timestamp}{api_secret}"
    signature = hashlib.sha1(sig_base.encode()).hexdigest()

    with open(image_path, "rb") as f:
        r = requests.post(
            f"https://api.cloudinary.com/v1_1/{cloud_name}/image/upload",
            data={"api_key": api_key, "timestamp": timestamp, "signature": signature},
            files={"file": f},
            timeout=60,
        )
    r.raise_for_status()
    url = r.json()["secure_url"]
    print(f"[PostAgent] Cloudinaryアップロード完了: {url}")
    return url


def publish_to_instagram(image_url: str, caption: str, ig_user_id: str, access_token: str) -> str:
    """
    Instagram Business アカウントに画像を投稿し、投稿IDを返す。
    Step1: メディアコンテナ作成
    Step2: 公開
    """
    # Step1: コンテナ作成
    r1 = requests.post(
        f"https://graph.facebook.com/v25.0/{ig_user_id}/media",
        data={
            "image_url": image_url,
            "caption": caption,
            "access_token": access_token,
        },
        timeout=30,
    )
    r1.raise_for_status()
    container_id = r1.json()["id"]
    print(f"[PostAgent] コンテナ作成: {container_id}")

    # Instagram側の処理待ち
    time.sleep(5)

    # Step2: 公開
    r2 = requests.post(
        f"https://graph.facebook.com/v25.0/{ig_user_id}/media_publish",
        data={"creation_id": container_id, "access_token": access_token},
        timeout=30,
    )
    r2.raise_for_status()
    post_id = r2.json()["id"]
    print(f"[PostAgent] 投稿完了: {post_id}")
    return post_id


def _create_child_container(image_url: str, ig_user_id: str, access_token: str) -> str:
    """カルーセル用の子メディアコンテナを作成してIDを返す"""
    r = requests.post(
        f"https://graph.facebook.com/v25.0/{ig_user_id}/media",
        data={
            "image_url": image_url,
            "is_carousel_item": "true",
            "access_token": access_token,
        },
        timeout=30,
    )
    r.raise_for_status()
    return r.json()["id"]


def publish_carousel_to_instagram(
    image_urls: list[str],
    caption: str,
    ig_user_id: str,
    access_token: str,
) -> str:
    """
    Instagramにカルーセル投稿（複数枚画像）し、投稿IDを返す。
    Step1: 各画像の子コンテナ作成
    Step2: カルーセルコンテナ作成（media_type=CAROUSEL）
    Step3: 公開
    """
    if not 2 <= len(image_urls) <= 10:
        raise ValueError(f"カルーセルは2〜10枚が必要です（指定: {len(image_urls)}枚）")

    # Step1: 子コンテナを順番に作成（API安定のため各作成後に短いウェイト）
    child_ids: list[str] = []
    for i, url in enumerate(image_urls, 1):
        child_id = _create_child_container(url, ig_user_id, access_token)
        print(f"[PostAgent] スライド{i} 子コンテナ作成: {child_id}")
        child_ids.append(child_id)
        time.sleep(2)

    # 全子コンテナの処理完了を待つ
    print(f"[PostAgent] 子コンテナ処理待ち（15秒）...")
    time.sleep(15)

    # Step2: カルーセルコンテナ作成
    # Meta APIはカンマ区切り文字列で children を受け取る
    r2 = requests.post(
        f"https://graph.facebook.com/v25.0/{ig_user_id}/media",
        data={
            "media_type": "CAROUSEL",
            "children": ",".join(child_ids),
            "caption": caption,
            "access_token": access_token,
        },
        timeout=30,
    )
    if not r2.ok:
        raise RuntimeError(
            f"カルーセルコンテナ作成失敗 ({r2.status_code}): {r2.text}"
        )
    carousel_id = r2.json()["id"]
    print(f"[PostAgent] カルーセルコンテナ作成: {carousel_id}")

    # Instagram側の処理待ち
    time.sleep(8)

    # Step3: 公開
    r3 = requests.post(
        f"https://graph.facebook.com/v25.0/{ig_user_id}/media_publish",
        data={"creation_id": carousel_id, "access_token": access_token},
        timeout=30,
    )
    if not r3.ok:
        raise RuntimeError(
            f"カルーセル公開失敗 ({r3.status_code}): {r3.text}"
        )
    post_id = r3.json()["id"]
    print(f"[PostAgent] カルーセル投稿完了: {post_id} （{len(image_urls)}枚）")
    return post_id


def get_recent_insights(ig_user_id: str, access_token: str, limit: int = 5) -> list[dict]:
    """直近の投稿インサイトを取得（フォロワーリーチ・インプレッション）"""
    r = requests.get(
        f"https://graph.facebook.com/v25.0/{ig_user_id}/media",
        params={
            "fields": "id,timestamp,like_count,comments_count",
            "limit": limit,
            "access_token": access_token,
        },
        timeout=30,
    )
    r.raise_for_status()
    return r.json().get("data", [])
