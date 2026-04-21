"""
分析エージェント
投稿ログの読み書きと、パフォーマンスサマリーを担当。
マルチプラットフォーム（Instagram / Threads / X）対応。
投稿記録・週次レポートを Obsidian Vault にも自動保存する。
"""
import json
from datetime import datetime
from pathlib import Path
from typing import Optional

from agents.obsidian_writer import write_post_log, write_weekly_report

LOG_PATH = Path(__file__).parent.parent / "logs" / "post_log.jsonl"
LOG_PATH.parent.mkdir(exist_ok=True)

PLATFORM_LABELS = {
    "instagram": "Instagram",
    "threads":   "Threads  ",
    "twitter":   "X(Twitter)",
}


def log_post(
    topic_summary: str,
    weekday: int,
    instagram_id: Optional[str] = None,
    threads_id: Optional[str] = None,
    twitter_id: Optional[str] = None,
    image_url: Optional[str] = None,
    caption_length: int = 0,
    template_used: Optional[str] = None,
) -> None:
    entry = {
        "datetime": datetime.now().isoformat(),
        "weekday": weekday,
        "topic_summary": topic_summary,
        "image_url": image_url,
        "caption_length": caption_length,
        "template_used": template_used,
        "platforms": {
            "instagram": instagram_id,
            "threads": threads_id,
            "twitter": twitter_id,
        },
    }

    # JSONL ログに追記
    with open(LOG_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    posted = [k for k, v in entry["platforms"].items() if v]
    print(f"[Analytics] ログ記録: {entry['datetime'][:16]} | {topic_summary} | {', '.join(posted) or 'なし'}")

    # Obsidian 投稿ログに保存
    try:
        write_post_log(entry)
    except Exception as e:
        print(f"[Analytics] Obsidian書き込みスキップ: {e}")


def print_summary(recent: int = 7, save_to_obsidian: bool = True) -> None:
    """
    直近N件の投稿サマリーをターミナルに表示し、Obsidian に週次レポートを保存する。
    save_to_obsidian=False にすると表示のみ（Obsidian保存をスキップ）。
    """
    if not LOG_PATH.exists():
        print("[Analytics] ログなし")
        return

    all_entries = []
    with open(LOG_PATH, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    all_entries.append(json.loads(line))
                except json.JSONDecodeError:
                    pass

    # datetime フィールドを持つ正規エントリのみ対象
    valid_entries = [e for e in all_entries if "datetime" in e]
    targets = valid_entries[-recent:]

    # ターミナル表示
    print(f"\n{'='*60}")
    print(f"  投稿サマリー（直近{recent}件）")
    print(f"{'='*60}")
    for entry in targets:
        dt = entry.get("datetime", "")[:16]
        topic = entry.get("topic_summary", "")[:18]
        platforms = entry.get("platforms", {})
        flags = []
        for key, label in PLATFORM_LABELS.items():
            val = platforms.get(key)
            flags.append(f"{'✓' if val else '–'}{label}")
        print(f"  {dt} | {topic:<18} | {' '.join(flags)}")
    print(f"{'='*60}")
    print(f"  累計投稿数: {len(valid_entries)}")
    print(f"{'='*60}\n")

    # Obsidian に週次レポートを保存
    if save_to_obsidian and targets:
        try:
            write_weekly_report(
                entries=targets,
                total_all=len(valid_entries),
                period_label=f"直近{len(targets)}件",
            )
        except Exception as e:
            print(f"[Analytics] Obsidian週次レポートスキップ: {e}")


def load_recent_entries(n: int = 30) -> list[dict]:
    """直近N件の有効な投稿エントリを返す（外部エージェントからの参照用）"""
    if not LOG_PATH.exists():
        return []
    entries = []
    with open(LOG_PATH, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    e = json.loads(line)
                    if "datetime" in e:
                        entries.append(e)
                except json.JSONDecodeError:
                    pass
    return entries[-n:]
