"""
自アカウント Instagram 投稿パフォーマンス分析スクリプト
2日に1回 GitHub Actions から実行される（analyze.yml）。

フロー:
  1. Instagram Graph API で自分の投稿（フィード + リール）を最新50件取得
  2. 各投稿のインサイト（いいね数・リーチ・保存数・再生数）を取得
  3. Claude Haiku で上位パフォーマンス投稿の共通点を分析
  4. logs/self_analysis.json に保存

Usage:
  python3 scripts/analyze_self.py
"""
import datetime
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

import anthropic
import requests
from dotenv import load_dotenv

ENV_PATH = os.path.expanduser("~/Documents/Obsidian Vault/.env")
LOGS_DIR = ROOT / "logs"
OUTPUT_FILE = LOGS_DIR / "self_analysis.json"
JST = datetime.timezone(datetime.timedelta(hours=9))
IG_API = "https://graph.facebook.com/v25.0"

MAX_MEDIA = 50


def fetch_own_media(ig_user_id: str, access_token: str) -> list[dict]:
    """自分の投稿を最新 MAX_MEDIA 件取得"""
    r = requests.get(
        f"{IG_API}/{ig_user_id}/media",
        params={
            "fields": "id,caption,media_type,timestamp,like_count,comments_count,permalink",
            "limit": MAX_MEDIA,
            "access_token": access_token,
        },
        timeout=15,
    )
    if not r.ok:
        print(f"[SelfAnalysis] メディア取得失敗: {r.text[:150]}")
        return []
    return r.json().get("data", [])


def _fetch_insights(media_id: str, media_type: str, access_token: str) -> dict:
    is_video = media_type in ("REELS", "VIDEO")
    metrics = "reach,saved,plays,total_interactions" if is_video else "reach,saved,impressions"
    r = requests.get(
        f"{IG_API}/{media_id}/insights",
        params={"metric": metrics, "access_token": access_token},
        timeout=15,
    )
    if not r.ok:
        return {}
    insights = {}
    for item in r.json().get("data", []):
        val = item.get("values", [{}])[0].get("value") if item.get("values") else item.get("value", 0)
        insights[item["name"]] = val or 0
    return insights


def enrich_with_insights(media_list: list[dict], access_token: str) -> list[dict]:
    enriched = []
    for i, media in enumerate(media_list):
        if i > 0:
            time.sleep(0.5)
        insights = _fetch_insights(media["id"], media.get("media_type", "IMAGE"), access_token)
        enriched.append({**media, "insights": insights})
    return enriched


def _engagement_rate(media: dict) -> float:
    insights = media.get("insights", {})
    reach = insights.get("reach", 0)
    if not reach:
        return 0.0
    likes = media.get("like_count", 0)
    comments = media.get("comments_count", 0)
    saves = insights.get("saved", 0)
    return round((likes + comments + saves) / reach * 100, 2)


def _posting_hour_jst(timestamp: str) -> str:
    try:
        dt = datetime.datetime.fromisoformat(timestamp.replace("Z", "+00:00")).astimezone(JST)
        return f"{dt.hour:02d}:00"
    except Exception:
        return ""


def analyze_patterns(media_list: list[dict], client: anthropic.Anthropic) -> dict:
    """上位パフォーマンス投稿の共通点を Claude Haiku で分析"""
    sorted_media = sorted(
        [m for m in media_list if m.get("insights")],
        key=_engagement_rate,
        reverse=True,
    )
    top = sorted_media[:20]
    if not top:
        return {}

    records = []
    for m in top:
        insights = m.get("insights", {})
        ts = m.get("timestamp", "")[:16]
        hour = _posting_hour_jst(m.get("timestamp", ""))
        caption = (m.get("caption", "") or "")[:80]
        er = _engagement_rate(m)
        records.append(
            f"[{m.get('media_type','IMAGE')}] {ts} {hour} JST  "
            f"ER={er}% いいね={m.get('like_count',0)} "
            f"リーチ={insights.get('reach',0)} 保存={insights.get('saved',0)} "
            f"再生={insights.get('plays',0)}\n"
            f"  #タグ数={(m.get('caption','') or '').count('#')} "
            f"文字数={len(m.get('caption','') or '')}\n"
            f"  冒頭: {caption}"
        )

    sample_text = "\n---\n".join(records)
    prompt = f"""以下はInstagramアカウント「ryo_finance_ai」の上位パフォーマンス投稿データです（エンゲージメント率順）:

{sample_text}

以下の7項目をJSONで出力してください:
1. best_posting_hours: パフォーマンスが高い投稿時間帯リスト（例: ["21:00","12:00"]）
2. best_media_types: パフォーマンスが高いメディアタイプリスト（例: ["VIDEO","CAROUSEL_ALBUM"]）
3. optimal_hashtag_count: 最適なハッシュタグ数（整数）
4. optimal_caption_length: 最適なキャプション長の範囲（例: "200-350字"）
5. top_content_patterns: 高パフォーマンス投稿の共通パターン（3点リスト）
6. improvement_suggestions: 次の投稿への具体的な改善提案（3点リスト）
7. avg_engagement_rate: 上位投稿の平均エンゲージメント率（数値）

JSON形式のみ出力（コードブロックなし）:"""

    try:
        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=1000,
            messages=[{"role": "user", "content": prompt}],
        )
        text = response.content[0].text.strip().replace("```json", "").replace("```", "").strip()
        return json.loads(text)
    except Exception as e:
        print(f"[SelfAnalysis] パターン分析失敗: {e}")
        return {}


def save_result(media_list: list[dict], patterns: dict) -> Path:
    LOGS_DIR.mkdir(exist_ok=True)
    now = datetime.datetime.now(JST)

    summary = [
        {
            "id": m.get("id"),
            "media_type": m.get("media_type"),
            "timestamp": m.get("timestamp"),
            "permalink": m.get("permalink"),
            "like_count": m.get("like_count", 0),
            "comments_count": m.get("comments_count", 0),
            "reach": m.get("insights", {}).get("reach", 0),
            "saved": m.get("insights", {}).get("saved", 0),
            "plays": m.get("insights", {}).get("plays", 0),
            "engagement_rate": _engagement_rate(m),
            "caption_length": len(m.get("caption", "") or ""),
            "hashtag_count": (m.get("caption", "") or "").count("#"),
            "posting_hour": _posting_hour_jst(m.get("timestamp", "")),
        }
        for m in media_list[:30]
    ]

    data = {
        "generated_at": now.isoformat(),
        "total_posts_analyzed": len(media_list),
        "patterns": patterns,
        "top_posts": summary,
    }
    OUTPUT_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[SelfAnalysis] 保存完了: {OUTPUT_FILE}")
    return OUTPUT_FILE


def main() -> None:
    load_dotenv(ENV_PATH)

    ig_token = os.getenv("INSTAGRAM_ACCESS_TOKEN", "")
    ig_id = os.getenv("INSTAGRAM_BUSINESS_ID", "")
    api_key = os.getenv("ANTHROPIC_API_KEY", "")

    missing = [k for k, v in {
        "INSTAGRAM_ACCESS_TOKEN": ig_token,
        "INSTAGRAM_BUSINESS_ID": ig_id,
        "ANTHROPIC_API_KEY": api_key,
    }.items() if not v]
    if missing:
        print(f"エラー: 未設定の環境変数: {', '.join(missing)}", file=sys.stderr)
        sys.exit(1)

    client = anthropic.Anthropic(api_key=api_key)
    now_jst = datetime.datetime.now(JST)
    print(f"\n=== 自アカウント投稿分析 {now_jst.strftime('%Y-%m-%d %H:%M JST')} ===\n")

    print(f"[Step 1] 自分の投稿を最大{MAX_MEDIA}件取得...")
    media_list = fetch_own_media(ig_id, ig_token)
    if not media_list:
        print("投稿データが取得できませんでした。終了します。")
        sys.exit(0)

    type_counts: dict[str, int] = {}
    for m in media_list:
        t = m.get("media_type", "IMAGE")
        type_counts[t] = type_counts.get(t, 0) + 1
    print(f"  → {len(media_list)}件取得: {', '.join(f'{t}:{n}件' for t, n in type_counts.items())}")

    print(f"\n[Step 2] インサイト取得中（{len(media_list)}件）...")
    media_list = enrich_with_insights(media_list, ig_token)
    print("  → インサイト付与完了")

    print("\n[Step 3] Claudeでパターン分析中...")
    patterns = analyze_patterns(media_list, client)
    if patterns:
        print(f"  → 分析完了: ER平均={patterns.get('avg_engagement_rate', '?')}%")

    save_result(media_list, patterns)
    print("\n=== 完了 ===\n")


if __name__ == "__main__":
    main()
