import os
import json
import requests
from dotenv import load_dotenv
from discord_notify import send_instagram_likes, send_alert

load_dotenv(os.path.expanduser("~/Documents/Obsidian Vault/.env"))

def get_like_candidates():
    """競合分析・バズ分析からいいね候補を生成"""
    candidates = []

    # 競合アカウント分析から取得
    competitor_path = os.path.join(os.path.dirname(__file__), "config/competitor_analysis.json")
    if os.path.exists(competitor_path):
        with open(competitor_path, "r") as f:
            data = json.load(f)
        accounts = data if isinstance(data, list) else data.get("accounts", [])
        for acc in accounts[:5]:
            username = acc.get("username") or acc.get("account", "")
            if username:
                candidates.append({
                    "account": f"@{username.lstrip('@')}",
                    "url": f"https://www.instagram.com/{username.lstrip('@')}/",
                    "reason": acc.get("reason") or acc.get("description") or "競合アカウント・エンゲージ確認推奨"
                })

    # バズ分析から取得
    buzz_path = os.path.join(os.path.dirname(__file__), "config/buzz_analysis.json")
    if os.path.exists(buzz_path):
        with open(buzz_path, "r") as f:
            buzz = json.load(f)
        posts = buzz if isinstance(buzz, list) else buzz.get("posts", [])
        for post in posts[:3]:
            url = post.get("url") or post.get("link", "")
            account = post.get("account") or post.get("username", "")
            reason = post.get("reason") or post.get("description") or "バズ投稿・いいね推奨"
            if url or account:
                candidates.append({
                    "account": f"@{account.lstrip('@')}" if account else "バズ投稿",
                    "url": url or f"https://www.instagram.com/{account.lstrip('@')}/",
                    "reason": reason
                })

    return candidates

def run():
    print("=== Instagram いいね候補生成 ===")
    try:
        candidates = get_like_candidates()
        if not candidates:
            send_alert("いいね候補データが見つかりませんでした", level="warning")
            return
        send_instagram_likes(candidates)
        print(f"=== {len(candidates)}件送信完了 ===")
    except Exception as e:
        send_alert(f"Instagram いいね候補生成エラー: {str(e)}", level="error")

if __name__ == "__main__":
    run()
