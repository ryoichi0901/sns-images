"""
文体分析エージェント
config/reference_posts.jsonの投稿を読み込み、
Claude Haikuで文体プロファイルを抽出してlogs/style_profile.jsonに保存する。
"""
import json
from pathlib import Path
import anthropic

CONFIG_DIR = Path(__file__).parent.parent / "config"
LOGS_DIR = Path(__file__).parent.parent / "logs"
REFERENCE_POSTS_FILE = CONFIG_DIR / "reference_posts.json"
STYLE_PROFILE_FILE = LOGS_DIR / "style_profile.json"


def _load_reference_posts() -> list[dict]:
    """config/reference_posts.jsonから投稿を読み込む"""
    if not REFERENCE_POSTS_FILE.exists():
        return []
    with open(REFERENCE_POSTS_FILE, encoding="utf-8") as f:
        data = json.load(f)
    accounts = data.get("accounts", [])
    return [a for a in accounts if len(a.get("posts", [])) >= 1]


def _build_corpus(accounts: list[dict]) -> str:
    """全アカウントの投稿を1つのテキストにまとめる"""
    parts = []
    for account in accounts:
        name = account.get("name", "unknown")
        for post in account.get("posts", []):
            if post and post.strip():
                parts.append(f"【{name}】\n{post.strip()}")
    return "\n\n---\n\n".join(parts)


def run_style_analysis(client: anthropic.Anthropic) -> dict:
    """
    reference_posts.jsonを読み込んで文体分析を実行し、
    logs/style_profile.jsonに保存する。
    投稿データがない場合は空のプロファイルを返す。
    """
    accounts = _load_reference_posts()
    if not accounts:
        print("[StyleAnalyzer] 参考投稿データなし（reference_posts.jsonに投稿を追加してください）")
        return {}

    total_posts = sum(len(a.get("posts", [])) for a in accounts)
    print(f"[StyleAnalyzer] 分析開始: {len(accounts)}アカウント / {total_posts}投稿")

    corpus = _build_corpus(accounts)

    prompt = f"""以下は参考にしたい投稿文のサンプルです。
文体・語調・表現の特徴を詳細に分析してください。

{corpus}

以下の観点で分析してJSON形式で出力してください:

1. ending_patterns: よく使う語尾パターン（例: 「〜だった」「〜なんです」「〜と思う」）をリストで5〜8個
2. sentence_length_tendency: 文の長さの傾向（"short" / "long" / "mixed" のいずれか + 補足説明）
3. characteristic_phrases: よく使うフレーズ・口癖をリストで5〜8個
4. emotion_expression_style: 感情表現の特徴（驚き・共感・後悔などの出し方）を2〜3文で
5. hook_patterns: 冒頭フックのパターンをリストで3〜5個
6. rhythm_notes: 文章のリズム・テンポに関する特徴を1〜2文で
7. avoid_patterns: この文体では使われていない・避けている表現パターンをリストで3〜5個

JSON形式のみ出力（コードブロックなし）:"""

    try:
        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=1000,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = response.content[0].text.strip().replace("```json", "").replace("```", "").strip()
        profile = json.loads(raw)
    except Exception as e:
        print(f"[StyleAnalyzer] 分析失敗: {e}")
        return {}

    with open(STYLE_PROFILE_FILE, "w", encoding="utf-8") as f:
        json.dump(profile, f, ensure_ascii=False, indent=2)
    print(f"[StyleAnalyzer] 保存完了: {STYLE_PROFILE_FILE}")
    return profile
