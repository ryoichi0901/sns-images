"""
utage_schedule.py - DOM直読み版
"""
import asyncio, os, re, sys, time
from datetime import datetime, timedelta, timezone
from pathlib import Path
import requests
from playwright.async_api import async_playwright

UTAGE_LOGIN_URL = "https://utage-system.com/operator/u3LOxxsfqxbU/login"
JST = timezone(timedelta(hours=9))
PAGE_TIMEOUT_MS = 60000
MAX_ATTEMPTS = 3
DISCORD_CHUNK_SIZE = 1900

def load_env_file(path):
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))

load_env_file(Path.home() / "Documents/Obsidian Vault/.env")

DISCORD_WEBHOOK = os.environ.get("DISCORD_WEBHOOK_UTAGE", "")
UTAGE_EMAIL     = os.environ.get("UTAGE_EMAIL", "")
UTAGE_PASSWORD  = os.environ.get("UTAGE_PASSWORD", "")

EVENTS = {
    "uot1j97GeWZR": "栄養アドバイザー個別相談",
    "uSVmk5X0FMBB": "個別サポートコース栄養指導・潜在意識書き換えセッション",
    "Tpd0mf3bdbek": "受講生の無料妊活相談",
    "fUSiDCKSxUd4": "看護師スタッフ個別カウンセリング",
    "RJ3FemO7uGXt": "守護霊リーディングセッション",
    "so0sd24xtEEF": "脳幹セラピー",
    "Tm3IiLWoQGDF": "渡辺優子個別カウンセリング",
    "U8XVmwIEK98t": "44歳出産！エスミンの無料相談",
}

MONTHLY_EVENTS = {
    "60LsfTVQuv06": "藤沢サロンランチ会",
    "9E0C83HtYoOP": "守護霊メッセージとリーディング会",
    "WpazBl8YvCDE": "潜在意識の書き換えオンライン",
    "LJvkMVp0ttgc": "神社参拝お申し込みフォーム",
    "FTYdAQ0xiyBy": "渡辺優子のオンライン質問会",
}

def target_dates():
    today = datetime.now(JST).date()
    return [today + timedelta(days=i) for i in range(3)]

async def get_slots(page, event_id):
    slots = []
    try:
        # /edit はフォームなし。実データは /calendar に埋め込まれている
        await page.goto(
            f"https://utage-system.com/event/{event_id}/calendar",
            wait_until="domcontentloaded",
            timeout=PAGE_TIMEOUT_MS,
        )

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
        raise RuntimeError(f"枠取得失敗 {event_id}: {e}") from e
    return slots

async def get_booked(page, event_id):
    booked = []
    try:
        await page.goto(
            f"https://utage-system.com/event/{event_id}/applicant",
            wait_until="domcontentloaded",
            timeout=PAGE_TIMEOUT_MS,
        )
        headers = [
            (await th.inner_text()).strip()
            for th in await page.query_selector_all("table thead th")
        ]
        rows = await page.query_selector_all("table tbody tr")

        def column_index(label, default):
            try:
                return headers.index(label)
            except ValueError:
                return default

        schedule_idx = column_index("日程", 1)
        name_idx = column_index("お名前", 3)
        status_idx = column_index("参加状況", 6)

        for row in rows:
            cells = await row.query_selector_all("td")
            if len(cells) <= max(schedule_idx, name_idx):
                continue
            row_text = (await row.inner_text()).strip()

            status = ""
            if len(cells) > status_idx:
                status = (await cells[status_idx].inner_text()).strip()
            schedule_text = (await cells[schedule_idx].inner_text()).strip()
            parsed = parse_schedule_text(schedule_text)
            if not parsed:
                continue

            name = (await cells[name_idx].inner_text()).strip()
            booked.append({
                **parsed,
                "name": name or "（名前不明）",
                "status": status,
                "canceled": is_canceled_status(status) or is_canceled_status(row_text),
            })
    except Exception as e:
        raise RuntimeError(f"予約取得失敗 {event_id}: {e}") from e
    return booked

def parse_schedule_text(schedule_text):
    m = re.search(
        r"(\d{4}/\d{2}/\d{2}).*?(\d{2}:\d{2})\s*[-〜~–—]\s*(\d{2}:\d{2})",
        schedule_text,
        re.S,
    )
    if not m:
        return None
    try:
        d = datetime.strptime(m.group(1), "%Y/%m/%d").date()
    except ValueError:
        return None
    return {"date": d, "start": m.group(2), "end": m.group(3)}

def is_canceled_status(status):
    normalized = re.sub(r"\s+", "", status or "")
    return "キャンセル" in normalized or "取消" in normalized or "不参加" in normalized

def format_canceled_label(bookings):
    labels = []
    for b in bookings:
        status = b.get("status") or "キャンセル"
        label = f"{b['name']} さま {status}"
        if label not in labels:
            labels.append(label)
    return "、".join(labels)

async def get_participants(page, event_id):
    participants = []
    try:
        await page.goto(
            f"https://utage-system.com/event/{event_id}/applicant",
            wait_until="domcontentloaded",
            timeout=PAGE_TIMEOUT_MS,
        )

        headers = [
            (await th.inner_text()).strip()
            for th in await page.query_selector_all("table thead th")
        ]
        rows = await page.query_selector_all("table tbody tr")

        def column_index(label, default):
            try:
                return headers.index(label)
            except ValueError:
                return default

        schedule_idx = column_index("日程", 1)
        name_idx = column_index("お名前", 3)
        status_idx = column_index("参加状況", 6)

        for row in rows:
            cells = await row.query_selector_all("td")
            if len(cells) <= max(schedule_idx, name_idx):
                continue
            row_text = (await row.inner_text()).strip()
            schedule_text = (await cells[schedule_idx].inner_text()).strip()
            parsed = parse_schedule_text(schedule_text)
            if not parsed:
                continue

            name = (await cells[name_idx].inner_text()).strip()
            if not name:
                name = "（名前不明）"

            status = ""
            if len(cells) > status_idx:
                status = (await cells[status_idx].inner_text()).strip()
            if is_canceled_status(status) or is_canceled_status(row_text):
                continue

            participants.append({
                **parsed,
                "name": name,
                "status": status,
            })
    except Exception as e:
        raise RuntimeError(f"参加者取得失敗 {event_id}: {e}") from e
    return participants

async def login_utage(page):
    if not UTAGE_EMAIL or not UTAGE_PASSWORD:
        raise RuntimeError("UTAGE_EMAIL / UTAGE_PASSWORD が未設定です。")

    last_error = None
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            print(f"[login] UTAGEログイン {attempt}/{MAX_ATTEMPTS}", file=sys.stderr)
            await page.goto(
                UTAGE_LOGIN_URL,
                wait_until="domcontentloaded",
                timeout=PAGE_TIMEOUT_MS,
            )
            email = page.locator("input[placeholder='メールアドレス']")
            password = page.locator("input[placeholder='パスワード']")
            await email.wait_for(state="visible", timeout=PAGE_TIMEOUT_MS)
            await email.fill(UTAGE_EMAIL)
            await password.fill(UTAGE_PASSWORD)
            await page.locator("button:has-text('ログイン')").click()
            await page.wait_for_timeout(1500)
            await page.wait_for_load_state("domcontentloaded", timeout=PAGE_TIMEOUT_MS)
            if "login" not in page.url:
                return
            raise RuntimeError("ログイン後もログイン画面のままです。")
        except Exception as e:
            last_error = e
            print(f"[warn] UTAGEログイン失敗 {attempt}/{MAX_ATTEMPTS}: {e}", file=sys.stderr)
            if attempt < MAX_ATTEMPTS:
                await page.wait_for_timeout(attempt * 2000)

    try:
        await page.screenshot(path="utage_login_failure.png", full_page=True)
    except Exception:
        pass
    raise RuntimeError(f"UTAGEログインに{MAX_ATTEMPTS}回失敗しました: {last_error}")

async def scrape_all():
    results = {"schedule": {}, "monthly": {}}
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()

        await login_utage(page)

        for event_id, event_name in EVENTS.items():
            print(f"[{event_name}] 取得中...", file=sys.stderr)
            slots  = await get_slots(page, event_id)
            booked = await get_booked(page, event_id)
            results["schedule"][event_name] = {"slots": slots, "booked": booked}

        for event_id, event_name in MONTHLY_EVENTS.items():
            print(f"[{event_name}] 参加者取得中...", file=sys.stderr)
            participants = await get_participants(page, event_id)
            results["monthly"][event_name] = {"participants": participants}

        await browser.close()
    return results

def build_message(results):
    targets = target_dates()
    wd = ["月","火","水","木","金","土","日"]
    lines = ["📅 **UTAGEスケジュール（今日・明日・明後日）**\n"]
    schedule_results = results.get("schedule", results)

    for i, d in enumerate(targets):
        label  = ["今日","明日","明後日"][i]
        header = f"**── {label}（{d.month}/{d.day}・{wd[d.weekday()]}） ──**"
        day_lines = []

        for event_name, data in schedule_results.items():
            day_slots  = sorted([s for s in data["slots"]  if s["date"] == d], key=lambda x: x["start"])
            day_booked = [b for b in data["booked"] if b["date"] == d]
            if not day_slots and not day_booked:
                continue
            active_booked = [b for b in day_booked if not b.get("canceled")]
            canceled_booked = [b for b in day_booked if b.get("canceled")]
            for s in day_slots:
                slot_str = f"{s['start']}〜{s['end']}"
                matched  = [b for b in active_booked if b["start"] == s["start"]]
                canceled = [b for b in canceled_booked if b["start"] == s["start"]]
                if matched:
                    day_lines.append(f"  ✅ {event_name}　{slot_str}　{matched[0]['name']} さま　予約済み")
                elif canceled:
                    day_lines.append(f"  ⚠️ {event_name}　{slot_str}　空き（{format_canceled_label(canceled)}）")
                else:
                    day_lines.append(f"  ⚠️ {event_name}　{slot_str}　空き ← 埋めませんか？")
            for b in active_booked:
                if not any(s["start"] == b["start"] for s in day_slots):
                    day_lines.append(f"  ✅ {event_name}　{b['start']}〜{b['end']}　{b['name']} さま　予約済み")
            for b in canceled_booked:
                if not any(s["start"] == b["start"] for s in day_slots):
                    status = b.get("status") or "キャンセル"
                    day_lines.append(f"  ❌ {event_name}　{b['start']}〜{b['end']}　{b['name']} さま　{status}")

        lines.append(header)
        lines.extend(day_lines if day_lines else ["  📭 この日の枠なし"])
        lines.append("")

    monthly_lines = build_monthly_lines(results.get("monthly", {}), wd)
    if monthly_lines:
        lines.append("👥 **月1開催イベント参加者**")
        lines.extend(monthly_lines)
        lines.append("")

    lines.append(f"_取得: {datetime.now(JST).strftime('%Y-%m-%d %H:%M')} JST_")
    return "\n".join(lines)

def build_monthly_lines(monthly_results, wd):
    today = datetime.now(JST).date()
    lines = []

    for event_name, data in monthly_results.items():
        upcoming = [
            p for p in data["participants"]
            if p["date"] >= today
        ]
        grouped = {}
        for p in sorted(upcoming, key=lambda x: (x["date"], x["start"], x["name"])):
            key = (p["date"], p["start"], p["end"])
            grouped.setdefault(key, []).append(p["name"])

        lines.append(f"**── {event_name} ──**")
        if not grouped:
            lines.append("  📭 今後の参加予定者なし")
            continue

        for (event_date, start, end), names in grouped.items():
            date_label = f"{event_date.month}/{event_date.day}・{wd[event_date.weekday()]}"
            unique_names = list(dict.fromkeys(names))
            joined_names = "、".join(unique_names)
            lines.append(f"  ✅ {date_label} {start}〜{end}　{len(unique_names)}名：{joined_names}")

    return lines

def split_discord_message(msg, limit=DISCORD_CHUNK_SIZE):
    chunks = []
    current = []
    current_length = 0
    for line in msg.splitlines(keepends=True):
        while len(line) > limit:
            if current:
                chunks.append("".join(current).rstrip())
                current = []
                current_length = 0
            chunks.append(line[:limit].rstrip())
            line = line[limit:]
        if current and current_length + len(line) > limit:
            chunks.append("".join(current).rstrip())
            current = []
            current_length = 0
        current.append(line)
        current_length += len(line)
    if current:
        chunks.append("".join(current).rstrip())
    return chunks

def send_discord(msg):
    if not DISCORD_WEBHOOK:
        print("DISCORD_WEBHOOK_UTAGE 未設定")
        return
    chunks = split_discord_message(msg)
    for index, chunk in enumerate(chunks, 1):
        last_error = None
        for attempt in range(1, MAX_ATTEMPTS + 1):
            try:
                response = requests.post(
                    DISCORD_WEBHOOK,
                    json={"content": chunk},
                    timeout=30,
                )
                response.raise_for_status()
                break
            except requests.RequestException as e:
                last_error = e
                if attempt < MAX_ATTEMPTS:
                    time.sleep(attempt * 2)
        else:
            raise RuntimeError(
                f"Discord送信失敗（{index}/{len(chunks)}）: {last_error}"
            )

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
