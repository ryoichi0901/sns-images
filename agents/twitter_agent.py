"""
Xエージェント (Twitter API v2)
tweepy を使いツイートを投稿する。
アフィリエイトリンクをツイート末尾に付与。
280文字制限に自動対応。
"""
from typing import Optional
import tweepy

from agents.affiliate_resolver import resolve_by_weekday, resolve_by_theme

TWEET_MAX = 280


def build_tweet_text(base_tweet: str, weekday: int, theme: Optional[str] = None) -> str:
    """
    ツイート本文にアフィリエイトURLを付与し、280字以内に収める。
    URL は Twitter の t.co 短縮で23字固定として計算。
    theme を指定するとテーマ優先のリンクを使用する。
    """
    aff = resolve_by_theme(theme) if theme else resolve_by_weekday(weekday)
    url = aff["url"]
    url_cost = 23  # Twitter t.co は常に23字換算

    # URL + 改行2文字分を確保
    max_text = TWEET_MAX - url_cost - 2
    trimmed = base_tweet[:max_text].rstrip()
    return f"{trimmed}\n\n{url}"


def publish_to_twitter(
    tweet_text: str,
    weekday: int,
    api_key: str,
    api_secret: str,
    access_token: str,
    access_token_secret: str,
    theme: Optional[str] = None,
) -> str:
    """
    X (Twitter) にツイートを投稿し、ツイートIDを返す。
    theme を指定するとテーマ優先のアフィリエイトURLを付与する。
    """
    full_tweet = build_tweet_text(tweet_text, weekday, theme=theme)
    print(f"[TwitterAgent] ツイート文字数: {len(full_tweet)}")

    client = tweepy.Client(
        consumer_key=api_key,
        consumer_secret=api_secret,
        access_token=access_token,
        access_token_secret=access_token_secret,
    )
    response = client.create_tweet(text=full_tweet)
    tweet_id = str(response.data["id"])
    print(f"[TwitterAgent] 投稿完了: {tweet_id}")
    return tweet_id
