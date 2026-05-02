"""
自アカウント Instagram 投稿パフォーマンス分析スクリプト
2日に1回 GitHub Actions から実行される（analyze.yml）。

必要な権限: instagram_basic のみ（instagram_manage_insights 不要）

フロー:
  1. Instagram Graph API でフォロワー数を取得
  2. 自分の投稿（フィード + リール）を最新50件取得
     取得フィールド: like_count, comments_count, media_type, timestamp, caption
  3. Python でエンゲージメント率・曜日/時間帯・メディアタイプ・キャプション相関を集計
  4. Claude Haiku で集計結果を解釈・改善提案を生成
  5. logs/self_analysis.json に保存

Usage:
  python3 scripts/analyze_self.py
"""
import collections
import datetime
import json
import os
import sys
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
DAY_NAMES = ["月", "火", "水", "木", "金", "土", "日"]


# ---------- API取得 ----------

def fetch_followers_count(ig_user_id: str, access_token: str) -> int:
    r = requests.get(
        f"{IG_API}/{ig_user_id}",
        params={"fields": "followers_count", "access_token": access_token},
        timeout=15,
    )
    if not r.ok:
        print(f"[SelfAnalysis] フォロワー数取得失敗: {r.text[:120]}")
        return 0
    return r.json().get("followers_count", 0)


def fetch_own_media(ig_user_id: str, access_token: str) -> list[dict]:
    """基本メディアAPIで投稿を最新 MAX_MEDIA 件取得（Insights権限不要）"""
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


# ---------- 集計ヘルパー ----------

def _parse_jst(timestamp: str) -> "datetime.datetime | None":
    try:
        return datetime.datetime.fromisoformat(
            timestamp.replace("Z", "+00:00")
        ).astimezone(JST)
    except Exception:
        return None


def _engagement_rate(media: dict, followers: int) -> float:
    if not followers:
        return 0.0
    likes = media.get("like_count", 0)
    comments = media.get("comments_count", 0)
    return round((likes + comments) / followers * 100, 3)


def _caption_stats(caption: str) -> tuple[int, int]:
    """(文字数, ハッシュタグ数) を返す"""
    text = caption or ""
    return len(text), text.count("#")


def compute_stats(media_list: list[dict], followers: int) -> dict:
    """
    投稿リストから以下を集計して返す:
    - top_posts: ER上位10件
    - by_weekday: 曜日別 avg ER
    - by_hour: 時間帯別 avg ER
    - by_media_type: メディアタイプ別 avg ER / 件数
    - caption_length_buckets: 文字数帯別 avg ER
    - hashtag_count_buckets: ハッシュタグ数帯別 avg ER
    """
    enriched = []
    for m in media_list:
        dt = _parse_jst(m.get("timestamp", ""))
        cap_len, tag_cnt = _caption_stats(m.get("caption", ""))
        er = _engagement_rate(m, followers)
        enriched.append({
            **m,
            "er": er,
            "dt": dt,
            "weekday": dt.weekday() if dt else None,
            "hour": dt.hour if dt else None,
            "caption_length": cap_len,
            "hashtag_count": tag_cnt,
        })

    # ER上位10件
    top_posts = sorted(enriched, key=lambda x: x["er"], reverse=True)[:10]
    top_posts_out = [
        {
            "permalink": p.get("permalink", ""),
            "media_type": p.get("media_type"),
            "timestamp_jst": p["dt"].strftime("%Y-%m-%d %H:%M") if p["dt"] else "",
            "like_count": p.get("like_count", 0),
            "comments_count": p.get("comments_count", 0),
            "er": p["er"],
            "caption_length": p["caption_length"],
            "hashtag_count": p["hashtag_count"],
            "caption_head": (p.get("caption", "") or "")[:80],
        }
        for p in top_posts
    ]

    # 曜日別
    wd_buckets: dict[int, list[float]] = collections.defaultdict(list)
    for m in enriched:
        if m["weekday"] is not None:
            wd_buckets[m["weekday"]].append(m["er"])
    by_weekday = {
        DAY_NAMES[wd]: round(sum(ers) / len(ers), 3)
        for wd, ers in sorted(wd_buckets.items())
        if ers
    }

    # 時間帯別（3時間ブロック）
    hour_buckets: dict[str, list[float]] = collections.defaultdict(list)
    for m in enriched:
        if m["hour"] is not None:
            block = f"{(m['hour'] // 3) * 3:02d}:00-{(m['hour'] // 3) * 3 + 2:02d}:59"
            hour_buckets[block].append(m["er"])
    by_hour = {
        block: round(sum(ers) / len(ers), 3)
        for block, ers in sorted(hour_buckets.items())
        if ers
    }

    # メディアタイプ別
    type_buckets: dict[str, list[float]] = collections.defaultdict(list)
    for m in enriched:
        type_buckets[m.get("media_type", "IMAGE")].append(m["er"])
    by_media_type = {
        mt: {"avg_er": round(sum(ers) / len(ers), 3), "count": len(ers)}
        for mt, ers in type_buckets.items()
    }

    # キャプション文字数帯別（100字刻み）
    len_buckets: dict[str, list[float]] = collections.defaultdict(list)
    for m in enriched:
        cl = m["caption_length"]
        bucket = f"{(cl // 100) * 100}-{(cl // 100) * 100 + 99}字"
        len_buckets[bucket].append(m["er"])
    caption_length_buckets = {
        b: round(sum(ers) / len(ers), 3)
        for b, ers in sorted(len_buckets.items())
        if ers
    }

    # ハッシュタグ数帯別
    tag_buckets: dict[str, list[float]] = collections.defaultdict(list)
    for m in enriched:
        tc = m["hashtag_count"]
        bucket = f"{tc}個" if tc <= 10 else "11個以上"
        tag_buckets[bucket].append(m["er"])
    hashtag_count_buckets = {
        b: round(sum(ers) / len(ers), 3)
        for b, ers in sorted(tag_buckets.items())
        if ers
    }

    return {
        "top_posts": top_posts_out,
        "by_weekday": by_weekday,
        "by_hour": by_hour,
        "by_media_type": by_media_type,
        "caption_length_buckets": caption_length_buckets,
        "hashtag_count_buckets": hashtag_count_buckets,
    }


# ---------- Claude分析 ----------

def analyze_patterns(stats: dict, followers: int, client: anthropic.Anthropic) -> dict:
    """集計結果を Claude Haiku で解釈し改善提案を生成"""
    top_summary = "\n".join(
        f"  ER={p['er']}% [{p['media_type']}] {p['timestamp_jst']} "
        f"いいね={p['like_count']} コメ={p['comments_count']} "
        f"文字={p['caption_length']}字 #={p['hashtag_count']}個 / {p['caption_head']}"
        for p in stats["top_posts"]
    )

    prompt = f"""Instagram「ryo_finance_ai」の投稿分析結果（フォロワー数: {followers}人）

【ER上位10投稿】（ER = (いいね+コメント)/フォロワー数）
{top_summary}

【曜日別 平均ER】
{json.dumps(stats['by_weekday'], ensure_ascii=False)}

【時間帯別 平均ER】（JSTの3時間ブロック）
{json.dumps(stats['by_hour'], ensure_ascii=False)}

【メディアタイプ別】
{json.dumps(stats['by_media_type'], ensure_ascii=False)}

【キャプション文字数帯別 平均ER】
{json.dumps(stats['caption_length_buckets'], ensure_ascii=False)}

【ハッシュタグ数別 平均ER】
{json.dumps(stats['hashtag_count_buckets'], ensure_ascii=False)}

上記データを分析し以下をJSONで出力してください:
1. best_posting_hours: 最もERが高い投稿時間帯リスト（例: ["21:00","12:00"]）
2. best_weekdays: 最もERが高い曜日リスト（例: ["火","木"]）
3. best_media_types: 最もERが高いメディアタイプリスト（例: ["VIDEO","CAROUSEL_ALBUM"]）
4. optimal_hashtag_count: 最適なハッシュタグ数（整数）
5. optimal_caption_length: 最適なキャプション長の範囲（例: "200-350字"）
6. top_content_patterns: 高パフォーマンス投稿の共通パターン（3点リスト）
7. improvement_suggestions: 次の投稿への具体的な改善提案（3点リスト）
8. avg_engagement_rate: ER上位10投稿の平均ER（小数点2桁の数値）

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


# ---------- 保存 ----------

def save_result(stats: dict, patterns: dict, followers: int) -> Path:
    LOGS_DIR.mkdir(exist_ok=True)
    now = datetime.datetime.now(JST)
    data = {
        "generated_at": now.isoformat(),
        "followers_count": followers,
        "total_posts_analyzed": len(stats.get("top_posts", [])),
        "patterns": patterns,
        "stats": {
            "by_weekday": stats["by_weekday"],
            "by_hour": stats["by_hour"],
            "by_media_type": stats["by_media_type"],
            "caption_length_buckets": stats["caption_length_buckets"],
            "hashtag_count_buckets": stats["hashtag_count_buckets"],
        },
        "top_posts": stats["top_posts"],
    }
    OUTPUT_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[SelfAnalysis] 保存完了: {OUTPUT_FILE}")
    return OUTPUT_FILE


# ---------- エントリポイント ----------

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

    print("[Step 1] フォロワー数取得...")
    followers = fetch_followers_count(ig_id, ig_token)
    print(f"  → フォロワー数: {followers:,}人")

    print(f"\n[Step 2] 自分の投稿を最大{MAX_MEDIA}件取得...")
    media_list = fetch_own_media(ig_id, ig_token)
    if not media_list:
        print("投稿データが取得できませんでした。終了します。")
        sys.exit(0)

    type_counts: dict[str, int] = {}
    for m in media_list:
        t = m.get("media_type", "IMAGE")
        type_counts[t] = type_counts.get(t, 0) + 1
    print(f"  → {len(media_list)}件取得: {', '.join(f'{t}:{n}件' for t, n in type_counts.items())}")

    print("\n[Step 3] 集計中（ER・曜日/時間帯・メディアタイプ・キャプション相関）...")
    stats = compute_stats(media_list, followers)
    print(f"  → 集計完了 / ER上位: {stats['top_posts'][0]['er'] if stats['top_posts'] else '?'}%")

    print("\n[Step 4] Claudeでパターン分析中...")
    patterns = analyze_patterns(stats, followers, client)
    if patterns:
        print(f"  → 分析完了: ER平均={patterns.get('avg_engagement_rate', '?')}%")

    save_result(stats, patterns, followers)
    print("\n=== 完了 ===\n")


if __name__ == "__main__":
    main()
