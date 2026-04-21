"""
アフィリエイトリンク解決モジュール
env varからURLを読み込み、曜日またはテーマに応じたリンク情報を返す。

必要な環境変数（~/Documents/Obsidian Vault/.env）:
  AFFILIATE_LINK_FX            # FX口座開設リンク
  AFFILIATE_LINK_NISA          # NISA・証券口座リンク
  AFFILIATE_LINK_SIDE_BUSINESS # 副業・AI系リンク
  LINKTREE_URL                 # リンクツリー（全リンクまとめ・fallback）
"""
import json
import os
from pathlib import Path

AFFILIATE_PATH = Path(__file__).parent.parent / "config" / "affiliate.json"

# フォールバック順：指定env_key → LINKTREE_URL → プレースホルダー
_FALLBACK_PLACEHOLDER = "https://lit.link/"


def _load_config() -> dict:
    with open(AFFILIATE_PATH, encoding="utf-8") as f:
        return json.load(f)


def _resolve_url(env_key: str) -> str:
    """env_key に対応する URL を env var から読み込む。未設定なら LINKTREE_URL にフォールバック。"""
    url = os.getenv(env_key, "").strip()
    if url:
        return url
    fallback = os.getenv("LINKTREE_URL", "").strip()
    if fallback:
        return fallback
    return _FALLBACK_PLACEHOLDER


def resolve_by_weekday(weekday: int) -> dict:
    """
    曜日（0=月〜6=日）に対応するアフィリエイト情報を返す。
    returns: { label, cta, url, env_key, theme }
    """
    config = _load_config()
    entry = config["weekday_links"][str(weekday)]
    return {
        "label":   entry["label"],
        "cta":     entry["cta"],
        "url":     _resolve_url(entry["env_key"]),
        "env_key": entry["env_key"],
        "theme":   entry["theme"],
    }


def resolve_by_theme(theme: str) -> dict:
    """
    テーマキー（nisa / ai_side_job / automation / investment / fx / literacy / ai_report / life_plan）
    に対応するアフィリエイト情報を返す。
    曜日を問わずテーマで直接リンクを指定したいときに使う。
    """
    config = _load_config()
    env_key = config["theme_to_env_key"].get(theme, "LINKTREE_URL")
    # label / cta はテーマに一致する weekday_links から取得
    matched_entry = next(
        (v for v in config["weekday_links"].values() if v["theme"] == theme),
        None,
    )
    label = matched_entry["label"] if matched_entry else "詳細はプロフィールリンクから"
    cta   = matched_entry["cta"]   if matched_entry else "👇 プロフィールリンクから"
    return {
        "label":   label,
        "cta":     cta,
        "url":     _resolve_url(env_key),
        "env_key": env_key,
        "theme":   theme,
    }


def get_linktree_url() -> str:
    """LINKTREE_URL を直接返す（Instagram bio リンク用）"""
    return os.getenv("LINKTREE_URL", _FALLBACK_PLACEHOLDER).strip()


def validate_env() -> dict[str, bool]:
    """必要な env var が設定されているかチェックし、結果を返す"""
    required = [
        "AFFILIATE_LINK_FX",
        "AFFILIATE_LINK_NISA",
        "AFFILIATE_LINK_SIDE_BUSINESS",
        "LINKTREE_URL",
    ]
    return {key: bool(os.getenv(key, "").strip()) for key in required}
