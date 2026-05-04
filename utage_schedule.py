"""
utage_schedule.py - DOM直読み版
"""
import asyncio, os, re, sys
from datetime import date, datetime, timedelta
import requests
from playwright.async_api import async_playwright

UTAGE_LOGIN_URL = "https://utage-system.com/operator/u3LOxxsfqxbU/login"
DISCORD_WEBHOOK = os.environ.get("DISCORD_WEBHOOK_UTAGE", "")
UTAGE_EMAIL     = os.environ.get("UTAGE_EMAIL", "")
UTAGE_PASSWORD  = os.environ.get("UTAGE_PASSWORD", "")

EVENTS = {
    "uot1j97GeWZR": "栄養アドバイザー個別相談",
    "Tpd0mf3bdbek": "受講生の無料妊活相談",
    "fUSiDCKSxUd4": "看護師スタッフ個別カウンセリング",
    "RJ3FemO7uGXt": "守護霊リーディングセッション",
    "so0sd24xtEEF": "脳幹セラピー",
    "Tm3IiLWoQGDF": "渡辺優子個別カウンセリング",
}

def target_dates():
    today = date.today()
    return [today + timedelta(days=i) for i in range(3)]

async def get_slots(page, event_id):
    slots = []
    try:
        # /edit はフォームなし。実データは /calendar に埋め込まれている
        await page.goto(f"https://utage-system.com/event/{event_id}/calendar")
        await page.wait_for_load_state("networkidle")

        # specified_date_schedule[n][specified_date] / [time_from] / [time_to] を取得
        rows_data = await page.evaluate("""() =>
            Array.from(
                document.querySelectorAll(
                    'input[name^="specified_date_schedule["][name$="][specified_date]"]'
                )
            ).map(el => {
                const n  = el.name.match(/\\[(\\d+)\\]/)[1];
                const tf = document.querySelector(
                    `select[name='specified_date_schedule[${n}][time_from]']`);
                const tt = document.querySelector(
                    `select[name='specified_date_schedule[${n}][time_to]']`);
                const op = document.querySelector(
                    `select[name='specified_date_schedule[${n}][is_opened]']`);
                return {
                    date:      el.value,
                    start:     tf ? tf.value : '',
                    end:       tt ? tt.value : '',
                    is_opened: op ? op.value : '1',
                };
            })
        """)

        for r in rows_data:
            if not r["date"] or not r["start"] or not r["end"]:
                continue
            if r["is_opened"] != "1":  # 非公開スロットはスキップ
                continue
            ds = r["date"].replace("-", "/")
            try:
                d = datetime.strptime(ds, "%Y/%m/%d").date()
                slots.append({"date": d, "start": r["start"][:5], "end": r["end"][:5]})
            except ValueError:
                continue

        print(f"  → 枠 {len(slots)}件: {[(str(s['date']), s['start']) for s in slots[:3]]}", file=sys.stderr)
    except Exception as e:
        print(f"[warn] 枠取得失敗 {event_id}: {e}", file=sys.stderr)
    return slots

async def get_booked(page, event_id):
    booked = []
    try:
        await page.goto(f"https://utage-system.com/event/{event_id}/applicant")
        await page.wait_for_load_state("networkidle")
        rows = await page.query_selector_all("table tbody tr")
        for row in rows:
            cells = await row.query_selector_all("td")
            if len(cells) < 4:
                continue
            # 日程列（index 1）
            schedule_text = (await cells[1].inner_text()).strip()
            m = re.search(r"(\d{4}/\d{2}/\d{2})[^\d]*(\d{2}:\d{2})-(\d{2}:\d{2})", schedule_text)
            if not m:
                continue
            try:
                d = datetime.strptime(m.group(1), "%Y/%m/%d").date()
            except ValueError:
                continue
            name = (await cells[3].inner_text()).strip() if len(cells) > 3 else "（名前不明）"
            booked.append({"date": d, "start": m.group(2), "end": m.group(3), "name": name or "（名前不明）"})
    except Exception as e:
        print(f"[warn] 予約取得失敗 {event_id}: {e}", file=sys.stderr)
    return booked

async def scrape_all():
    results = {}
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()

        await page.goto(UTAGE_LOGIN_URL)
        await page.wait_for_load_state("networkidle")
        await page.locator("input[placeholder='メールアドレス']").fill(UTAGE_EMAIL)
        await page.locator("input[placeholder='パスワード']").fill(UTAGE_PASSWORD)
        await page.locator("button:has-text('ログイン')").click()
        await page.wait_for_load_state("networkidle")
        if "login" in page.url:
            raise RuntimeError("ログイン失敗。UTAGE_EMAIL / UTAGE_PASSWORD を確認してください。")

        for event_id, event_name in EVENTS.items():
            print(f"[{event_name}] 取得中...", file=sys.stderr)
            slots  = await get_slots(page, event_id)
            booked = await get_booked(page, event_id)
            results[event_name] = {"slots": slots, "booked": booked}

        await browser.close()
    return results

def build_message(results):
    targets = target_dates()
    wd = ["月","火","水","木","金","土","日"]
    lines = ["📅 **UTAGEスケジュール（今日・明日・明後日）**\n"]

    for i, d in enumerate(targets):
        label  = ["今日","明日","明後日"][i]
        header = f"**── {label}（{d.month}/{d.day}・{wd[d.weekday()]}） ──**"
        day_lines = []

        for event_name, data in results.items():
            day_slots  = sorted([s for s in data["slots"]  if s["date"] == d], key=lambda x: x["start"])
            day_booked = [b for b in data["booked"] if b["date"] == d]
            if not day_slots:
                continue
            for s in day_slots:
                slot_str = f"{s['start']}〜{s['end']}"
                matched  = [b for b in day_booked if b["start"] == s["start"]]
                if matched:
                    day_lines.append(f"  ✅ {event_name}　{slot_str}　{matched[0]['name']} さま　予約済み")
                else:
                    day_lines.append(f"  ⚠️ {event_name}　{slot_str}　空き ← 埋めませんか？")
            for b in day_booked:
                if not any(s["start"] == b["start"] for s in day_slots):
                    day_lines.append(f"  ✅ {event_name}　{b['start']}〜{b['end']}　{b['name']} さま　予約済み")

        lines.append(header)
        lines.extend(day_lines if day_lines else ["  📭 この日の枠なし"])
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
        results = await scrape_all()
        msg = build_message(results)
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
