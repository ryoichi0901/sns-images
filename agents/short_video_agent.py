"""
ショート動画台本生成エージェント
Claude Haiku APIを使い、曜日別テーマ × 共感→ストーリー→CTA構成で
YouTube Shorts / TikTok / Instagram Reels向け60秒台本を生成する。
"""
import datetime
import json
import time
from pathlib import Path
from typing import Optional

import anthropic

from agents.content_agent import _load_themes, select_template, _load_research_context, _load_buzz_analysis

LOGS_DIR = Path(__file__).parent.parent / "logs"
LOGS_DIR.mkdir(exist_ok=True)

SHORT_VIDEO_SYSTEM_PROMPT = """あなたは金融×AI副業の専門家インフルエンサーです。
以下のペルソナで、縦型ショート動画（60秒）の台本を生成してください。

【ペルソナ】
- 金融機関（メガバンク）20年勤務の元バンカー・FP資格保持
- 副業解禁後3ヶ月でAIで月5万、6ヶ月で月7万を達成。今も右肩上がり
- 読者はお金に不安を持つ20〜40代の会社員・主婦

【投稿トーン（最重要）】
- 等身大の語りかけ口調：友達に話しかけるように自然に書く
- 冒頭は必ず「元銀行員の私が〜」でキャラクター軸を出す
- 「していた→損をした→だから話す」の因果の流れを意識する
- 「〜なんです」「〜なんですよ」「〜ですよね」等の自然な話し言葉を使う
- 上から目線・断定的なトーンは避ける

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
- 収益約束: 「月〇万円稼げます」「〇万円の副収入が作れます」「必ず稼げる」
- 資産断言: 「〇年で〇万円になります」「〇%のリターンが得られる」「確実に資産が増える」
- 投資断定: 「〇〇を買えばいい」「今が買い時」「必ず儲かる」

代わりに一人称・体験談ベースのナレーションを使う:
- 「私の場合は〜だったんです」
- 「実際にやってみて気づいたのは〜」
- 「個人差はあると思うんですが、私は〜」

【台本構成：共感→ストーリー→CTA（固定）】
シーン1 empathy（0〜10秒）:
  - 「元銀行員の私が〜」でキャラ軸を出した共感フレーズで始める
  - テロップは20字以内

シーン2 story1（10〜25秒）：「していた」
  - 銀行員時代にやっていたこと・信じていたことの描写

シーン3 story2（25〜40秒）：「損をした・気づいた」
  - 転機・失敗・発見。何が間違っていたかを具体的に

シーン4 story3（40〜50秒）：「だから話す」
  - 変化・成果・今やっていること（私の場合は〜）

シーン5 cta（50〜60秒）:
  - テーマ別CTAをそのまま自然な会話形式で使う
  - 「続きはプロフィールから」を必ず含める

【出力形式】JSON形式のみ。余分なテキスト・コードブロック不要。
{
  "title": "タイトル案（60字以内）",
  "thumbnail": "サムネイル文字案（2行、改行は\\nで）",
  "hook_sub": "フックシーンのサブテキスト（ペルソナの実績・経歴を一言で。例: 副業解禁6ヶ月→月7万達成。20字以内）",
  "cta_text": "CTA全文（プロフィールリンク誘導含む）",
  "scenes": [
    {"id": "empathy", "start": 0,  "end": 10, "voice": "ナレーション全文", "telop": "テロップ（20字以内）"},
    {"id": "story1",  "start": 10, "end": 25, "voice": "...", "telop": "..."},
    {"id": "story2",  "start": 25, "end": 40, "voice": "...", "telop": "..."},
    {"id": "story3",  "start": 40, "end": 50, "voice": "...", "telop": "..."},
    {"id": "cta",     "start": 50, "end": 60, "voice": "...", "telop": "..."}
  ],
  "hashtags": {
    "youtube": ["#Shorts", ...],
    "tiktok":  [...],
    "reels":   [...]
  }
}"""


def _get_theme_group(themes: dict, weekday: int) -> dict:
    """曜日からテーマグループ情報を返す"""
    day_theme = themes["weekday_themes"][str(weekday)]
    group_key = day_theme.get("theme_group", "investment")
    return themes.get("theme_groups", {}).get(group_key, {})


def generate_short_video_script(
    weekday: int,
    client: anthropic.Anthropic,
    template_id: Optional[str] = None,
    date: Optional[datetime.date] = None,
) -> dict:
    """
    weekday    : 0=月曜 〜 6=日曜
    template_id: テンプレートID（省略時は日付で自動選択）
    date       : 基準日（省略時は今日）
    returns    : title / thumbnail / cta_text / scenes / hashtags
    """
    today = date or datetime.date.today()
    themes = _load_themes()
    theme = themes["weekday_themes"][str(weekday)]
    group = _get_theme_group(themes, weekday)
    tmpl = select_template(today, template_id)
    research_context = _load_research_context(today)
    buzz_analysis = _load_buzz_analysis()

    character_phrase = group.get("character_phrase", "元銀行員の私が経験から話す")
    cta_text = group.get("cta_text", "続きはプロフィールから")
    group_label = group.get("label", "")

    user_prompt = f"""【今日のテーマ】
テーマグループ: {group_label}
曜日テーマ: {theme['name']}
トピック: {theme['topic']}
トーン: {theme['tone']}

【キャラ軸フレーズ（必ずempathyシーンの冒頭に反映すること）】
{character_phrase}

【このテーマのCTA（cta_textフィールドに使うこと）】
{cta_text}

【使用テンプレート: {tmpl['name']}】
狙う感情: {tmpl['target_emotion']}
フック指示: {tmpl['hook_instruction']}"""

    if research_context:
        comp = research_context.get("competitor_analysis", {})
        trend = research_context.get("trend_analysis", {})
        hooks = "\n".join(f"  - {h}" for h in comp.get("high_engagement_hooks", []))
        kw = ", ".join(trend.get("trending_keywords", []))
        user_prompt += f"""

【競合・トレンドリサーチ結果（台本に反映すること）】
▼ バズっているフック:
{hooks or "  データなし"}
▼ トレンドKW: {kw or "データなし"}
▼ バズパターン: {comp.get("buzz_patterns", "データなし")}"""

    if buzz_analysis:
        patterns = buzz_analysis.get("patterns", {})
        top_hooks = "\n".join(
            f"  - {h}" for h in patterns.get("top_hooks", [])
        ) or "  データなし"
        diff_tips = "\n".join(
            f"  - {t}" for t in patterns.get("differentiation_tips", [])
        ) or "  データなし"
        user_prompt += f"""

【週次バズ分析（フックとシーン構成に反映すること）】
▼ バズっているフックパターン:
{top_hooks}
▼ 差別化ポイント:
{diff_tips}"""

    user_prompt += """

上記テーマで、共感→ストーリー→CTAの5シーン構成のショート動画台本JSONを生成してください。
empathyシーンは「元銀行員の私が〜」で始め、キャラ軸フレーズを反映すること。
story1〜3は「していた→損をした→だから話す」の因果の流れで構成すること。"""

    for attempt in range(3):
        try:
            response = client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=1500,
                system=[
                    {
                        "type": "text",
                        "text": SHORT_VIDEO_SYSTEM_PROMPT,
                        "cache_control": {"type": "ephemeral"},
                    }
                ],
                messages=[{"role": "user", "content": user_prompt}],
            )
            text = response.content[0].text.strip()
            text = text.replace("```json", "").replace("```", "").strip()
            result = json.loads(text)

            scenes = result.get("scenes", [])
            if len(scenes) != 5:
                raise ValueError(f"scenes は5シーン必要です（取得数: {len(scenes)}）")
            scene_ids = [s["id"] for s in scenes]
            if scene_ids[0] != "empathy" or scene_ids[-1] != "cta":
                raise ValueError(f"先頭=empathy / 末尾=cta が必要です（取得: {scene_ids}）")

            # cta_text が未生成の場合はテーマグループのデフォルトを使用
            if not result.get("cta_text"):
                result["cta_text"] = cta_text

            print(
                f"[ShortVideoAgent] トークン: 入力={response.usage.input_tokens}, "
                f"キャッシュ読込={getattr(response.usage, 'cache_read_input_tokens', 0)}"
            )
            print(f"[ShortVideoAgent] 生成完了: {result.get('title', '')}")
            print(f"[ShortVideoAgent] CTA: {result.get('cta_text', '')[:40]}")
            return result

        except Exception as e:
            print(f"[ShortVideoAgent] エラー (試行{attempt + 1}/3): {e}")
            if attempt < 2:
                time.sleep(10)

    raise RuntimeError("ショート動画台本生成に3回失敗しました")


def save_script(script: dict, date: Optional[datetime.date] = None) -> Path:
    """台本JSONをlogsディレクトリに保存してパスを返す"""
    today = date or datetime.date.today()
    date_str = today.strftime("%Y%m%d")
    path = LOGS_DIR / f"script_{date_str}.json"
    path.write_text(json.dumps(script, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[ShortVideoAgent] 台本保存: {path}")
    return path
