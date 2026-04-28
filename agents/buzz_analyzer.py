"""
バズ投稿分析エージェント
Threadsの金融・副業ジャンルのバズ投稿を週1回収集・分析してJSONで保存する。
自社の高パフォーマンス投稿も分析して投稿戦略に反映する。
"""
import json
import os
import re
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Optional

import requests
import anthropic

LOGS_DIR = Path(__file__).parent.parent / "logs"
CONFIG_DIR = Path(__file__).parent.parent / "config"
BUZZ_ANALYSIS_FILE = LOGS_DIR / "buzz_analysis.json"
COMPETITOR_CONFIG = CONFIG_DIR / "competitors.json"
POST_LOG_FILE = LOGS_DIR / "post_log.jsonl"

THREADS_API = "https://graph.threads.net/v1.0"
ANALYSIS_STALE_DAYS = 7


def is_analysis_fresh() -> bool:
    """buzz_analysis.jsonが7日以内に生成されていればTrue"""
    if not BUZZ_ANALYSIS_FILE.exists():
        return False
    try:
        with open(BUZZ_ANALYSIS_FILE, encoding="utf-8") as f:
            data = json.load(f)
        generated = date.fromisoformat(data.get("generated_at", "2000-01-01"))
        return (date.today() - generated).days < ANALYSIS_STALE_DAYS
    except Exception:
        return False


def _load_competitor_config() -> dict:
    """競合アカウント設定を読み込む"""
    if not COMPETITOR_CONFIG.exists():
        return {"accounts": [], "genres": [], "buzz_threshold": 100}
    with open(COMPETITOR_CONFIG, encoding="utf-8") as f:
        return json.load(f)


def _try_fetch_threads_profile(username: str) -> list[dict]:
    """Threadsの公開プロフィールから投稿テキストを取得する（ベストエフォート）"""
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "ja,en-US;q=0.7,en;q=0.3",
    }
    url = f"https://www.threads.net/@{username}"
    try:
        r = requests.get(url, headers=headers, timeout=20)
        if r.status_code != 200:
            return []
        # __NEXT_DATA__からJSONデータを抽出する試み
        match = re.search(
            r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>',
            r.text,
            re.DOTALL,
        )
        if not match:
            return []
        data = json.loads(match.group(1))
        threads_list = (
            data.get("props", {})
            .get("pageProps", {})
            .get("profile", {})
            .get("threads", [])
        )
        posts = []
        for thread in threads_list[:30]:
            for item in thread.get("thread_items", []):
                post = item.get("post", {})
                text = (post.get("caption") or {}).get("text", "")
                like_count = post.get("like_count", 0)
                if text and like_count >= 100:
                    posts.append({
                        "username": username,
                        "text": text[:500],
                        "like_count": like_count,
                    })
        return posts
    except Exception as e:
        print(f"[BuzzAnalyzer] スクレイピング失敗 @{username}: {e}")
        return []


def _fetch_own_top_posts_via_api(access_token: str, user_id: str) -> list[dict]:
    """Threads APIで自社の人気投稿を取得する"""
    if not access_token or not user_id:
        return []
    try:
        params = {
            "fields": "id,text,timestamp,like_count",
            "access_token": access_token,
            "limit": 50,
        }
        r = requests.get(
            f"{THREADS_API}/{user_id}/threads",
            params=params,
            timeout=20,
        )
        r.raise_for_status()
        threads = r.json().get("data", [])
        return [
            {
                "username": "ryo_finance_ai",
                "text": t.get("text", ""),
                "like_count": t.get("like_count", 0),
                "timestamp": t.get("timestamp", ""),
            }
            for t in threads
            if t.get("text")
        ]
    except Exception as e:
        print(f"[BuzzAnalyzer] Threads API取得失敗: {e}")
        return []


def collect_buzz_posts(access_token: str = "", user_id: str = "") -> list[dict]:
    """Threads APIと公開スクレイピングでバズ投稿を収集する"""
    config = _load_competitor_config()
    buzz_threshold = config.get("buzz_threshold", 100)
    posts: list[dict] = []

    # 自社投稿をAPIで取得
    if access_token and user_id:
        own_posts = _fetch_own_top_posts_via_api(access_token, user_id)
        high_perf = [p for p in own_posts if p.get("like_count", 0) >= buzz_threshold]
        print(f"[BuzzAnalyzer] 自社投稿取得: {len(own_posts)}件 (うちいいね{buzz_threshold}以上: {len(high_perf)}件)")
        posts.extend(high_perf)

    # 競合アカウントをスクレイピング
    for account in config.get("accounts", []):
        time.sleep(2)
        fetched = _try_fetch_threads_profile(account)
        print(f"[BuzzAnalyzer] @{account}: {len(fetched)}件取得")
        posts.extend(fetched)

    return posts


def _load_own_post_log() -> list[dict]:
    """post_log.jsonlから過去投稿を読み込む"""
    if not POST_LOG_FILE.exists():
        return []
    records = []
    with open(POST_LOG_FILE, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
                if "topic_summary" in rec:
                    records.append(rec)
            except json.JSONDecodeError:
                continue
    return records


def analyze_own_post_patterns(client: anthropic.Anthropic) -> dict:
    """自社の過去投稿から高パフォーマンスパターンを抽出する"""
    records = _load_own_post_log()
    if not records:
        print("[BuzzAnalyzer] 自社投稿ログなし")
        return {}

    # 最新50件を対象に
    sample = records[-50:]
    summaries = [
        f"テーマ: {r.get('topic_summary', '')} / テンプレート: {r.get('template_used', '-')} / キャプション{r.get('caption_length', 0)}字"
        for r in sample
    ]
    sample_text = "\n".join(summaries[:30])

    prompt = f"""以下は金融×AI副業SNSアカウント「ryo_finance_ai」の過去投稿記録です。

{sample_text}

以下の観点で分析してJSON形式で出力してください:
1. top_templates: 最も使われているテンプレートと特徴（3個）
2. effective_topics: パフォーマンスが高そうなトピック傾向
3. caption_length_insight: キャプション長の傾向と推奨
4. improvement_suggestions: 次の投稿に活かせる改善提案（3点）

JSON形式のみ出力（コードブロックなし）:"""

    try:
        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=1200,
            messages=[{"role": "user", "content": prompt}],
        )
        text = response.content[0].text.strip().replace("```json", "").replace("```", "").strip()
        return json.loads(text)
    except Exception as e:
        print(f"[BuzzAnalyzer] 自社投稿分析失敗: {e}")
        return {}


def analyze_buzz_patterns(posts: list[dict], client: anthropic.Anthropic) -> dict:
    """Claudeでバズ投稿のパターンを分析する"""
    if not posts:
        sample_text = "（収集データなし。金融×副業ジャンルの一般的なバズパターンを分析してください）"
    else:
        sample_text = "\n---\n".join(
            f"@{p['username']} (いいね{p.get('like_count', 0)}件)\n{p['text']}"
            for p in posts[:20]
        )

    config = _load_competitor_config()
    genres = "・".join(config.get("genres", ["副業", "投資"]))

    prompt = f"""以下はThreadsの{genres}ジャンルのバズ投稿です（いいね100件以上）。

{sample_text}

以下の6項目をJSON形式で出力してください。各リストは3個以内に絞ること。

{{"top_hooks":["フック例1","フック例2","フック例3"],"content_structures":["構成1","構成2","構成3"],"cta_patterns":["CTA1","CTA2","CTA3"],"writing_style":["文体特徴1","文体特徴2","文体特徴3"],"avg_post_length":"100〜150字","differentiation_tips":["差別化1","差別化2","差別化3"]}}

上記のJSON形式のみ出力（説明・コードブロック不要）:"""

    try:
        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=1500,
            messages=[{"role": "user", "content": prompt}],
        )
        text = response.content[0].text.strip().replace("```json", "").replace("```", "").strip()
        return json.loads(text)
    except Exception as e:
        print(f"[BuzzAnalyzer] パターン分析失敗: {e}")
        return {}


def analyze_competitors(client: anthropic.Anthropic) -> dict:
    """競合アカウントの差別化ポイントを分析する"""
    config = _load_competitor_config()
    accounts = config.get("accounts", [])
    if not accounts:
        return {}

    all_posts: list[dict] = []
    for account in accounts:
        time.sleep(2)
        fetched = _try_fetch_threads_profile(account)
        all_posts.extend(fetched)

    if not all_posts:
        account_list = "\n".join(f"- @{a}" for a in accounts)
        prompt = f"""以下はThreads金融×副業ジャンルの主要競合アカウントです:

{account_list}

投稿データは取得できませんでしたが、このジャンルの一般的な競合パターンを踏まえて、
「ryo_finance_ai（元メガバンク20年・FP資格・AI副業月7万達成）」が差別化できるポイントをJSON形式で出力してください:

{{
  "competitor_patterns": "競合の一般的な投稿パターン",
  "ryo_strengths": ["強み1", "強み2", "強み3"],
  "differentiation_actions": ["具体的な差別化アクション1", "具体的な差別化アクション2", "具体的な差別化アクション3"]
}}

JSON形式のみ出力（コードブロックなし）:"""
    else:
        posts_text = "\n---\n".join(
            f"@{p['username']}\n{p['text']}"
            for p in all_posts[:15]
        )
        prompt = f"""以下はThreads金融×副業ジャンルの競合アカウントの投稿です:

{posts_text}

「ryo_finance_ai（元メガバンク20年・FP資格・AI副業月7万達成）」の差別化戦略をJSON形式で出力してください:

{{
  "competitor_patterns": "競合の投稿パターンの特徴",
  "ryo_strengths": ["差別化できる強み1", "差別化できる強み2", "差別化できる強み3"],
  "differentiation_actions": ["具体的な差別化アクション1", "具体的な差別化アクション2", "具体的な差別化アクション3"]
}}

JSON形式のみ出力（コードブロックなし）:"""

    try:
        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=800,
            messages=[{"role": "user", "content": prompt}],
        )
        text = response.content[0].text.strip().replace("```json", "").replace("```", "").strip()
        return json.loads(text)
    except Exception as e:
        print(f"[BuzzAnalyzer] 競合分析失敗: {e}")
        return {}


def save_buzz_analysis(
    patterns: dict,
    competitor_insights: dict,
    own_post_insights: dict,
    posts: list[dict],
) -> Path:
    """分析結果をJSONで保存する"""
    output = {
        "generated_at": date.today().isoformat(),
        "total_posts_collected": len(posts),
        "buzz_posts_sample": posts[:20],
        "patterns": patterns,
        "competitor_insights": competitor_insights,
        "own_post_insights": own_post_insights,
    }
    with open(BUZZ_ANALYSIS_FILE, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    return BUZZ_ANALYSIS_FILE


def run_weekly_analysis(
    client: anthropic.Anthropic,
    access_token: str = "",
    user_id: str = "",
    force: bool = False,
) -> dict:
    """週次バズ投稿分析を実行する。force=Trueで強制再実行。"""
    if not force and is_analysis_fresh():
        print("[BuzzAnalyzer] 分析結果が最新（7日以内）のためスキップ")
        with open(BUZZ_ANALYSIS_FILE, encoding="utf-8") as f:
            return json.load(f)

    print("[BuzzAnalyzer] 週次バズ投稿分析開始...")

    posts = collect_buzz_posts(access_token, user_id)
    print(f"[BuzzAnalyzer] 合計{len(posts)}件収集")

    print("[BuzzAnalyzer] バズパターン分析中...")
    patterns = analyze_buzz_patterns(posts, client)

    print("[BuzzAnalyzer] 競合アカウント分析中...")
    competitor_insights = analyze_competitors(client)

    print("[BuzzAnalyzer] 自社投稿パターン分析中...")
    own_post_insights = analyze_own_post_patterns(client)

    path = save_buzz_analysis(patterns, competitor_insights, own_post_insights, posts)
    print(f"[BuzzAnalyzer] 分析完了・保存: {path}")

    return {
        "generated_at": date.today().isoformat(),
        "total_posts_collected": len(posts),
        "patterns": patterns,
        "competitor_insights": competitor_insights,
        "own_post_insights": own_post_insights,
    }
