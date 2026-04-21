import os,json,time,base64,requests,datetime
from pathlib import Path
env_path = os.path.expanduser("~/Documents/Obsidian Vault/.env")
for line in open(env_path,encoding="utf-8"):
    line=line.strip()
    if "=" in line and not line.startswith("#"):
        k,v=line.split("=",1)
        os.environ[k.strip()]=v.strip()
T=os.environ.get
IT=T("INSTAGRAM_ACCESS_TOKEN")
II=T("INSTAGRAM_BUSINESS_ID")
AK=T("ANTHROPIC_API_KEY")
SK=T("STABILITY_API_KEY")
IK=T("IMGBB_API_KEY")
BD=Path(__file__).parent.parent
ID2=BD/"images"
LF=BD/"logs"/"post_log.jsonl"
ID2.mkdir(exist_ok=True)
LF.parent.mkdir(exist_ok=True)
def gen_caption():
    p="Create Instagram post JSON only: {"caption":"500 char Japanese caption with emoji and CTA","image_prompt":"business finance navy blue gold clean modern no text 9:16","alt_text":"description"}"
    r=requests.post("https://api.anthropic.com/v1/messages",
        headers={"x-api-key":AK,"anthropic-version":"2023-06-01","content-type":"application/json"},
        json={"model":"claude-sonnet-4-20250514","max_tokens":1000,"messages":[{"role":"user","content":p}]},timeout=60)
    r.raise_for_status()
    text=r.json()["content"][0]["text"].strip()
    for d in [""]: text=text.replace(d,"")
    return json.loads(text.strip())
def gen_image(prompt,ds):
    path=ID2/("post_"+ds+".jpg")
    r=requests.post("https://api.stability.ai/v2beta/stable-image/generate/core",
        headers={"authorization":"Bearer "+SK,"accept":"image/*"},
        files={"none":""},data={"prompt":prompt,"aspect_ratio":"9:16","output_format":"jpeg"},timeout=60)
    if r.status_code==200:
        path.write_bytes(r.content)
        print("Image:",path.name)
        return path
    raise Exception("Image error:"+str(r.status_code))
def upload(path):
    with open(path,"rb") as f: d=base64.b64encode(f.read()).decode()
    r=requests.post("https://api.imgbb.com/1/upload",data={"key":IK,"image":d},timeout=30)
    r.raise_for_status()
    url=r.json()["data"]["url"]
    print("Uploaded:",url)
    return url
def post(img_url,cap):
    r=requests.post("https://graph.facebook.com/v25.0/"+II+"/media",
        params={"image_url":img_url,"caption":cap,"access_token":IT},timeout=30)
    r.raise_for_status()
    cid=r.json()["id"]
    time.sleep(5)
    r2=requests.post("https://graph.facebook.com/v25.0/"+II+"/media_publish",
        params={"creation_id":cid,"access_token":IT},timeout=30)
    r2.raise_for_status()
    return r2.json()["id"]
def main():
    today=datetime.date.today()
    c=gen_caption()
    cap=c["caption"]
    img=gen_image(c["image_prompt"],today.strftime("%Y%m%d"))
    url=upload(img)
    pid=post(url,cap)
    print("Posted:",pid)
    with open(LF,"a",encoding="utf-8") as f:
        f.write(json.dumps({"date":str(today),"id":pid},ensure_ascii=False)+"
")
if __name__=="__main__": main()