"""
Threadsエージェント
Threads Graph APIを使い、テキスト（+画像オプション）を投稿する。
アフィリエイトリンクをテキスト末尾に付与。
補足コメント（リプライ）の自動生成・投稿機能を含む。
"""
import time
from typing import TYPE_CHECKING, Optional
import requests

if TYPE_CHECKING:
    import anthropic as _ant

FOLLOWUP_DELAY = 300  # 5分

_FOLLOWUP_PROMPT = """\
以下のThreads投稿に対する補足コメントを生成してください。

【元の投稿】
{post_text}

【補足方針】
投稿内容に関連する銀行員時代の具体的なエピソード・数字・実体験を1つ追加する。
元投稿と重複しない新しい視点を加える。

【補足コメントの型】
「補足：〇〇（具体的なエピソードや数字）
〜という経験から、□□だと気づきました。」

【制約】
- 100〜150字以内
- ハッシュタグなし
- 一人称・体験談ベースで書く
- 捏造統計・根拠不明の数字は使わない（自分の体験のみ）

補足コメントの本文のみ出力してください。前置き・説明不要。\
"""

THREADS_API = "https://graph.threads.net/v1.0"


def build_threads_text(base_text: str, weekday: int, theme: Optional[str] = None) -> str:
    """本文をそのまま返す。シグネチャは後方互換のため維持。"""
    return base_text


def publish_to_threads(
    text: str,
    weekday: int,
    user_id: str,
    access_token: str,
    image_url: Optional[str] = None,
    theme: Optional[str] = None,
) -> str:
    """
    Threads に投稿し、投稿IDを返す。
    image_url が指定された場合は画像付き投稿、なければテキストのみ。
    theme を指定するとテーマ優先のアフィリエイトリンクを付与する。
    """
    full_text = build_threads_text(text, weekday, theme=theme)

    # Step1: コンテナ作成
    payload: dict = {"text": full_text, "access_token": access_token}
    if image_url:
        payload["media_type"] = "IMAGE"
        payload["image_url"] = image_url
    else:
        payload["media_type"] = "TEXT"

    r1 = requests.post(
        f"{THREADS_API}/{user_id}/threads",
        data=payload,
        timeout=30,
    )
    r1.raise_for_status()
    container_id = r1.json()["id"]
    print(f"[ThreadsAgent] コンテナ作成: {container_id}")

    time.sleep(3)

    # Step2: 公開
    r2 = requests.post(
        f"{THREADS_API}/{user_id}/threads_publish",
        data={"creation_id": container_id, "access_token": access_token},
        timeout=30,
    )
    r2.raise_for_status()
    post_id = r2.json()["id"]
    print(f"[ThreadsAgent] 投稿完了: {post_id}")
    return post_id


def post_followup_comment(
    post_id: str,
    post_text: str,
    user_id: str,
    access_token: str,
    client: "Optional[_ant.Anthropic]" = None,
    delay: int = FOLLOWUP_DELAY,
) -> str:
    """
    Threads 投稿に補足コメントをリプライ投稿する。
    delay 秒（デフォルト5分）待機後にコメントを生成・投稿し、コメントIDを返す。
    client: anthropic.Anthropic インスタンス（run.py で初期化済みのものを渡す）
    """
    print(f"\n[ThreadsAgent] 補足コメント: {delay // 60}分後に投稿します...")
    for remaining in range(delay, 0, -30):
        print(f"  あと {remaining}秒...", end="\r", flush=True)
        time.sleep(min(30, remaining))
    print()

    # コメント生成（client が渡されていない場合は ANTHROPIC_API_KEY から初期化）
    if client is None:
        import os
        import anthropic as _anthropic
        client = _anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

    print("[ThreadsAgent] 補足コメント生成中...")
    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=300,
        messages=[{"role": "user", "content": _FOLLOWUP_PROMPT.format(post_text=post_text)}],
    )
    comment_text = response.content[0].text.strip()
    if len(comment_text) > 150:
        comment_text = comment_text[:150]
    print(f"[ThreadsAgent] 補足コメント生成完了: {len(comment_text)}字")
    print(f"  内容: {comment_text[:60]}...")

    # Step1: リプライコンテナ作成
    r1 = requests.post(
        f"{THREADS_API}/{user_id}/threads",
        data={
            "media_type":   "TEXT",
            "text":         comment_text,
            "reply_to_id":  post_id,
            "access_token": access_token,
        },
        timeout=30,
    )
    r1.raise_for_status()
    container_id = r1.json()["id"]
    print(f"[ThreadsAgent] 補足コメントコンテナ: {container_id}")
    time.sleep(3)

    # Step2: 公開
    r2 = requests.post(
        f"{THREADS_API}/{user_id}/threads_publish",
        data={"creation_id": container_id, "access_token": access_token},
        timeout=30,
    )
    r2.raise_for_status()
    comment_id = r2.json()["id"]
    print(f"[ThreadsAgent] 補足コメント投稿完了: {comment_id}")
    return comment_id
