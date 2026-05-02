import os
import json
import time
import requests
from dotenv import load_dotenv
from discord_notify import send_instagram_likes, send_alert

load_dotenv(os.path.expanduser("~/Documents/Obsidian Vault/.env"))

ACCESS_TOKEN = os.getenv("INSTAGRAM_ACCESS_TOKEN")
BUSINESS_ID = os.getenv("INSTAGRAM_BUSINESS_ID")

# チェックするハッシュタグ（追加・削除自由）
HASHTAGS = [
    "AI副業",
    "AI自動化",
    "生成AI副業",
    "資産形成",
    "副業初心者",
    "会社員副業",
    "NISA副業",
    "お金の勉強",
]

def get_hashtag_posts(hashtag: str) -> list:
    """ハッシュタグの最新投稿を取得"""
    try:
        # ハッシュタグIDを取得
        res = requests.get(
            "https://graph.facebook.com/v25.0/ig_hashtag_search",
            params={
                "user_id": BUSINESS_ID,
                "q": hashtag,
                "access_token": ACCESS_TOKEN,
            },
            timeout=10
        )
        data = res.json()
        if "data" not in data or not data["data"]:
            return []
        hashtag_id = data["data"][0]["id"]

        # 最新投稿を取得
        res2 = requests.get(
            f"https://graph.facebook.com/v25.0/{hashtag_id}/recent_media",
            params={
                "user_id": BUSINESS_ID,
                "fields": "id,media_type,permalink",
                "access_token": ACCESS_TOKEN,
                "limit": 3,
            },
            timeout=10
        )
        posts = res2.json().get("data", [])
        return [
            {
                "account": f"#{hashtag}",
                "url": p.get("permalink", ""),
                "reason": f"ハッシュタグ #{hashtag} の最新投稿（{p.get('media_type', '')}）"
            }
            for p in posts if p.get("permalink")
        ]
    except Exception as e:
        print(f"[WARN] #{hashtag} 取得失敗: {e}")
        return []

def run():
    print("=== Instagram いいね候補生成 ===")
    try:
        candidates = []
        for tag in HASHTAGS:
            posts = get_hashtag_posts(tag)
            candidates.extend(posts)
            time.sleep(1)  # レート制限対策

        if not candidates:
            send_alert("いいね候補が見つかりませんでした。APIトークンを確認してください。", level="warning")
            return

        # 最大10件に絞る
        send_instagram_likes(candidates[:10])
        print(f"=== {len(candidates[:10])}件送信完了 ===")
    except Exception as e:
        send_alert(f"Instagram いいね候補生成エラー: {str(e)}", level="error")

if __name__ == "__main__":
    run()
