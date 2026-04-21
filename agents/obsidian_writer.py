"""
Obsidian Vault 書き込みモジュール
投稿ログ・週次レポート・改善提案をマークダウン形式で保存する。

保存先:
  ~/Documents/Obsidian Vault/SNS運用/投稿ログ/YYYY-MM-DD.md   （日次・追記）
  ~/Documents/Obsidian Vault/SNS運用/分析レポート/YYYY-MM-DD-weekly.md
  ~/Documents/Obsidian Vault/SNS運用/分析レポート/YYYY-MM-DD-improvement.md
"""
from datetime import datetime
from pathlib import Path
from typing import Optional

VAULT_ROOT  = Path.home() / "Documents" / "Obsidian Vault"
POST_LOG_DIR = VAULT_ROOT / "SNS運用" / "投稿ログ"
REPORT_DIR   = VAULT_ROOT / "SNS運用" / "分析レポート"

_DAY_NAMES = ["月", "火", "水", "木", "金", "土", "日"]

_PLATFORM_LABELS = {
    "instagram": "Instagram",
    "threads":   "Threads",
    "twitter":   "X(Twitter)",
}


def _ensure_dirs() -> None:
    POST_LOG_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_DIR.mkdir(parents=True, exist_ok=True)


# ──────────────────────────────────────────────
# 投稿ログ
# ──────────────────────────────────────────────

def write_post_log(entry: dict) -> Path:
    """
    1回の投稿記録を当日の投稿ログファイルに追記する。
    ファイルが存在しない場合はヘッダーから新規作成する。
    """
    _ensure_dirs()

    dt_str  = entry.get("datetime", datetime.now().isoformat())
    dt      = datetime.fromisoformat(dt_str)
    date_str = dt.strftime("%Y-%m-%d")
    weekday  = entry.get("weekday", dt.weekday())
    day_name = _DAY_NAMES[weekday]

    path = POST_LOG_DIR / f"{date_str}.md"

    # ── ファイルが存在しない場合はヘッダーを生成 ──
    if not path.exists():
        header = _build_log_header(date_str, day_name)
        path.write_text(header, encoding="utf-8")

    # ── 投稿エントリを追記 ──
    block = _build_log_entry(entry, dt)
    with open(path, "a", encoding="utf-8") as f:
        f.write(block)

    print(f"[Obsidian] 投稿ログ保存: {path}")
    return path


def _build_log_header(date_str: str, day_name: str) -> str:
    return f"""---
date: {date_str}
weekday: {day_name}曜日
tags: [SNS運用, 投稿ログ]
---

# {date_str}（{day_name}曜日）投稿ログ

"""


def _build_log_entry(entry: dict, dt: datetime) -> str:
    topic     = entry.get("topic_summary", "")
    image_url = entry.get("image_url", "")
    cap_len   = entry.get("caption_length", 0)
    platforms = entry.get("platforms", {})

    # プラットフォーム結果テーブル
    rows = []
    for key, label in _PLATFORM_LABELS.items():
        post_id = platforms.get(key)
        status  = f"✅ `{post_id}`" if post_id else "－"
        rows.append(f"| {label} | {status} |")
    table = "\n".join(rows)

    # 画像プレビュー（URLがあれば）
    image_block = f"\n![]({image_url})\n" if image_url else ""

    return f"""## {dt.strftime("%H:%M")} 投稿

**トピック**: {topic}
**キャプション文字数**: {cap_len}字

### 投稿結果

| プラットフォーム | 結果 |
|---|---|
{table}
{image_block}
---

"""


# ──────────────────────────────────────────────
# 週次レポート
# ──────────────────────────────────────────────

def write_weekly_report(
    entries: list[dict],
    total_all: int,
    period_label: Optional[str] = None,
) -> Path:
    """
    直近N件の投稿データから週次レポートを生成してObsidianに保存する。
    """
    _ensure_dirs()

    today    = datetime.now()
    date_str = today.strftime("%Y-%m-%d")
    path     = REPORT_DIR / f"{date_str}-weekly.md"

    content = _build_weekly_report(entries, total_all, date_str, period_label)
    path.write_text(content, encoding="utf-8")

    print(f"[Obsidian] 週次レポート保存: {path}")
    return path


def _build_weekly_report(
    entries: list[dict],
    total_all: int,
    date_str: str,
    period_label: Optional[str],
) -> str:
    n = len(entries)
    period = period_label or f"直近{n}件"

    # プラットフォーム別成功率
    platform_counts: dict[str, int] = {k: 0 for k in _PLATFORM_LABELS}
    for e in entries:
        for k in _PLATFORM_LABELS:
            if e.get("platforms", {}).get(k):
                platform_counts[k] += 1

    platform_rows = "\n".join(
        f"| {label} | {platform_counts[key]}/{n} | "
        f"{'✅' if platform_counts[key] == n else '⚠️' if platform_counts[key] > 0 else '－'} |"
        for key, label in _PLATFORM_LABELS.items()
    )

    # テンプレート集計
    template_counts: dict[str, int] = {}
    for e in entries:
        tmpl = e.get("template_used", "（不明）")
        template_counts[tmpl] = template_counts.get(tmpl, 0) + 1
    template_rows = "\n".join(
        f"| {tmpl} | {cnt}回 |"
        for tmpl, cnt in sorted(template_counts.items(), key=lambda x: -x[1])
    )

    # 投稿一覧
    post_rows = []
    for e in entries:
        dt    = e.get("datetime", "")[:16]
        topic = e.get("topic_summary", "")[:25]
        flags = "".join(
            "✅" if e.get("platforms", {}).get(k) else "－"
            for k in _PLATFORM_LABELS
        )
        post_rows.append(f"| {dt} | {topic} | {flags} |")
    post_table = "\n".join(post_rows)

    return f"""---
date: {date_str}
type: weekly-report
period: {period}
tags: [SNS運用, 分析レポート, 週次]
---

# 週次パフォーマンスレポート（{period}）

生成日時: {datetime.now().strftime("%Y-%m-%d %H:%M")}

## 投稿実績サマリー

| 項目 | 値 |
|---|---|
| 集計期間 | {period} |
| 集計件数 | {n}件 |
| 累計投稿数 | {total_all}件 |

## プラットフォーム別成功率

| プラットフォーム | 成功/集計 | 状態 |
|---|---|---|
{platform_rows}

## テンプレート使用状況

| テンプレート | 使用回数 |
|---|---|
{template_rows}

## 投稿一覧（IG / TH / X）

| 日時 | トピック | IG TH X |
|---|---|---|
{post_table}

## メモ・気づき

（週次の振り返りをここに記録）

"""


# ──────────────────────────────────────────────
# 改善提案レポート
# ──────────────────────────────────────────────

def write_improvement_report(
    report_body: str,
    period_label: Optional[str] = None,
) -> Path:
    """
    content-improver が生成した改善提案をObsidianに保存する。
    report_body はマークダウン形式の文字列。
    """
    _ensure_dirs()

    today    = datetime.now()
    date_str = today.strftime("%Y-%m-%d")
    path     = REPORT_DIR / f"{date_str}-improvement.md"

    header = f"""---
date: {date_str}
type: improvement-report
period: {period_label or "直近7日間"}
tags: [SNS運用, 分析レポート, 改善提案]
---

# コンテンツ改善提案（{date_str}）

生成日時: {today.strftime("%Y-%m-%d %H:%M")}

"""
    path.write_text(header + report_body, encoding="utf-8")

    print(f"[Obsidian] 改善提案保存: {path}")
    return path
