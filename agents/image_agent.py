"""
画像生成エージェント
Pollinations AI（無料）で画像を生成し、ローカルに保存する。
"""
import random
import time
import urllib.parse
from pathlib import Path
import requests

IMAGES_DIR = Path(__file__).parent.parent / "images"
IMAGES_DIR.mkdir(exist_ok=True)

POLLINATIONS_BASE = "https://image.pollinations.ai/prompt"

# テーマ共通の品質強化プレフィックス
QUALITY_PREFIX = (
    "professional photography, high quality, instagram post, "
    "no text overlay, no watermark, "
)

# スライド位置ごとに適用するビジュアルスタイル（7枚分 + ループ用余裕）
SLIDE_STYLES = [
    "dramatic overhead composition, bold high contrast, deep shadows",
    "close-up emotional detail, soft bokeh, warm cinematic tones",
    "flat lay minimalist arrangement, cool blue-grey palette, clean lines",
    "dynamic diagonal composition, vivid saturated colors, energetic feel",
    "split composition with negative space, neutral modern palette, sharp focus",
    "wide establishing shot, golden hour backlight, aspirational mood",
    "centered symmetrical composition, gold accents, triumphant upward motion",
]


def _fetch_and_save(fetch_url: str, path: Path, label: str) -> Path:
    """Pollinations から画像を取得してファイルに保存する（リトライ付き）"""
    for attempt in range(3):
        try:
            print(f"[ImageAgent] {label} 生成中... (試行{attempt + 1}/3)")
            r = requests.get(fetch_url, timeout=120)
            if r.status_code == 200 and len(r.content) > 10_000:
                path.write_bytes(r.content)
                size_kb = len(r.content) // 1024
                print(f"[ImageAgent] 保存完了: {path.name} ({size_kb}KB)")
                return path
            if r.status_code == 429:
                wait = 45 * (attempt + 1)
                print(f"[ImageAgent] レート制限 (429)。{wait}秒待機...")
                time.sleep(wait)
                continue
            print(f"[ImageAgent] 不正なレスポンス: {r.status_code}, size={len(r.content)}")
        except Exception as e:
            print(f"[ImageAgent] エラー (試行{attempt + 1}/3): {e}")
        if attempt < 2:
            time.sleep(15)
    raise RuntimeError(f"{label} の画像生成に3回失敗しました")


def generate_image(prompt: str, date_str: str) -> Path:
    """
    prompt: 英語の画像プロンプト
    date_str: ファイル名に使う日付文字列 (YYYYMMDD)
    returns: 保存した画像のPath
    """
    path = IMAGES_DIR / f"post_{date_str}.jpg"
    full_prompt = QUALITY_PREFIX + prompt
    encoded = urllib.parse.quote(full_prompt)
    url = f"{POLLINATIONS_BASE}/{encoded}?width=1080&height=1080&nologo=true&seed={_date_seed(date_str)}"
    return _fetch_and_save(url, path, "単枚")


def generate_carousel_images(slides: list[dict], date_str: str) -> list[Path]:
    """
    カルーセル用に各スライドの画像を順番に生成して保存する。
    slides: carousel_slides リスト（各要素に image_prompt が必要）
    date_str: YYYYMMDD
    returns: 保存したPathのリスト（スライド順）
    """
    paths: list[Path] = []
    # 毎回異なる画像を生成するためランダムベースシードを使用
    base_seed = random.randint(1, 99999)

    for idx, slide in enumerate(slides):
        num = slide["slide_num"]
        path = IMAGES_DIR / f"post_{date_str}_slide{num}.jpg"
        # スライド位置固有のビジュアルスタイルを付与して視覚的多様性を確保
        style = SLIDE_STYLES[idx % len(SLIDE_STYLES)]
        full_prompt = QUALITY_PREFIX + slide["image_prompt"] + ", " + style
        encoded = urllib.parse.quote(full_prompt)
        seed = (base_seed + num * 1000) % 100000
        url = f"{POLLINATIONS_BASE}/{encoded}?width=1080&height=1080&nologo=true&seed={seed}"
        paths.append(_fetch_and_save(url, path, f"スライド{num}"))
        # Pollinations レート制限を避けるためスライド間に十分なウェイト（最終スライドはスキップ）
        if idx < len(slides) - 1:
            time.sleep(20)

    return paths


def _date_seed(date_str: str) -> int:
    """単枚投稿用：日付から一貫したシードを生成（同日は同じ画像テイスト）"""
    return sum(int(c) * (i + 1) for i, c in enumerate(date_str) if c.isdigit()) % 10000
