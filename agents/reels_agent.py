"""
Instagram Reels投稿エージェント
Cloudinaryへの動画アップロード → Instagram Graph API経由でReels公開を担当。
"""
import hashlib
import json
import sys
import time
from pathlib import Path

import requests

# ポーリング設定
POLL_INTERVAL_SEC = 30
MAX_POLL_ATTEMPTS = 10
API_VERSION = "v21.0"


def upload_video_to_cloudinary(
    video_path: Path,
    cloud_name: str,
    api_key: str,
    api_secret: str,
) -> str:
    """CloudinaryにMP4動画をアップロードし、公開URLを返す"""
    timestamp = str(int(time.time()))
    sig_base = f"timestamp={timestamp}{api_secret}"
    signature = hashlib.sha1(sig_base.encode()).hexdigest()

    with open(video_path, "rb") as f:
        r = requests.post(
            f"https://api.cloudinary.com/v1_1/{cloud_name}/video/upload",
            data={"api_key": api_key, "timestamp": timestamp, "signature": signature},
            files={"file": f},
            timeout=120,
        )
    if not r.ok:
        raise RuntimeError(
            f"Cloudinaryアップロード失敗 ({r.status_code}): {r.text}"
        )
    secure_url = r.json()["secure_url"]
    print(f"[ReelsAgent] Cloudinaryアップロード完了: {secure_url}")
    return secure_url


def create_reels_container(
    video_url: str,
    caption: str,
    ig_user_id: str,
    access_token: str,
) -> str:
    """Reelsメディアコンテナを作成してcreation_idを返す"""
    r = requests.post(
        f"https://graph.facebook.com/{API_VERSION}/{ig_user_id}/media",
        data={
            "media_type": "REELS",
            "video_url": video_url,
            "caption": caption,
            "access_token": access_token,
        },
        timeout=30,
    )
    if not r.ok:
        raise RuntimeError(
            f"Reelsコンテナ作成失敗 ({r.status_code}): {r.text}"
        )
    creation_id = r.json()["id"]
    print(f"[ReelsAgent] コンテナ作成完了: {creation_id}")
    return creation_id


def wait_for_container_ready(
    creation_id: str,
    access_token: str,
) -> None:
    """
    コンテナのstatus_codeがFINISHEDになるまでポーリングする。
    POLL_INTERVAL_SEC 秒ごとに最大 MAX_POLL_ATTEMPTS 回試行。
    """
    for attempt in range(1, MAX_POLL_ATTEMPTS + 1):
        r = requests.get(
            f"https://graph.facebook.com/{API_VERSION}/{creation_id}",
            params={"fields": "status_code", "access_token": access_token},
            timeout=30,
        )
        if not r.ok:
            raise RuntimeError(
                f"ステータス取得失敗 ({r.status_code}): {r.text}"
            )
        status_code = r.json().get("status_code", "")
        print(
            f"[ReelsAgent] ポーリング {attempt}/{MAX_POLL_ATTEMPTS}: status_code={status_code}"
        )

        if status_code == "FINISHED":
            print("[ReelsAgent] コンテナ処理完了")
            return
        if status_code == "ERROR":
            raise RuntimeError("Reelsコンテナの処理がERRORステータスで終了しました")

        if attempt < MAX_POLL_ATTEMPTS:
            time.sleep(POLL_INTERVAL_SEC)

    raise TimeoutError(
        f"コンテナが{POLL_INTERVAL_SEC * MAX_POLL_ATTEMPTS}秒以内にFINISHEDになりませんでした"
    )


def publish_reels(
    creation_id: str,
    ig_user_id: str,
    access_token: str,
) -> str:
    """Reelsを公開してpost_idを返す"""
    r = requests.post(
        f"https://graph.facebook.com/{API_VERSION}/{ig_user_id}/media_publish",
        data={"creation_id": creation_id, "access_token": access_token},
        timeout=30,
    )
    if not r.ok:
        raise RuntimeError(
            f"Reels公開失敗 ({r.status_code}): {r.text}"
        )
    post_id = r.json()["id"]
    print(f"[ReelsAgent] Reels投稿完了: post_id={post_id}")
    return post_id


def build_caption(script: dict) -> str:
    """台本JSONからキャプション文字列を組み立てる"""
    title = script.get("title", "")
    reels_tags = script.get("hashtags", {}).get("reels", [])
    hashtag_block = "\n".join(reels_tags)
    return f"{title}\n\n{hashtag_block}"


def run(
    video_path: Path,
    script_path: Path,
    cloud_name: str,
    api_key: str,
    api_secret: str,
    ig_user_id: str,
    access_token: str,
) -> str:
    """
    Reels投稿フルフロー:
    1. Cloudinaryに動画アップロード
    2. Reelsコンテナ作成
    3. FINISHEDまでポーリング
    4. 公開
    """
    script = json.loads(script_path.read_text(encoding="utf-8"))
    caption = build_caption(script)
    print(f"[ReelsAgent] キャプション:\n{caption}\n")

    # Step1: Cloudinaryアップロード
    video_url = upload_video_to_cloudinary(video_path, cloud_name, api_key, api_secret)

    # Step2: コンテナ作成
    creation_id = create_reels_container(video_url, caption, ig_user_id, access_token)

    # Step3: 処理完了待ち
    wait_for_container_ready(creation_id, access_token)

    # Step4: 公開
    post_id = publish_reels(creation_id, ig_user_id, access_token)
    return post_id


if __name__ == "__main__":
    import os
    from dotenv import load_dotenv

    env_path = Path.home() / "Documents/Obsidian Vault/.env"
    load_dotenv(dotenv_path=env_path)

    required_vars = [
        "CLOUDINARY_CLOUD_NAME",
        "CLOUDINARY_API_KEY",
        "CLOUDINARY_API_SECRET",
        "IG_USER_ID",
        "IG_ACCESS_TOKEN",
    ]
    missing = [v for v in required_vars if not os.getenv(v)]
    if missing:
        print(f"[ReelsAgent] 環境変数が不足しています: {missing}", file=sys.stderr)
        sys.exit(1)

    post_id = run(
        video_path=Path("/Users/watanaberyouichi/Documents/ryo-sns-auto/output/short_20260423.mp4"),
        script_path=Path("/Users/watanaberyouichi/Documents/ryo-sns-auto/logs/script_20260423.json"),
        cloud_name=os.environ["CLOUDINARY_CLOUD_NAME"],
        api_key=os.environ["CLOUDINARY_API_KEY"],
        api_secret=os.environ["CLOUDINARY_API_SECRET"],
        ig_user_id=os.environ["IG_USER_ID"],
        access_token=os.environ["IG_ACCESS_TOKEN"],
    )
    print(f"[ReelsAgent] 完了: post_id={post_id}")
