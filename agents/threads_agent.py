"""
Threadsエージェント
Threads Graph APIを使い、テキスト（+画像オプション）を投稿する。
アフィリエイトリンクをテキスト末尾に付与。
"""
import time
from typing import Optional
import requests

from agents.affiliate_resolver import resolve_by_weekday, resolve_by_theme

THREADS_API = "https://graph.threads.net/v1.0"


def build_threads_text(base_text: str, weekday: int, theme: Optional[str] = None) -> str:
    """
    本文末尾にアフィリエイトリンクブロックを付与する。
    theme を指定するとテーマ優先でリンクを選択する。
    """
    aff = resolve_by_theme(theme) if theme else resolve_by_weekday(weekday)
    link_block = f"\n\n{aff['cta']}\n{aff['label']}\n{aff['url']}"
    return base_text + link_block


def publish_to_threads(
    text: str,
    weekday: int,
    user_id: str,
    access_token: str,
    image_url: Optional[str] = None,
    theme: Optional[str] = None,
) -> str:
    """
    Threads に投稿し、投稿IDを返す。
    image_url が指定された場合は画像付き投稿、なければテキストのみ。
    theme を指定するとテーマ優先のアフィリエイトリンクを付与する。
    """
    full_text = build_threads_text(text, weekday, theme=theme)

    # Step1: コンテナ作成
    payload: dict = {"text": full_text, "access_token": access_token}
    if image_url:
        payload["media_type"] = "IMAGE"
        payload["image_url"] = image_url
    else:
        payload["media_type"] = "TEXT"

    r1 = requests.post(
        f"{THREADS_API}/{user_id}/threads",
        data=payload,
        timeout=30,
    )
    r1.raise_for_status()
    container_id = r1.json()["id"]
    print(f"[ThreadsAgent] コンテナ作成: {container_id}")

    time.sleep(3)

    # Step2: 公開
    r2 = requests.post(
        f"{THREADS_API}/{user_id}/threads_publish",
        data={"creation_id": container_id, "access_token": access_token},
        timeout=30,
    )
    r2.raise_for_status()
    post_id = r2.json()["id"]
    print(f"[ThreadsAgent] 投稿完了: {post_id}")
    return post_id
