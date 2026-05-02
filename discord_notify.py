import requests
import os
from datetime import datetime
from dotenv import load_dotenv

load_dotenv(os.path.expanduser("~/Documents/Obsidian Vault/.env"))

WEBHOOKS = {
    "fx":        os.getenv("DISCORD_WEBHOOK_FX"),
    "instagram": os.getenv("DISCORD_WEBHOOK_INSTAGRAM"),
    "utage":     os.getenv("DISCORD_WEBHOOK_UTAGE"),
    "alerts":    os.getenv("DISCORD_WEBHOOK_ALERTS"),
}

def send_embed(channel, title, description, fields=None, color=0x00b4d8):
    webhook_url = WEBHOOKS.get(channel)
    if not webhook_url:
        print(f"[ERROR] Webhook未設定: {channel}")
        return False
    embed = {
        "title": title,
        "description": description,
        "color": color,
        "footer": {"text": f"ryo-dashboard • {datetime.now().strftime('%Y/%m/%d %H:%M')}"},
    }
    if fields:
        embed["fields"] = fields
    res = requests.post(webhook_url, json={"embeds": [embed]})
    if res.status_code in (200, 204):
        print(f"[OK] Discord送信成功: #{channel}")
        return True
    else:
        print(f"[ERROR] {res.status_code} {res.text}")
        return False

def send_fx_analysis(symbol, price, change_pct, analysis, rsi=None, trend=None):
    color = 0x2ecc71 if change_pct >= 0 else 0xe74c3c
    arrow = "▲" if change_pct >= 0 else "▼"
    fields = [
        {"name": "💰 価格", "value": f"${price:,.2f}", "inline": True},
        {"name": "📈 前日比", "value": f"{arrow} {abs(change_pct):.2f}%", "inline": True},
    ]
    if rsi:
        fields.append({"name": "📊 RSI", "value": str(rsi), "inline": True})
    if trend:
        fields.append({"name": "🔍 トレンド", "value": trend, "inline": True})
    send_embed("fx", f"🟡 {symbol} 分析レポート", analysis, fields, color)

def send_instagram_likes(posts):
    if not posts:
        return
    description = "\n".join(
        [f"**{i+1}. {p['account']}**\n{p['reason']}\n{p['url']}" for i, p in enumerate(posts)]
    )
    send_embed("instagram", "📱 いいね候補リスト", description, color=0xe1306c)

def send_utage_schedule(events):
    if not events:
        send_embed("utage", "📅 本日のUTAGEスケジュール", "予定はありません", color=0x9b59b6)
        return
    fields = [{"name": f"⏰ {e['time']} | {e['type']}", "value": e['name'], "inline": False} for e in events]
    send_embed("utage", "📅 本日のUTAGEスケジュール", f"本日の予定：{len(events)}件", fields, 0x9b59b6)

def send_alert(message, level="info"):
    icons = {"info": "ℹ️", "warning": "⚠️", "error": "🚨"}
    colors = {"info": 0x3498db, "warning": 0xf39c12, "error": 0xe74c3c}
    send_embed("alerts", f"{icons.get(level,'ℹ️')} システム通知", message, color=colors.get(level, 0x3498db))
