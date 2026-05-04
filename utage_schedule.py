"""
utage_schedule.py - Playwright版
UTAGEの申込者一覧をスクレイピングして今日・明日・明後日の予約をDiscordに送信
"""
import asyncio, json, os, re, sys
from datetime import date, datetime, timedelta
from pathlib import Path
import requests
from playwright.async_api import async_playwright

UTAGE_LOGIN_URL = "https://utage-system.com/operator/u3LOxxsfqxbU/login"
APPLICANT_URL   = "https://utage-system.com/event/RJ3FemO7uGXt/applicant"
DISCORD_WEBHOOK = os.environ.get("DISCORD_WEBHOOK_UTAGE", "")
UTAGE_EMAIL     = os.environ.get("UTAGE_EMAIL", "")
UTAGE_PASSWORD  = os.environ.get("UTAGE_PASSWORD", "")

def target_dates():
    today = date.today()
    return [today + timedelta(days=i) for i in range(3)]

async def fetch_reservations():
    email    = UTAGE_EMAIL
    password = UTAGE_PASSWORD
    if not email or not password:
        raise ValueError("UTAGE_EMAIL / UTAGE_PASSWORD が未設定")

    reservations = []
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page    = await browser.new_page()
        await page.goto(UTAGE_LOGIN_URL)
        await page.wait_for_load_state("networkidle")
        try:
            await page.fill('input[type="email"]', email)
            await page.fill('input[type="password"]', password)
            await page.click('button[type="submit"]')
        except Exception:
            await page.fill('input[name="email"]', email)
            await page.fill('input[name="password"]', password)
            await page.click('input[type="submit"]')
        await page.wait_for_load_state("networkidle")
        await page.goto(APPLICANT_URL)
        await page.wait_for_load_state("networkidle")
        rows = await page.query_selector_all("tr")
        for row in rows:
            text = await row.inner_text()
            m = re.search(r"(\d{4}/\d{2}/\d{2})[^\d]*(\d{2}:\d{2})-(\d{2}:\d{2})", text)
            if not m:
                continue
            try:
                dt = datetime.strptime(m.group(1), "%Y/%m/%d").date()
            except ValueError:
                continue
            cells = await row.query_selector_all("td")
            name = "（名前不明）"
            for cell in cells:
                t = (await cell.inner_text()).strip()
                if re.search(r"[\u3040-\u30ff\u4e00-\u9fff]", t) and 2 < len(t) < 15:
                    if not re.search(r"\d{4}/\d{2}/\d{2}", t):
                        name = t
                        break
            reservations.append({"name": name, "date": dt, "slot": f"{m.group(2)}〜{m.group(3)}"})
        await browser.close()
    return reservations

def build_message(reservations):
    targets = target_dates()
    wd = ["月","火","水","木","金","土","日"]
    lines = ["📅 **UTAGEスケジュール（今日・明日・明後日）**\n"]
    for i, d in enumerate(targets):
        label  = ["今日","明日","明後日"][i]
        header = f"**{label}（{d.month}/{d.day}・{wd[d.weekday()]}）**"
        booked = [r for r in reservations if r["date"] == d]
        if booked:
            lines.append(header + "\n" + "\n".join(f"  ✅ {r['slot']}　{r['name']}" for r in booked))
        else:
            lines.append(header + "\n  ⚠️ 予約なし　← 枠を埋めませんか？")
        lines.append("")
    lines.append(f"_取得: {datetime.now().strftime('%Y-%m-%d %H:%M')}_")
    return "\n".join(lines)

def send_discord(msg):
    if not DISCORD_WEBHOOK:
        print("DISCORD_WEBHOOK_UTAGE 未設定")
        return
    requests.post(DISCORD_WEBHOOK, json={"content": msg}).raise_for_status()

async def main():
    try:
        reservations = await fetch_reservations()
        msg = build_message(reservations)
        print(msg)
        send_discord(msg)
        print("Discord送信完了")
    except Exception as e:
        err = f"⚠️ UTAGEスケジュールエラー: {e}"
        print(err, file=sys.stderr)
        send_discord(err)
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())
