import os
import time
import json
import re
import anthropic
import yfinance as yf
from dotenv import load_dotenv
from discord_notify import send_embed, send_alert

load_dotenv(os.path.expanduser("~/Documents/Obsidian Vault/.env"))

SYMBOLS = {
    "GOLD / XAU-USD": "GC=F",
    "USD/JPY":        "JPY=X",
    "BTC/USD":        "BTC-USD",
}

def get_price_data(ticker_symbol):
    ticker = yf.Ticker(ticker_symbol)
    hist = ticker.history(period="5d")
    if hist.empty:
        return None
    latest = hist.iloc[-1]
    prev = hist.iloc[-2] if len(hist) >= 2 else hist.iloc[-1]
    price = latest["Close"]
    change_pct = ((price - prev["Close"]) / prev["Close"]) * 100
    return {
        "price": round(float(price), 2),
        "change_pct": round(float(change_pct), 2),
        "high_5d": round(float(hist["High"].max()), 2),
        "low_5d": round(float(hist["Low"].min()), 2),
    }

def analyze_with_claude(name, data):
    client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
    prompt = f"""あなたはプロのFXトレーダーです。以下のデータを元に詳細な分析をしてください。

銘柄: {name}
現在価格: {data['price']}
前日比: {data['change_pct']}%
5日高値: {data['high_5d']}
5日安値: {data['low_5d']}

以下をJSON形式のみで返してください（他の文章不要）:
{{
  "trend": "上昇継続 / 下落継続 / レンジ / 反転注意 のいずれか",
  "rsi_1h": "1時間足RSIの推定値（数値のみ）",
  "rsi_4h": "4時間足RSIの推定値（数値のみ）",
  "rsi_1d": "日足RSIの推定値（数値のみ）",
  "analysis": "相場の全体感を2〜3文で（日本語）",
  "buy_entries": [
    {{
      "entry": "買いエントリー価格",
      "tp": "利確ライン",
      "sl": "損切りライン",
      "reason": "このエントリーの根拠（1〜2文）"
    }}
  ],
  "sell_entries": [
    {{
      "entry": "売りエントリー価格",
      "tp": "利確ライン",
      "sl": "損切りライン",
      "reason": "このエントリーの根拠（1〜2文）"
    }}
  ],
  "notes": "注意事項や重要な経済指標など（あれば）"
}}"""
    res = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=800,
        messages=[{"role": "user", "content": prompt}]
    )
    text = res.content[0].text
    match = re.search(r'\{.*\}', text, re.DOTALL)
    if match:
        return json.loads(match.group())
    return {}

def safe_val(v, default="N/A"):
    return str(v) if v and str(v).strip() else default

def send_fx_report(name, data, result):
    change_pct = data["change_pct"]
    color = 0x2ecc71 if change_pct >= 0 else 0xe74c3c
    arrow = "▲" if change_pct >= 0 else "▼"
    desc = safe_val(result.get("analysis"), "分析データを取得しました")

    fields = [
        {"name": "💰 現在価格", "value": f"{data['price']:,.2f}", "inline": True},
        {"name": "📈 前日比", "value": f"{arrow} {abs(change_pct):.2f}%", "inline": True},
        {"name": "🔍 トレンド", "value": safe_val(result.get("trend")), "inline": True},
        {"name": "📊 RSI 1H", "value": safe_val(result.get("rsi_1h")), "inline": True},
        {"name": "📊 RSI 4H", "value": safe_val(result.get("rsi_4h")), "inline": True},
        {"name": "📊 RSI 1D", "value": safe_val(result.get("rsi_1d")), "inline": True},
    ]

    # 買いエントリー
    buy_entries = result.get("buy_entries", [])
    for i, b in enumerate(buy_entries, 1):
        label = f"🟢 買い#{i} エントリー/TP/SL"
        val = f"エントリー: {safe_val(b.get('entry'))}\nTP: {safe_val(b.get('tp'))}\nSL: {safe_val(b.get('sl'))}\n根拠: {safe_val(b.get('reason'))}"
        fields.append({"name": label, "value": val, "inline": False})

    # 売りエントリー
    sell_entries = result.get("sell_entries", [])
    for i, s in enumerate(sell_entries, 1):
        label = f"🔴 売り#{i} エントリー/TP/SL"
        val = f"エントリー: {safe_val(s.get('entry'))}\nTP: {safe_val(s.get('tp'))}\nSL: {safe_val(s.get('sl'))}\n根拠: {safe_val(s.get('reason'))}"
        fields.append({"name": label, "value": val, "inline": False})

    notes = result.get("notes", "")
    if notes and notes.strip():
        fields.append({"name": "⚠️ 注意事項", "value": notes, "inline": False})

    send_embed("fx", f"🟡 {name} 分析レポート", desc, fields=fields, color=color)

def run():
    print("=== FX分析開始 ===")
    for name, ticker in SYMBOLS.items():
        try:
            data = get_price_data(ticker)
            if not data:
                send_alert(f"{name}のデータ取得に失敗しました", level="warning")
                continue
            result = analyze_with_claude(name, data)
            send_fx_report(name, data, result)
            time.sleep(1)
        except Exception as e:
            send_alert(f"{name}の分析中にエラー: {str(e)}", level="error")
    print("=== FX分析完了 ===")

if __name__ == "__main__":
    run()
