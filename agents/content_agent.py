"""
コンテンツ生成エージェント
Claude APIを使い、曜日別テーマ × バズテンプレートで
マルチプラットフォーム投稿文を生成する。
プロンプトキャッシュで繰り返しコストを削減。
"""
import datetime
import json
import time
from pathlib import Path
import anthropic

THEMES_PATH = Path(__file__).parent.parent / "config" / "themes.json"
TEMPLATES_PATH = Path(__file__).parent.parent / "config" / "post_templates.json"

# キャッシュ対象のベースシステムプロンプト（変わらない部分）
BASE_SYSTEM_PROMPT = """あなたは金融×AI副業の専門家インフルエンサーです。
以下のペルソナと構造に従い、3プラットフォーム用の日本語投稿文を作成してください。

【ペルソナ】
- 金融機関（メガバンク）20年勤務の元バンカー・FP資格保持
- 現在はAI×副業で毎月の収入を大幅にアップ
- NISA・投資信託・節税・副業の実践的アドバイスを発信
- 読者はお金に不安を持つ20〜40代の会社員・主婦

【2026年アルゴリズム最優先シグナル】
シェア > 保存 > コメント > いいね の順で重要。
「友達に教えたい」「保存して後で読む」を誘発するコンテンツを作れ。

【プラットフォーム別スタイル】
Instagram (caption):
- 冒頭15字以内に強烈なフックを置く（驚き・数字・共感）
- 具体的な数字・事例を必ず1つ以上含める
- 保存・シェアを促すCTAを最後に
- 絵文字で読みやすく分割
- ハッシュタグは末尾に5個（2026年最適ルール）
- 500字以内

Threads (threads_text):
- 会話的でカジュアルなトーン
- 箇条書き・リスト形式を活用
- CTAはフォロー・いいね誘導
- ハッシュタグは3個のみ
- 300字以内（アフィリエイトリンクは別途自動付与）

X / Twitter (tweet):
- インパクトある1〜2文で完結
- 数字・データを必ず1つ入れる
- ハッシュタグ2個のみ
- 200字以内（末尾URLは別途自動付与）

【出力形式】
JSON形式のみ。余分なテキスト・コードブロック不要。
{
  "caption": "Instagram用500字以内",
  "threads_text": "Threads用300字以内",
  "tweet": "X用200字以内",
  "image_prompt": "英語の画像生成プロンプト",
  "alt_text": "画像説明（日本語50字以内）",
  "topic_summary": "テーマを一言で（日本語）",
  "template_used": "使用したテンプレートID"
}"""

# カルーセルモード用システムプロンプト（BASE_SYSTEM_PROMPT にスライド定義を追加）
CAROUSEL_SYSTEM_PROMPT = BASE_SYSTEM_PROMPT + """

【カルーセル投稿モード】
上記の通常フィールドに加え、carousel_slides フィールドを生成してください。

各スライドの構成:
{
  "slide_num": スライド番号（整数、1始まり）,
  "headline": "スライド見出し（15字以内、インパクト重視）",
  "body": "スライド本文（80字以内、絵文字可）",
  "image_prompt": "このスライド専用の英語画像プロンプト（50語以内、高品質・ノーテキスト指定含む）"
}

スライド数: テンプレートの carousel_structure に従い 5〜7枚。
- 1枚目: 必ずフック（保存・クリックを誘発する衝撃の見出し）
- 中間枚: テンプレート構成に沿ったコンテンツ
- 最終枚: 必ずCTA（フォロー・保存を促す行動喚起）

出力JSON（通常フィールド＋carousel_slides）:
{
  "caption": "Instagram用500字以内（カルーセル全体のキャプション）",
  "threads_text": "Threads用300字以内",
  "tweet": "X用200字以内",
  "image_prompt": "表紙スライド用英語プロンプト",
  "alt_text": "画像説明（日本語50字以内）",
  "topic_summary": "テーマを一言で（日本語）",
  "template_used": "使用したテンプレートID",
  "carousel_slides": [
    {"slide_num": 1, "headline": "...", "body": "...", "image_prompt": "..."},
    ...
  ]
}"""


def _load_themes() -> dict:
    with open(THEMES_PATH, encoding="utf-8") as f:
        return json.load(f)


def _load_templates() -> dict:
    with open(TEMPLATES_PATH, encoding="utf-8") as f:
        return json.load(f)


def select_template(date: datetime.date, override: "str | None" = None) -> dict:
    """
    テンプレートを選択して返す。
    override が指定されていればそのIDを使用。
    なければ日付のordinal % 5 で自動ローテーション。
    """
    data = _load_templates()
    if override and override in data["templates"]:
        tmpl = data["templates"][override]
        print(f"[ContentAgent] テンプレート指定: {tmpl['name']}")
        return tmpl

    order = data["rotation_rule"]["order"]
    idx = date.toordinal() % len(order)
    tmpl_id = order[idx]
    tmpl = data["templates"][tmpl_id]
    print(f"[ContentAgent] テンプレート自動選択: {tmpl['name']} ({tmpl_id})")
    return tmpl


def _build_user_prompt(weekday: int, date: datetime.date, template_id: "str | None", carousel: bool) -> "tuple[dict, str]":
    """ユーザープロンプトとテンプレートを構築して返す"""
    themes = _load_themes()
    theme = themes["weekday_themes"][str(weekday)]
    persona = themes["persona"]
    required_tags = " ".join(themes["required_tags"])
    tmpl = select_template(date, template_id)

    instruction = (
        "上記テーマ × テンプレートで carousel_slides を含むカルーセル投稿JSONを生成してください。"
        if carousel
        else "上記のテーマ × テンプレートを組み合わせたマルチプラットフォーム投稿JSONを生成してください。"
    )

    prompt = f"""【今日のテーマ】
曜日テーマ: {theme['name']}
トピック: {theme['topic']}
トーン: {theme['tone']}
必須ハッシュタグ: {required_tags}
推奨ハッシュタグ（5個の中から選ぶ）: {' '.join(tmpl['hashtag_hint'])}
画像スタイルヒント: {theme['image_style']} / {tmpl['image_style_addon']}

【使用テンプレート: {tmpl['name']}】
狙う感情: {tmpl['target_emotion']}
バズの仕組み: {tmpl['buzz_mechanism']}

フック指示: {tmpl['hook_instruction']}
本文指示: {tmpl['body_instruction']}
CTA指示: {tmpl['cta_instruction']}
カルーセル構成: {tmpl['carousel_structure']}

ペルソナ補足: {persona}

{instruction}
template_used には "{tmpl['id']}" を入れてください。"""

    return tmpl, prompt


def _call_claude(
    system_prompt: str,
    user_prompt: str,
    max_tokens: int,
    client: anthropic.Anthropic,
    error_label: str,
) -> dict:
    """Claude APIを呼び出してJSONを返す（リトライ付き）"""
    for attempt in range(3):
        try:
            response = client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=max_tokens,
                system=[
                    {
                        "type": "text",
                        "text": system_prompt,
                        "cache_control": {"type": "ephemeral"},
                    }
                ],
                messages=[{"role": "user", "content": user_prompt}],
            )
            text = response.content[0].text.strip()
            text = text.replace("```json", "").replace("```", "").strip()
            result = json.loads(text)
            print(
                f"[ContentAgent] トークン: 入力={response.usage.input_tokens}, "
                f"キャッシュ読込={getattr(response.usage, 'cache_read_input_tokens', 0)}"
            )
            return result
        except Exception as e:
            print(f"[ContentAgent] エラー (試行{attempt + 1}/3): {e}")
            if attempt < 2:
                time.sleep(10)

    raise RuntimeError(f"{error_label}に3回失敗しました")


def generate_content(
    weekday: int,
    client: anthropic.Anthropic,
    template_id: "str | None" = None,
    date: "datetime.date | None" = None,
) -> dict:
    """
    weekday    : 0=月曜 〜 6=日曜
    template_id: テンプレートID（省略時は日付で自動選択）
    date       : 基準日（省略時は今日）
    returns    : caption / threads_text / tweet / image_prompt / alt_text /
                 topic_summary / template_used
    """
    today = date or datetime.date.today()
    tmpl, user_prompt = _build_user_prompt(weekday, today, template_id, carousel=False)
    result = _call_claude(BASE_SYSTEM_PROMPT, user_prompt, 1500, client, "コンテンツ生成")
    print(f"[ContentAgent] 生成完了: {result.get('topic_summary', '')}")
    print(f"[ContentAgent] テンプレート: {result.get('template_used', tmpl['id'])}")
    return result


def generate_carousel_content(
    weekday: int,
    client: anthropic.Anthropic,
    template_id: "str | None" = None,
    date: "datetime.date | None" = None,
) -> dict:
    """
    カルーセル投稿用コンテンツを生成する。
    通常フィールドに加え carousel_slides リストを含むdictを返す。
    """
    today = date or datetime.date.today()
    tmpl, user_prompt = _build_user_prompt(weekday, today, template_id, carousel=True)

    for attempt in range(3):
        try:
            result = _call_claude(CAROUSEL_SYSTEM_PROMPT, user_prompt, 2500, client, "カルーセルコンテンツ生成")
            slides = result.get("carousel_slides")
            if not slides or len(slides) < 2:
                raise ValueError(
                    f"carousel_slides が不正です（取得値: {slides!r}）。LLMが構造を省略した可能性があります。"
                )
            print(f"[ContentAgent] カルーセル生成完了: {result.get('topic_summary', '')}")
            print(f"[ContentAgent] スライド数: {len(slides)}")
            print(f"[ContentAgent] テンプレート: {result.get('template_used', tmpl['id'])}")
            return result
        except Exception as e:
            print(f"[ContentAgent] エラー (試行{attempt + 1}/3): {e}")
            if attempt < 2:
                time.sleep(10)

    raise RuntimeError("カルーセルコンテンツ生成に3回失敗しました")


def list_templates() -> None:
    """利用可能なテンプレート一覧を表示"""
    data = _load_templates()
    today = datetime.date.today()
    order = data["rotation_rule"]["order"]
    auto_idx = today.toordinal() % len(order)
    auto_id = order[auto_idx]

    print(f"\n{'='*55}")
    print("  利用可能なテンプレート")
    print(f"{'='*55}")
    for tid, t in data["templates"].items():
        marker = " ← 今日の自動選択" if tid == auto_id else ""
        print(f"  {tid:<20} {t['name']}{marker}")
    print(f"{'='*55}\n")
