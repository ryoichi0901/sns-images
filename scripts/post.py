import os,json,time,requests,datetime
import anthropic
import pytz
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv
load_dotenv(os.path.expanduser("~/Documents/Obsidian Vault/.env"))
IT = os.getenv("INSTAGRAM_ACCESS_TOKEN")
II = os.getenv("INSTAGRAM_BUSINESS_ID")
AK = os.getenv("ANTHROPIC_API_KEY")
BD = Path(__file__).parent.parent
ID2 = BD / "images"
LF = BD / "logs" / "post_log.jsonl"
ID2.mkdir(exist_ok=True)
LF.parent.mkdir(exist_ok=True)

def gen_caption():
    for i in range(3):
        try:
            r = requests.post("https://api.anthropic.com/v1/messages",
                headers={"x-api-key":AK,"anthropic-version":"2023-06-01","content-type":"application/json"},
                json={"model":"claude-haiku-4-5-20251001","max_tokens":1000,"messages":[{"role":"user","content":"Return JSON only no other text: {\"caption\":\"日本語500字以内。金融機関20年の知識とAI副業で資産形成する具体的なtips。ハッシュタグ10個含める。#AI副業 #資産形成 #副業収入 #金融リテラシー #NISA #投資初心者 を必ず含める\",\"image_prompt\":\"professional finance money investment AI technology modern clean\"}"}]},
                timeout=60)
            r.raise_for_status()
            text = r.json()["content"][0]["text"].strip()
            text = text.replace("```json","").replace("```","").strip()
            return json.loads(text)
        except Exception as e:
            print(f"Retry {i+1}/3: {e}")
            time.sleep(10)
    raise Exception("Claude API failed")

def gen_image(prompt, ds):
    path = ID2 / ("post_" + ds + ".jpg")
    encoded = requests.utils.quote(prompt)
    url = "https://image.pollinations.ai/prompt/"+encoded+"?width=1080&height=1080&nologo=true"
    r = requests.get(url, timeout=120)
    if r.status_code == 200:
        path.write_bytes(r.content)
        return path
    raise Exception("Image error:" + str(r.status_code))

def upload(path):
    import hashlib, time as t
    CN = os.getenv("CLOUDINARY_CLOUD_NAME")
    CK = os.getenv("CLOUDINARY_API_KEY")
    CS = os.getenv("CLOUDINARY_API_SECRET")
    timestamp = str(int(t.time()))
    sig = hashlib.sha256(f"timestamp={timestamp}{CS}".encode()).hexdigest()
    with open(path, "rb") as f:
        r = requests.post(
            f"https://api.cloudinary.com/v1_1/{CN}/image/upload",
            data={"api_key": CK, "timestamp": timestamp, "signature": sig},
            files={"file": f},
            timeout=60,
        )
    r.raise_for_status()
    url = r.json()["secure_url"]
    print("Cloudinary URL:", url)
    return url

def post(img_url, cap):
    r = requests.post("https://graph.facebook.com/v25.0/"+II+"/media",
        data={"image_url":img_url,"caption":cap,"access_token":IT},timeout=30)
    r.raise_for_status()
    cid = r.json()["id"]
    time.sleep(5)
    r2 = requests.post("https://graph.facebook.com/v25.0/"+II+"/media_publish",
        data={"creation_id":cid,"access_token":IT},timeout=30)
    r2.raise_for_status()
    return r2.json()["id"]

def get_time_slot():
    jst = pytz.timezone('Asia/Tokyo')
    hour = datetime.now(jst).hour
    if 5 <= hour < 10:
        return "朝"
    elif 10 <= hour < 15:
        return "昼"
    else:
        return "夜"

def gen_threads_text():
    slot = get_time_slot()
    slot_context = {
        "朝": "通勤・起床直後に読む人向け。簡潔で前向きな内容。",
        "昼": "昼休みに読む人向け。学びや気づきを与える内容。",
        "夜": "一日の終わりに読む人向け。明日への行動につながる内容。"
    }
    client = anthropic.Anthropic()
    message = client.messages.create(
        model="claude-opus-4-5",
        max_tokens=300,
        messages=[{
            "role": "user",
            "content": f"""あなたはThreadsで「金融×AI副業」をテーマに発信するインフルエンサーです。
時間帯：{slot}（{slot_context[slot]}）

以下の条件でThreadsの投稿文を1つ作成してください：
- 文字数：150字以内
- 改行を活用して読みやすくする
- ハッシュタグは末尾に3個以内
- 「元銀行員×AI副業」の視点で具体的なtipsや気づきを書く
- 説教・自慢にならず、友達に話しかける口調で

投稿文のみ出力してください。"""
        }]
    )
    return message.content[0].text.strip()

def post_threads_text_only():
    user_id = os.getenv("THREADS_USER_ID")
    token   = os.getenv("THREADS_ACCESS_TOKEN")
    text    = gen_threads_text()
    res = requests.post(
        f"https://graph.threads.net/v1.0/{user_id}/threads",
        params={"media_type": "TEXT", "text": text, "access_token": token}
    )
    container_id = res.json().get("id")
    requests.post(
        f"https://graph.threads.net/v1.0/{user_id}/threads_publish",
        params={"creation_id": container_id, "access_token": token}
    )
    print(f"Threads text posted: {text[:30]}...")
    return container_id

def post_threads(img_url, cap):
    THREADS_USER_ID = os.getenv("THREADS_USER_ID")
    THREADS_TOKEN   = os.getenv("THREADS_ACCESS_TOKEN")
    # Step1: コンテナ作成
    r = requests.post(
        f"https://graph.threads.net/v1.0/{THREADS_USER_ID}/threads",
        params={
            "media_type": "IMAGE",
            "image_url": img_url,
            "text": cap,
            "access_token": THREADS_TOKEN,
        },
        timeout=30,
    )
    r.raise_for_status()
    cid = r.json()["id"]
    time.sleep(5)
    # Step2: 公開
    r2 = requests.post(
        f"https://graph.threads.net/v1.0/{THREADS_USER_ID}/threads_publish",
        params={"creation_id": cid, "access_token": THREADS_TOKEN},
        timeout=30,
    )
    r2.raise_for_status()
    return r2.json()["id"]

def main():
    jst = pytz.timezone('Asia/Tokyo')
    hour = datetime.now(jst).hour
    is_evening = 20 <= hour <= 22

    if is_evening:
        today = datetime.now(jst)
        c = gen_caption()
        img = gen_image(c["image_prompt"], today.strftime("%Y%m%d"))
        url = upload(img)
        pid = post(url, c["caption"])
        tid = post_threads(url, c["caption"])
        print(f"Posted IG: {pid} Threads: {tid}")
        with open(LF,"a",encoding="utf-8") as f:
            f.write(json.dumps({"date":today.strftime("%Y-%m-%d"),"id":pid},ensure_ascii=False)+"\n")
    else:
        tid = post_threads_text_only()
        print(f"Threads text only: {tid}")

if __name__ == "__main__":
    main()
