"""
バズ投稿分析スクリプト（analyze.yml から呼ばれる）
2日に1回 GitHub Actions で実行され、buzz_analysis.json を更新する。

Usage:
  python3 scripts/analyze_buzz.py
"""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

import anthropic
from dotenv import load_dotenv

from agents.buzz_analyzer import run_weekly_analysis

ENV_PATH = os.path.expanduser("~/Documents/Obsidian Vault/.env")


def main() -> None:
    load_dotenv(ENV_PATH)

    api_key = os.getenv("ANTHROPIC_API_KEY", "")
    if not api_key:
        print("エラー: ANTHROPIC_API_KEY 未設定", file=sys.stderr)
        sys.exit(1)

    client = anthropic.Anthropic(api_key=api_key)
    access_token = os.getenv("THREADS_ACCESS_TOKEN", "")
    user_id = os.getenv("THREADS_USER_ID", "")

    print("\n=== バズ投稿分析（2日毎）===\n")
    result = run_weekly_analysis(client, access_token=access_token, user_id=user_id)
    print(f"\n=== 分析完了: {result.get('generated_at', '')} ===\n")


if __name__ == "__main__":
    main()
