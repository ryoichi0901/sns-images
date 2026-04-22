import os,json,time,requests,datetime
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
    import base64
    GH_TOKEN = os.getenv("GH_TOKEN")
    GH_REPO  = "ryoichi0901/sns-images"
    GH_BRANCH = "main"
    filename = path.name
    gh_path  = filename
    raw_url  = f"https://raw.githubusercontent.com/{GH_REPO}/{GH_BRANCH}/{filename}"
    api_url  = f"https://api.github.com/repos/{GH_REPO}/contents/{gh_path}"
    headers  = {"Authorization": f"token {GH_TOKEN}", "Accept": "application/vnd.github+json"}
    sha = None
    r = requests.get(api_url, headers=headers, timeout=30)
    if r.status_code == 200:
        sha = r.json().get("sha")
    content = base64.b64encode(path.read_bytes()).decode()
    body = {"message": f"Add {filename}", "content": content, "branch": GH_BRANCH}
    if sha:
        body["sha"] = sha
    r2 = requests.put(api_url, headers=headers, json=body, timeout=60)
    r2.raise_for_status()
    print("GitHub raw URL:", raw_url)
    return raw_url

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

def main():
    today = datetime.date.today()
    c = gen_caption()
    img = gen_image(c["image_prompt"], today.strftime("%Y%m%d"))
    url = upload(img)
    pid = post(url, c["caption"])
    tid = post_threads(url, c["caption"])
    print("Posted IG:", pid, "Threads:", tid)
    with open(LF,"a",encoding="utf-8") as f:
        f.write(json.dumps({"date":str(today),"id":pid},ensure_ascii=False)+"\n")

if __name__ == "__main__":
    main()

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
