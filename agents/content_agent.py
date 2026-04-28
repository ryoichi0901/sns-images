"""
コンテンツ生成エージェント
Claude APIを使い、曜日別テーマ × バズテンプレートで
マルチプラットフォーム投稿文を生成する。
プロンプトキャッシュで繰り返しコストを削減。

自己評価ループ（Threads専用）:
  - 10点満点で採点（フック3/共感2/読みやすさ2/独自性2/CTA1）
  - 8点未満なら改善して最大3回再生成
  - 最終スコアをログに記録
"""
import datetime
import json
import re
import time
from pathlib import Path
import anthropic

THEMES_PATH = Path(__file__).parent.parent / "config" / "themes.json"
TEMPLATES_PATH = Path(__file__).parent.parent / "config" / "post_templates.json"
LOGS_DIR = Path(__file__).parent.parent / "logs"
BUZZ_ANALYSIS_FILE = LOGS_DIR / "buzz_analysis.json"
CTA_COUNTER_FILE = LOGS_DIR / "cta_counter.json"
STYLE_PROFILE_FILE = LOGS_DIR / "style_profile.json"

THREADS_SCORE_THRESHOLD = 8
THREADS_MAX_CHARS = 150
THREADS_EVAL_RETRIES = 3
CTA_INTERVAL = 3  # 何投稿に1回CTAを含めるか

# キャッシュ対象のベースシステムプロンプト（変わらない部分）
BASE_SYSTEM_PROMPT = """あなたは金融×AI副業の発信者「りょう」として、3プラットフォーム用の日本語投稿文を作成してください。

【キャラクターの軸】
「20年間まじめに銀行員やってたのに、副業解禁になった瞬間に一番ハマったのがAIだった」
このギャップが面白さの核心。真面目・堅い・慎重 × AI・副業・発信 のギャップを活かす。
完璧な専門家ではなく「試行錯誤している元銀行員」として描く。
読者はお金に不安を持つ20〜40代の会社員・主婦。

【属性の出し方（重要）】
- 「元銀行員」は週2回まで。毎投稿入れない。エピソードの文脈で自然に出す
  例）「銀行にいた頃は〜」「20年窓口にいて気づいたのは〜」
- 月7万・副業6ヶ月などの数字実績は月1〜2回のみ。信頼担保として使う
- 毎投稿出すのは「今の自分の感情・気づき・失敗」

【今日のりょうさんの感情（毎回必ず1つ混ぜること）】
以下のパターンからその日のテーマに合ったものを1つ選び、投稿に自然に混ぜること:
- 焦り系：「正直、最近焦ってる。このまま続けていいのか、ふと不安になる。」
- 気づき系：「昨日やってみて気づいたんだけど、思ってたより全然むずかしかった。」
- 失敗系：「やらかした。〇〇、完全に間違えてた。」
- 迷い系：「これ、書いていいか迷ったんだけど、正直に言うと〜」
- 発見系：「ずっと当たり前だと思ってたことが、実は違ったと気づいた瞬間があった。」
- 疲れ系：「今日ちょっとしんどくて、でもそういう日に限って気づくことがある。」
- 嬉しい系：「小さいことなんだけど、今日ちょっと嬉しいことがあった。」
- 自問系：「最近ずっと考えてることがあって、まだ答え出てないんだけど。」

【投稿トーン（全プラットフォーム共通・最重要）】
- 等身大の語りかけ口調：友達に話しかけるように自然に書く
- 自分の疑問・失敗・不安も素直に表現する（「正直、最初は半信半疑でした」「実は私も同じでした」）
- 典型例フレーズ: 「AI副業って、もう遅いのかな？🤔」「〜って思ったことありませんか？」
- 上から目線・断定的なトーンは避ける
- 「〜なんです」「〜なんですよ」「〜ですよね」等の自然な話し言葉を使う

【人間らしさのルール（最重要）】
以下を意図的に混ぜること:
- 文の長さを不均一にする（短い1語文 → 長い文 → また短い文）
- 言い直し・補足を入れる（「というか、」「正確には、」「あ、でも」）
- 断定を避ける箇所では曖昧にする（「〜な気がして」「〜だったと思う」）
- 体験の「前」の感情を入れる（「最初は正直めんどくさかった」「半信半疑だった」）

以下は絶対に使わない（AI感が出るNG表現）:
- 「まず〜次に〜そして〜」の列挙構造
- 「〜ことが大切です」「〜ことが重要です」
- 「ぜひ〜してみてください」
- 「いかがでしたか？」
- 体言止めの連続（「節税。副業。資産形成。」）

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
- コンパクト3部構成（各部を1行空けで区切る）:
  1.【フック】1文で読者を引き付ける冒頭
     ※ユーザープロンプトに指定された冒頭フレーズを必ず使うこと
  2.【体験・気づき】銀行員時代の体験 or 副業の変化を2〜3文で（各文を改行で区切る）
     「副業解禁○ヶ月目」「月7万」等の自分の実績を自然に入れる
  3.【締め/CTA】ユーザープロンプトのinclude_ctaフラグがTrueのときのみCTAを含める
     CTAなしの場合は気づき・教訓で締める
- 絶対ルール:
  - 150字以内（ハッシュタグを含む）
  - 1文1行で書く（句点「。」「！」「？」のあとに改行）
  - 段落間は1行空ける
  - 根拠不明の統計・パーセンテージは絶対に使わない（自分の数字のみ）
  - 「続きはプロフィールから↑」は使わない
- ハッシュタグは3個のみ（末尾）
- （アフィリエイトリンクは別途自動付与）

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


def _load_style_profile() -> "dict | None":
    """文体プロファイルを読み込む（style_profile.jsonが存在する場合のみ）"""
    if not STYLE_PROFILE_FILE.exists():
        return None
    try:
        with open(STYLE_PROFILE_FILE, encoding="utf-8") as f:
            profile = json.load(f)
        if not profile:
            return None
        print("[ContentAgent] 文体プロファイル読込完了")
        return profile
    except Exception as e:
        print(f"[ContentAgent] 文体プロファイル読込失敗（スキップ）: {e}")
        return None


def _load_buzz_analysis() -> "dict | None":
    """週次バズ投稿分析結果を読み込む"""
    if not BUZZ_ANALYSIS_FILE.exists():
        return None
    try:
        with open(BUZZ_ANALYSIS_FILE, encoding="utf-8") as f:
            data = json.load(f)
        patterns = data.get("patterns", {})
        hooks_count = len(patterns.get("top_hooks", []))
        print(f"[ContentAgent] バズ分析読込: フックパターン{hooks_count}件")
        return data
    except Exception as e:
        print(f"[ContentAgent] バズ分析読込失敗（スキップ）: {e}")
        return None


def _load_own_top_posts(limit: int = 10) -> "list[dict]":
    """post_log.jsonlから最新の投稿を読み込む"""
    post_log = LOGS_DIR / "post_log.jsonl"
    if not post_log.exists():
        return []
    records = []
    try:
        with open(post_log, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                rec = json.loads(line)
                if "topic_summary" in rec:
                    records.append(rec)
        return records[-limit:]
    except Exception as e:
        print(f"[ContentAgent] 自社投稿読込失敗（スキップ）: {e}")
        return []


def _read_post_count() -> int:
    """CTA管理用の投稿カウンターを読む"""
    if not CTA_COUNTER_FILE.exists():
        return 0
    try:
        with open(CTA_COUNTER_FILE, encoding="utf-8") as f:
            return json.load(f).get("total_posts", 0)
    except Exception:
        return 0


def _increment_post_count() -> int:
    """投稿カウンターをインクリメントして新しい値を返す"""
    count = _read_post_count() + 1
    with open(CTA_COUNTER_FILE, "w", encoding="utf-8") as f:
        json.dump({"total_posts": count}, f)
    return count


def _should_include_cta() -> bool:
    """現在の投稿にCTAを含めるべきか（CTA_INTERVAL投稿に1回）"""
    return _read_post_count() % CTA_INTERVAL == (CTA_INTERVAL - 1)


def _format_threads_text(text: str) -> str:
    """Threads投稿フォーマットを強制する: 150字以内・1文1行・段落間1行空け"""
    # 末尾のハッシュタグを分離
    hashtag_match = re.search(r'(\n*(?:\s*#\S+)+\s*)$', text)
    hashtags = ""
    body = text
    if hashtag_match:
        hashtags = hashtag_match.group(0).strip()
        body = text[: hashtag_match.start()].strip()

    # 段落に分割して各段落内を1文1行化
    paragraphs = [p.strip() for p in re.split(r'\n{2,}', body) if p.strip()]
    formatted_paragraphs = []
    for para in paragraphs:
        # 句点・感嘆符・疑問符で分割して各文を1行に
        sentences = re.split(r'(?<=[。！？])', para)
        lines = [s.strip() for s in sentences if s.strip()]
        formatted_paragraphs.append('\n'.join(lines))

    formatted_body = '\n\n'.join(formatted_paragraphs)

    # 本文を150字以内に収める（ハッシュタグ除く）
    max_body_chars = THREADS_MAX_CHARS - (len(hashtags) + 2 if hashtags else 0)
    if len(formatted_body) > max_body_chars:
        trimmed = formatted_body[:max_body_chars]
        # 句点で切る
        last_end = max(
            trimmed.rfind('。'),
            trimmed.rfind('！'),
            trimmed.rfind('？'),
        )
        if last_end > max_body_chars // 2:
            formatted_body = trimmed[: last_end + 1]
        else:
            formatted_body = trimmed.rstrip() + '…'

    if hashtags:
        return f"{formatted_body}\n\n{hashtags}"
    return formatted_body


def _evaluate_threads_text(
    text: str,
    client: anthropic.Anthropic,
    include_cta: bool,
) -> dict:
    """Threads投稿を10点満点で評価して返す。
    返り値: {"score": int, "breakdown": dict, "improvements": str}
    """
    cta_note = (
        "（今回はCTAあり投稿です。CTAの有無・質を採点すること）"
        if include_cta
        else "（今回はCTAなし投稿です。CTAがなければ自動的にCTA項目は1点付与）"
    )
    prompt = f"""以下のThreads投稿を10点満点で採点してください。{cta_note}

【投稿文】
{text}

【採点基準】
- フック強さ（満点3点）: 冒頭1文で読者を引き付けるか。具体的な数字・問い・矛盾を含むか
- 共感・価値（満点2点）: 読者の悩みに刺さるか。有益な体験談・情報があるか
- 文字数・読みやすさ（満点2点）: 150字以内か・1文1行か・段落間が適切か
- 独自性（満点2点）: 銀行員ペルソナが出ているか・他のアカウントにない視点があるか
- CTA（満点1点）: CTAなし投稿は自動1点。CTAあり投稿はその質で採点

JSON形式のみ出力（コードブロックなし）:
{{"score": 8, "breakdown": {{"hook": 2, "empathy": 2, "readability": 1, "originality": 2, "cta": 1}}, "improvements": "フックをより具体的な数字で始めると良い"}}"""

    try:
        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=300,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = response.content[0].text.strip().replace("```json", "").replace("```", "").strip()
        result = json.loads(raw)
        return {
            "score": int(result.get("score", 0)),
            "breakdown": result.get("breakdown", {}),
            "improvements": result.get("improvements", ""),
        }
    except Exception as e:
        print(f"[ContentAgent] 評価エラー: {e}")
        return {"score": 0, "breakdown": {}, "improvements": "評価に失敗しました"}


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
    buzz_analysis: "dict | None" = None,
    own_top_posts: "list[dict] | None" = None,
    include_cta: bool = True,
    style_profile: "dict | None" = None,
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

    cta_instruction = (
        f"【Threads CTA（threads_textの末尾に使うこと・今回はCTAあり）】\n{threads_cta}"
        if include_cta
        else "【Threads CTA】今回はCTAなし。気づき・教訓で自然に締めること。"
    )

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

{cta_instruction}

【Threads include_cta フラグ: {"True" if include_cta else "False"}】

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

    # バズ投稿分析を注入
    if buzz_analysis:
        patterns = buzz_analysis.get("patterns", {})
        top_hooks = "\n".join(
            f"  - {h}" for h in patterns.get("top_hooks", [])
        ) or "  データなし"
        diff_tips = "\n".join(
            f"  - {t}" for t in patterns.get("differentiation_tips", [])
        ) or "  データなし"
        own_insights = buzz_analysis.get("own_post_insights", {})
        suggestions = "\n".join(
            f"  - {s}" for s in own_insights.get("improvement_suggestions", [])
        ) or "  データなし"

        prompt += f"""

【週次バズ分析（Threads投稿に最優先で反映すること）】
▼ バズっているフックパターン:
{top_hooks}

▼ ryo_finance_aiの差別化ポイント:
{diff_tips}

▼ 自社投稿の改善提案:
{suggestions}"""

    # 自社の過去投稿を注入
    if own_top_posts:
        recent_topics = "\n".join(
            f"  - {p.get('topic_summary', '')} [{p.get('template_used', '-')}]"
            for p in own_top_posts[-5:]
            if p.get("topic_summary")
        )
        if recent_topics:
            prompt += f"""

【直近の自社投稿テーマ（重複を避けること）】
{recent_topics}"""

    # 文体プロファイルを注入
    if style_profile:
        endings = "・".join(style_profile.get("ending_patterns", [])[:6])
        phrases = "・".join(style_profile.get("characteristic_phrases", [])[:6])
        hooks = "\n".join(
            f"  - {h}" for h in style_profile.get("hook_patterns", [])
        ) or "  データなし"
        avoid = "・".join(style_profile.get("avoid_patterns", [])[:5])
        emotion_style = style_profile.get("emotion_expression_style", "")
        length_tendency = style_profile.get("sentence_length_tendency", "")
        rhythm = style_profile.get("rhythm_notes", "")

        prompt += f"""

【参考文体プロファイル（この文体に近づけること）】
▼ よく使う語尾: {endings or "データなし"}
▼ 文長の傾向: {length_tendency or "データなし"}
▼ 口癖・フレーズ: {phrases or "データなし"}
▼ 感情表現の特徴: {emotion_style or "データなし"}
▼ フックパターン:
{hooks}
▼ リズム: {rhythm or "データなし"}
▼ この文体では使わない表現: {avoid or "データなし"}

上記プロファイルを参考にしながら、自然な語り口で生成してください。"""

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


def _threads_self_eval_loop(
    weekday: int,
    today: datetime.date,
    template_id: "str | None",
    client: anthropic.Anthropic,
    research_context: "dict | None",
    buzz_analysis: "dict | None",
    own_top_posts: "list[dict]",
    include_cta: bool,
    style_profile: "dict | None" = None,
) -> "tuple[str, int]":
    """
    Threads投稿テキストを自己評価ループで生成する。
    スコアが閾値未満なら改善指示を加えて最大THREADS_EVAL_RETRIES回再生成。
    Returns: (最終threads_text, 最終スコア)
    """
    improvements = ""
    best_text = ""
    best_score = 0

    for attempt in range(THREADS_EVAL_RETRIES):
        extra = ""
        if improvements:
            extra = f"\n\n【前回の改善指示（必ず反映すること）】\n{improvements}"

        tmpl, user_prompt = _build_user_prompt(
            weekday, today, template_id,
            carousel=False,
            research_context=research_context,
            buzz_analysis=buzz_analysis,
            own_top_posts=own_top_posts,
            include_cta=include_cta,
            style_profile=style_profile,
        )
        full_prompt = user_prompt + extra

        result = _call_claude(BASE_SYSTEM_PROMPT, full_prompt, 1500, client, f"Threads生成（試行{attempt + 1}）")
        threads_text = result.get("threads_text", "")
        if not threads_text:
            continue

        formatted = _format_threads_text(threads_text)
        eval_result = _evaluate_threads_text(formatted, client, include_cta)
        score = eval_result.get("score", 0)

        print(
            f"[ContentAgent] Threads評価 試行{attempt + 1}/{THREADS_EVAL_RETRIES}: "
            f"{score}/10 (フック:{eval_result['breakdown'].get('hook',0)} "
            f"共感:{eval_result['breakdown'].get('empathy',0)} "
            f"読みやすさ:{eval_result['breakdown'].get('readability',0)} "
            f"独自性:{eval_result['breakdown'].get('originality',0)} "
            f"CTA:{eval_result['breakdown'].get('cta',0)})"
        )

        if score > best_score:
            best_score = score
            best_text = formatted
            # 最終試行では最良版をそのまま使う
            if attempt == THREADS_EVAL_RETRIES - 1:
                break

        if score >= THREADS_SCORE_THRESHOLD:
            print(f"[ContentAgent] Threads合格: {score}/10")
            return best_text, best_score

        improvements = eval_result.get("improvements", "")
        print(f"[ContentAgent] Threads再生成: {improvements}")
        time.sleep(5)

    return best_text, best_score


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
                 topic_summary / template_used / threads_score
    """
    today = date or datetime.date.today()
    research_context = _load_research_context(today)
    buzz_analysis = _load_buzz_analysis()
    own_top_posts = _load_own_top_posts()
    style_profile = _load_style_profile()
    include_cta = _should_include_cta()

    print(f"[ContentAgent] CTA{'あり' if include_cta else 'なし'} (投稿数:{_read_post_count()})")

    # 通常コンテンツ生成（Threads以外）
    tmpl, user_prompt = _build_user_prompt(
        weekday, today, template_id,
        carousel=False,
        research_context=research_context,
        buzz_analysis=buzz_analysis,
        own_top_posts=own_top_posts,
        include_cta=include_cta,
        style_profile=style_profile,
    )
    result = _call_claude(BASE_SYSTEM_PROMPT, user_prompt, 1500, client, "コンテンツ生成")

    # Threads自己評価ループで高品質テキストに差し替え
    print("[ContentAgent] Threads自己評価ループ開始...")
    threads_text, threads_score = _threads_self_eval_loop(
        weekday, today, template_id, client,
        research_context, buzz_analysis, own_top_posts, include_cta,
        style_profile=style_profile,
    )
    if threads_text:
        result["threads_text"] = threads_text
    result["threads_score"] = threads_score

    # CTA投稿カウンターをインクリメント
    new_count = _increment_post_count()
    print(f"[ContentAgent] 生成完了: {result.get('topic_summary', '')} (Threadsスコア:{threads_score}/10, 累計投稿:{new_count})")
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
    buzz_analysis = _load_buzz_analysis()
    own_top_posts = _load_own_top_posts()
    style_profile = _load_style_profile()
    include_cta = _should_include_cta()

    tmpl, user_prompt = _build_user_prompt(
        weekday, today, template_id,
        carousel=True,
        research_context=research_context,
        buzz_analysis=buzz_analysis,
        own_top_posts=own_top_posts,
        include_cta=include_cta,
        style_profile=style_profile,
    )

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

            # カルーセルのThreadsテキストもフォーマット強制
            if result.get("threads_text"):
                result["threads_text"] = _format_threads_text(result["threads_text"])

            _increment_post_count()
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
