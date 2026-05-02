import os
import json
from datetime import datetime
from dotenv import load_dotenv

load_dotenv(os.path.expanduser("~/Documents/Obsidian Vault/.env"))

COMPETITOR_PATH = "config/competitor_analysis.json"
BUZZ_PATH = "config/buzz_analysis.json"

def load_competitors():
    with open(COMPETITOR_PATH, "r") as f:
        return json.load(f)

def save_competitors(data):
    with open(COMPETITOR_PATH, "w") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def get_existing_handles(data):
    return {acc.get("handle", "").lstrip("@").lower() for acc in data.get("accounts", [])}

def run():
    print("=== 競合アカウントリスト更新 ===")
    data = load_competitors()
    existing = get_existing_handles(data)
    added = 0

    # バズ分析から新アカウント抽出
    if os.path.exists(BUZZ_PATH):
        with open(BUZZ_PATH, "r") as f:
            buzz = json.load(f)
        posts = buzz if isinstance(buzz, list) else buzz.get("posts", [])
        for post in posts:
            handle = (post.get("account") or post.get("username", "")).lstrip("@").lower()
            if handle and handle not in existing:
                data["accounts"].append({
                    "handle": handle,
                    "url": f"https://www.instagram.com/{handle}/",
                    "reason": f"バズ分析で発見（{datetime.now().strftime('%Y-%m-%d')}）",
                    "added_at": datetime.now().strftime("%Y-%m-%d")
                })
                existing.add(handle)
                added += 1
                print(f"追加: @{handle}")

    data["_meta"] = data.get("_meta", {})
    data["_meta"]["last_updated"] = datetime.now().strftime("%Y-%m-%d %H:%M")
    data["_meta"]["total_accounts"] = len(data["accounts"])
    save_competitors(data)
    print(f"=== 完了：{added}件追加、合計{len(data['accounts'])}件 ===")

if __name__ == "__main__":
    run()
