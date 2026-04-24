"""
競合リサーチ + コメント文案自動生成スクリプト
毎朝 07:05 JST に Mac cron から実行される。

フロー:
  1. DuckDuckGo で Instagram/Threads の金融・副業系投稿を検索（5〜10件/日）
  2. Claude Haiku で各投稿に「銀行員目線のコメント文案」を生成
  3. logs/comment_targets_YYYYMMDD.md に出力（手動確認してから手動送信）

Usage:
  python3 scripts/research_comments.py           # 本番実行
  python3 scripts/research_comments.py --dry-run # Claude API なし（検索 + スキップ）
"""
import argparse
import datetime
import os
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

ENV_PATH = os.path.expanduser("~/Documents/Obsidian Vault/.env")
LOGS_DIR = ROOT / "logs"
JST = datetime.timezone(datetime.timedelta(hours=9))

# 1ニッチあたりの最大収集件数
MAX_PER_NICHE = 2

# ニッチ × 検索クエリ定義
# 各クエリで threads.net / instagram.com を含む URL のみ採用する
NICHES: list[tuple[str, list[str]]] = [
    ("金融リテラシー", [
        "金融リテラシー threads.net",
        "金融リテラシー instagram 投稿",
    ]),
    ("元銀行員", [
        "元銀行員 threads.net 副業",
        "元銀行員 instagram 2026",
    ]),
    ("AI副業", [
        "AI副業 threads.net 月収",
        "AI副業 instagram 副業収入",
    ]),
    ("NISA・投資初心者", [
        "NISA 初心者 threads.net",
        "NISA 積立投資 instagram 初心者向け",
    ]),
    ("副業収入", [
        "副業収入 threads.net 体験談",
        "副業 月収 instagram 2026",
    ]),
]

PLATFORM_DOMAINS = ("threads.net", "instagram.com")

COMMENT_SYSTEM_PROMPT = """\
あなたは元メガバンク行員20年・FP資格保持・AI副業で月7万を達成したインフルエンサーです。
他の SNS アカウントの投稿に、銀行員の実体験から価値を加えるコメントを書きます。

【コメントの原則】
- 銀行員・金融専門家としての視点から「追加価値」を提供する
- 共感 or 補足情報 or 銀行員時代の実体験を素直に書く
- 宣伝・自己紹介は絶対にしない（「銀行員時代〜」と軽く触れる程度でOK）
- 上から目線にならず「一緒に学んでいる仲間」の口調
- 50〜100字（短くまとめる）

【禁止事項】
- 「詳しくはプロフィールへ」などの誘導文
- 「フォローお願いします」
- 根拠不明の数字・統計（自分の体験値のみ使う）
- 投資・副業の断定的な推薦（「〜すべき」「必ず儲かる」など）
"""


@dataclass
class PostTarget:
    niche: str
    platform: str
    author: str
    url: str
    snippet: str
    comment: str = ""


def _detect_platform(url: str) -> str:
    if "instagram.com" in url:
        return "Instagram"
    if "threads.net" in url:
        return "Threads"
    return ""


def _extract_author(url: str) -> str:
    """URL からアカウント名を推定する"""
    parts = url.rstrip("/").split("/")
    # threads.net/@username/... パターン
    for part in parts:
        if part.startswith("@"):
            return part
    # instagram.com/username/p/... パターン
    if "instagram.com" in url:
        try:
            ig_idx = next(i for i, p in enumerate(parts) if "instagram.com" in p)
            candidate = parts[ig_idx + 1] if ig_idx + 1 < len(parts) else ""
            skip = {"p", "reel", "tv", "stories", "explore", "www", ""}
            if candidate and candidate not in skip:
                return f"@{candidate}"
        except StopIteration:
            pass
    return "@不明"


def search_posts() -> list[PostTarget]:
    """DuckDuckGo で各ニッチの Instagram/Threads 投稿を検索する"""
    try:
        from duckduckgo_search import DDGS
    except ImportError:
        print("[ResearchComments] エラー: duckduckgo-search が未インストールです")
        print("  pip install duckduckgo-search")
        sys.exit(1)

    targets: list[PostTarget] = []
    seen_urls: set[str] = set()

    with DDGS() as ddgs:
        for niche, queries in NICHES:
            niche_count = 0
            for query in queries:
                if niche_count >= MAX_PER_NICHE:
                    break
                print(f"[Search] {query}")
                try:
                    results = list(ddgs.text(query, timelimit="w", max_results=8))
                except Exception as e:
                    print(f"  検索エラー: {e}")
                    time.sleep(3)
                    continue

                for r in results:
                    if niche_count >= MAX_PER_NICHE:
                        break
                    url = r.get("href", "")
                    platform = _detect_platform(url)
                    if not platform or url in seen_urls:
                        continue

                    seen_urls.add(url)
                    author = _extract_author(url)
                    snippet = (r.get("body") or r.get("title") or "")[:250]
                    targets.append(PostTarget(
                        niche=niche,
                        platform=platform,
                        author=author,
                        url=url,
                        snippet=snippet,
                    ))
                    niche_count += 1
                    print(f"  [{platform}] {author} — {snippet[:50]}…")

                time.sleep(1.5)

    print(f"\n[ResearchComments] 収集完了: {len(targets)} 件\n")
    return targets


def _generate_one_comment(post: PostTarget, client) -> str:
    prompt = f"""以下の投稿に対して、銀行員目線のコメントを1つ書いてください。

プラットフォーム: {post.platform}
ニッチ: {post.niche}
投稿内容: {post.snippet}

コメント本文のみ出力してください（前置き・説明不要）。"""

    resp = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=200,
        system=COMMENT_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": prompt}],
    )
    return resp.content[0].text.strip()


def generate_comments(targets: list[PostTarget], client) -> None:
    for i, post in enumerate(targets, 1):
        print(f"[Comment] {i}/{len(targets)} {post.author} ({post.platform})")
        try:
            post.comment = _generate_one_comment(post, client)
            print(f"  → {post.comment[:60]}…")
        except Exception as e:
            print(f"  生成エラー: {e}")
            post.comment = "（生成失敗）"
        if i < len(targets):
            time.sleep(1)


def write_markdown(targets: list[PostTarget], today: datetime.date) -> Path:
    LOGS_DIR.mkdir(exist_ok=True)
    out = LOGS_DIR / f"comment_targets_{today.strftime('%Y%m%d')}.md"
    now_jst = datetime.datetime.now(JST)

    lines: list[str] = [
        f"# コメント候補リスト {today.strftime('%Y-%m-%d')}",
        "",
        f"生成: {now_jst.strftime('%Y-%m-%d %H:%M JST')} / {len(targets)} 件",
        "",
        "> **手順:** 各コメント文案を確認 → 必要なら編集 → チェックボックスをつけてから手動でプラットフォームに投稿",
        "",
        "---",
        "",
    ]

    # ニッチ順に出力
    niche_order = [name for name, _ in NICHES]
    by_niche: dict[str, list[PostTarget]] = {}
    for t in targets:
        by_niche.setdefault(t.niche, []).append(t)

    for niche in niche_order:
        posts = by_niche.get(niche, [])
        if not posts:
            continue
        lines += [f"## {niche}", ""]
        for j, p in enumerate(posts, 1):
            lines += [
                f"### {j}. {p.author} &nbsp; `{p.platform}`",
                "",
                f"🔗 {p.url}",
                "",
                "**投稿内容（抜粋）:**",
                f"> {p.snippet or '（内容取得できず）'}",
                "",
                "**コメント文案:**",
                "```",
                p.comment or "（未生成）",
                "```",
                "",
                "- [ ] 送信済み",
                "",
            ]
        lines += ["---", ""]

    out.write_text("\n".join(lines), encoding="utf-8")
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description="競合リサーチ + コメント文案生成")
    parser.add_argument("--dry-run", action="store_true", help="Claude API なし（検索のみ）")
    args = parser.parse_args()

    load_dotenv(ENV_PATH)

    today = datetime.datetime.now(JST).date()
    print(f"\n=== コメントリサーチ {today} ===\n")

    targets = search_posts()
    if not targets:
        print("投稿が見つかりませんでした。終了します。")
        sys.exit(0)

    if args.dry_run:
        print("[DRY RUN] Claude API をスキップします")
        for t in targets:
            t.comment = "（DRY RUN）"
    else:
        api_key = os.getenv("ANTHROPIC_API_KEY", "")
        if not api_key:
            print("エラー: ANTHROPIC_API_KEY 未設定", file=sys.stderr)
            sys.exit(1)
        import anthropic
        generate_comments(targets, anthropic.Anthropic(api_key=api_key))

    out = write_markdown(targets, today)
    print(f"\n=== 出力完了: {out} ===\n")


if __name__ == "__main__":
    main()
