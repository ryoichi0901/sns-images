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
LOGS_DIR = Path(__file__).parent.parent / "logs"

# キャッシュ対象のベースシステムプロンプト（変わらない部分）
BASE_SYSTEM_PROMPT = """あなたは金融×AI副業の専門家インフルエンサーです。
以下のペルソナと構造に従い、3プラットフォーム用の日本語投稿文を作成してください。

【ペルソナ】
- 金融機関（メガバンク）20年勤務の元バンカー・FP資格保持
- 現在はAI×副業で毎月の収入を大幅にアップ
- NISA・投資信託・節税・副業の実践的アドバイスを発信
- 読者はお金に不安を持つ20〜40代の会社員・主婦

【投稿トーン（全プラットフォーム共通・最重要）】
- 等身大の語りかけ口調：友達に話しかけるように自然に書く
- 自分の疑問・失敗・不安も素直に表現する（「正直、最初は半信半疑でした」「実は私も同じでした」）
- 典型例フレーズ: 「AI副業って、もう遅いのかな？🤔」「〜って思ったことありませんか？」
- 上から目線・断定的なトーンは避ける
- 「〜なんです」「〜なんですよ」「〜ですよね」等の自然な話し言葉を使う

【コンプライアンス（必須遵守・違反厳禁）】
以下の表現は絶対に使わない:
- 収益約束: 「月〇万円稼げる」「〇万円の副収入が作れます」「必ず稼げる」「誰でも月収〇万円」
- 資産断言: 「〇年で〇万円になります」「〇%のリターンが得られる」「確実に資産が増える」
- 投資断定: 「〇〇を買えばいい」「今が買い時」「必ず儲かる」「損しない方法」

代わりに一人称・体験談ベースの表現を使う:
- 「私の場合は〜だった」（体験として語る）
- 「〜という考え方もある」（一つの見方として提示）
- 「実際に試してみた結果〜でした」（体験談）
- 「個人差はありますが、私は〜」（免責を自然に含める）
- 「保証はできませんが、体験として〜」

【2026年アルゴリズム最優先シグナル】
シェア > 保存 > コメント > いいね の順で重要。
「友達に教えたい」「保存して後で読む」を誘発するコンテンツを作れ。

【プラットフォーム別スタイル】
Instagram (caption):
- 共感→ストーリー→CTA の3部構成（各パートを空行で区切る）:
  ①【共感】読者の感情・疑問に寄り添う2〜3行
    例: 「AI副業って、もう遅いのかな？🤔 ...正直、2年前の私も同じこと思ってました」
  ②【ストーリー】ペルソナの実体験・失敗→変化を4〜6行で描写（具体的な数字必須）
  ③【CTA】保存・フォロー・コメントを促す1〜2行
- 絵文字を適度に使い読みやすく分割
- ハッシュタグは末尾に5個（2026年最適ルール）
- 500字以内

Threads (threads_text):
- 5ステップ構成（各ステップを空行で区切る）:
  1.【冒頭】テーマ別の冒頭フレーズ（現在進行形の数字 or 銀行員時代の矛盾）
     ※ユーザープロンプトに指定された冒頭フレーズを必ず使うこと
  2.【体験】銀行員時代の具体的な場面（数字・会話・状況）
  3.【変化】副業解禁後の変化（「副業解禁○ヶ月目」の形で月数入り）
  4.【気づき】読者への教訓・気づき（断言でなく「〜だと思う」等）
  5.【CTA】テーマ別の問いかけCTA（下記のいずれか）
     - 読者への問いかけ：「あなたは〇〇、どうですか？」
     - 共感誘導：「同じ状況の人にシェアしてください」
     - 保存促進：「後で読み返せるよう保存しておいてください」
- 必須ルール:
  - 根拠不明の統計・パーセンテージは絶対に使わない（自分の数字のみ）
  - 「副業解禁○ヶ月」「月7万」等の自分の実績を自然に入れる
  - 「続きはプロフィールから↑」は使わない
- ハッシュタグは3個のみ（末尾）
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

スライド数: 必ず7枚（固定）。以下の構成に従うこと:
- 1枚目: フック（保存・クリックを誘発する衝撃の見出し）
- 2枚目: 問題提起（読者の悩みを深掘り）
- 3〜5枚目: 解決策・ノウハウ（各ポイントを1枚ずつ、具体的な数字・手順を含む）
- 6枚目: 実績・証拠（数字・比較・実例で裏付け）
- 7枚目: CTA（フォロー・保存・コメントを促す行動喚起）

各スライドの image_prompt は次のガイドラインでビジュアルを差別化すること:
- 1枚目: 大胆・高コントラスト・衝撃的な構図
- 2枚目: クローズアップ・感情的・ドラマチック照明
- 3〜5枚目: データ可視化・フラットレイ・ミニマル（各枚でカラーパレットを変える）
- 6枚目: 比較・分割画面・クリーンな現代的デザイン
- 7枚目: 上昇・達成感・ゴールドアクセント・シンメトリー構図

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


def _load_research_context(date: datetime.date) -> "dict | None":
    """当日の競合・トレンドリサーチ結果を自動読込する"""
    path = LOGS_DIR / f"research_context_{date.strftime('%Y%m%d')}.json"
    if not path.exists():
        print("[ContentAgent] リサーチコンテキストなし（スキップ）")
        return None
    try:
        with open(path, encoding="utf-8") as f:
            ctx = json.load(f)
        comp_count = len(ctx.get("competitor_analysis", {}).get("top_buzz_posts", []))
        kw_count = len(ctx.get("trend_analysis", {}).get("trending_keywords", []))
        print(f"[ContentAgent] リサーチコンテキスト読込: バズ投稿{comp_count}件 / トレンドKW{kw_count}件")
        return ctx
    except Exception as e:
        print(f"[ContentAgent] リサーチコンテキスト読込失敗（スキップ）: {e}")
        return None


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


def _build_user_prompt(
    weekday: int,
    date: datetime.date,
    template_id: "str | None",
    carousel: bool,
    research_context: "dict | None" = None,
) -> "tuple[dict, str]":
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

    # テーマグループのキャラ軸・CTA を取得
    group_key = theme.get("theme_group", "investment")
    group = themes.get("theme_groups", {}).get(group_key, {})
    character_phrase = group.get("character_phrase", "")
    threads_cta = group.get("cta_text", "コメントで教えてください")

    prompt = f"""【今日のテーマ】
曜日テーマ: {theme['name']}
テーマグループ: {group.get('label', '')}
トピック: {theme['topic']}
トーン: {theme['tone']}
必須ハッシュタグ: {required_tags}
推奨ハッシュタグ（5個の中から選ぶ）: {' '.join(tmpl['hashtag_hint'])}
画像スタイルヒント: {theme['image_style']} / {tmpl['image_style_addon']}

【Threads冒頭フレーズ（threads_textの冒頭に必ず使うこと）】
{character_phrase}

【Threads CTA（threads_textの末尾に使うこと）】
{threads_cta}

【使用テンプレート: {tmpl['name']}】
狙う感情: {tmpl['target_emotion']}
バズの仕組み: {tmpl['buzz_mechanism']}

フック指示: {tmpl['hook_instruction']}
本文指示: {tmpl['body_instruction']}
CTA指示: {tmpl['cta_instruction']}
カルーセル構成: {tmpl['carousel_structure']}

ペルソナ補足: {persona}"""

    # リサーチコンテキストがある場合はプロンプトに注入
    if research_context:
        comp = research_context.get("competitor_analysis", {})
        trend = research_context.get("trend_analysis", {})
        strat = research_context.get("strategic_recommendations", {})

        buzz_hooks = "\n".join(
            f"  - {h}" for h in comp.get("high_engagement_hooks", [])
        ) or "  データなし"
        hot_topics = "\n".join(
            f"  - {t}" for t in trend.get("hot_topics", [])
        ) or "  データなし"
        trending_kw = ", ".join(trend.get("trending_keywords", [])) or "データなし"

        prompt += f"""

【競合・トレンドリサーチ結果（必ずコンテンツに反映すること）】
▼ 現在バズっているフック・パターン:
{buzz_hooks}

▼ 今週のトレンドキーワード: {trending_kw}

▼ 注目トピック:
{hot_topics}

▼ バズ投稿の共通パターン:
  {comp.get('buzz_patterns', 'データなし')}

▼ 推奨コンテンツ方向性:
  フック: {strat.get('hook_direction', '-')}
  切り口: {strat.get('content_angle', '-')}

上記リサーチ結果を最大限に取り込み、現在バズっているトレンドに乗ったコンテンツを生成してください。"""

    prompt += f"""

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
    research_context = _load_research_context(today)
    tmpl, user_prompt = _build_user_prompt(weekday, today, template_id, carousel=False, research_context=research_context)
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
    research_context = _load_research_context(today)
    tmpl, user_prompt = _build_user_prompt(weekday, today, template_id, carousel=True, research_context=research_context)

    for attempt in range(3):
        try:
            result = _call_claude(CAROUSEL_SYSTEM_PROMPT, user_prompt, 2500, client, "カルーセルコンテンツ生成")
            slides = result.get("carousel_slides")
            if not slides or len(slides) < 5:
                raise ValueError(
                    f"carousel_slides が不足しています（取得数: {len(slides) if slides else 0}枚）。7枚必要です。"
                )
            if len(slides) > 7:
                slides = slides[:7]
                result["carousel_slides"] = slides
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
