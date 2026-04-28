"""
カルーセル画像生成エージェント
content_agent.py が生成したスライドコンテンツを受け取り、
capture_carousel.js (Puppeteer) 経由で PNG 画像を生成する。

返り値: PNG ファイルパスのリスト（7枚）
"""
import json
import subprocess
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).parent.parent
CAPTURE_SCRIPT = ROOT / "scripts" / "capture_carousel.js"
OUTPUT_DIR = ROOT / "logs" / "carousel_images"
HTML_TEMPLATE = ROOT / "templates" / "carousel_redesign_v4.html"


def _check_prerequisites() -> None:
    """実行前提条件を確認する"""
    if not CAPTURE_SCRIPT.exists():
        raise FileNotFoundError(f"capture_carousel.js が見つかりません: {CAPTURE_SCRIPT}")
    if not HTML_TEMPLATE.exists():
        raise FileNotFoundError(
            f"HTML テンプレートが見つかりません: {HTML_TEMPLATE}\n"
            "以下を実行して配置してください:\n"
            "  cp ~/Downloads/carousel_redesign_v4.html templates/"
        )


def capture_slides(carousel_content: dict, date_str: str = "") -> list[str]:
    """
    carousel_content: generate_carousel_content() の返り値 dict
                      必須キー: carousel_slides (list of dicts with num/headline/subtext/body)
    date_str: ログディレクトリの日付サフィックス（省略時は今日）
    Returns: PNG ファイルパスのリスト
    """
    _check_prerequisites()

    slides = carousel_content.get("carousel_slides", [])
    if not slides:
        raise ValueError("carousel_slides が空です")

    # content_agent の carousel_slides 形式を capture_carousel.js 用に変換
    # content_agent: {"slide_num", "headline", "body", "image_prompt"}
    # capture_carousel.js: {"num", "role", "headline", "subtext", "body"}
    ROLE_MAP = {1: "hook", 2: "problem", 3: "step", 4: "step", 5: "step", 6: "proof", 7: "cta"}
    normalized_slides = []
    for s in slides:
        num = s.get("slide_num", s.get("num", 0))
        normalized_slides.append({
            "num":      num,
            "role":     s.get("role", ROLE_MAP.get(num, "step")),
            "headline": s.get("headline", ""),
            "subtext":  s.get("subtext", ""),
            "body":     s.get("body", ""),
        })

    content_json = json.dumps({"slides": normalized_slides}, ensure_ascii=False)

    ds = date_str or date.today().strftime("%Y%m%d")
    out_dir = OUTPUT_DIR / ds
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"[CarouselAgent] Puppeteer でスライド撮影中（{len(normalized_slides)}枚）...")

    result = subprocess.run(
        ["node", str(CAPTURE_SCRIPT),
         "--content", content_json,
         "--out", str(out_dir)],
        capture_output=True,
        text=True,
        cwd=str(ROOT),
        timeout=120,
    )

    if result.returncode != 0:
        stderr = result.stderr.strip()
        raise RuntimeError(f"capture_carousel.js が失敗しました:\n{stderr}")

    # stderr は進捗ログ、stdout は JSON パスリスト
    for line in result.stderr.strip().splitlines():
        print(f"  {line}")

    stdout = result.stdout.strip()
    if not stdout:
        raise RuntimeError("capture_carousel.js からの出力が空です")

    paths = json.loads(stdout)
    print(f"[CarouselAgent] 完了: {len(paths)}枚の PNG を生成")
    for p in paths:
        print(f"  {Path(p).name}")
    return paths


def capture_slides_dry_run(carousel_content: dict) -> list[str]:
    """
    --dry-run 用: HTML テンプレートの存在確認のみ行い、
    スクリーンショットは撮らずにダミーパスを返す。
    """
    slides = carousel_content.get("carousel_slides", [])
    print(f"[CarouselAgent] DRY RUN: {len(slides)}枚のスライドを撮影予定")
    print(f"  HTML: {HTML_TEMPLATE}")
    print(f"  出力先: {OUTPUT_DIR / date.today().strftime('%Y%m%d')}")

    if not HTML_TEMPLATE.exists():
        print(f"  [WARNING] テンプレートが未配置: {HTML_TEMPLATE}")

    return [str(OUTPUT_DIR / date.today().strftime("%Y%m%d") / f"slide_{i+1}.png")
            for i in range(len(slides))]
