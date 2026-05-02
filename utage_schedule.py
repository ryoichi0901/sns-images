import os
import json
import requests
from datetime import datetime
from dotenv import load_dotenv
from discord_notify import send_utage_schedule, send_alert

load_dotenv(os.path.expanduser("~/Documents/Obsidian Vault/.env"))

UTAGE_API_KEY = os.getenv("UTAGE_API_KEY", "")
UTAGE_BASE_URL = "https://utage-system.com/api/v1"

def get_utage_schedule():
    """UTAGEから本日のスケジュールを取得"""
    if not UTAGE_API_KEY:
        # APIキーがない場合はサンプルデータ
        return [
            {"time": "確認できません", "name": "UTAGE_API_KEYを設定してください", "type": "設定エラー"}
        ]
    
    today = datetime.now().strftime("%Y-%m-%d")
    headers = {
        "Authorization": f"Bearer {UTAGE_API_KEY}",
        "Content-Type": "application/json"
    }
    
    try:
        res = requests.get(
            f"{UTAGE_BASE_URL}/schedules",
            headers=headers,
            params={"date": today},
            timeout=10
        )
        if res.status_code == 200:
            data = res.json()
            events = data if isinstance(data, list) else data.get("schedules", [])
            return [
                {
                    "time": e.get("time") or e.get("start_time", ""),
                    "name": e.get("name") or e.get("customer_name", ""),
                    "type": e.get("type") or e.get("session_type", "セッション")
                }
                for e in events
            ]
        else:
            return []
    except Exception as e:
        raise Exception(f"UTAGE API エラー: {str(e)}")

def run():
    print("=== UTAGEスケジュール取得 ===")
    try:
        events = get_utage_schedule()
        send_utage_schedule(events)
        print(f"=== {len(events)}件送信完了 ===")
    except Exception as e:
        send_alert(f"UTAGEスケジュール取得エラー: {str(e)}", level="error")

if __name__ == "__main__":
    run()
