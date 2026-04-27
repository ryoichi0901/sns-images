"""
Video Agent
Pillow + FFmpeg でショート動画（Instagram Reels 用）を生成する。
GitHub Actions を含む完全無料環境で動作する。
紺（#0d1b3e）× 金（#c9a227）デザインを維持する。
"""
import os
import subprocess
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

WIDTH, HEIGHT, FPS = 1080, 1920, 30

NAVY       = (13, 27, 62)
NAVY_DARK  = (6, 12, 32)
NAVY_PANEL = (10, 22, 40)
GOLD       = (201, 162, 39)
WHITE      = (255, 255, 255)

STORY_LABELS = {
    "story1": "していた",
    "story2": "損をした",
    "story3": "だから話す",
}

# フォント候補（Linux / macOS 両対応）
_FONT_CANDIDATES = [
    # GitHub Actions ubuntu-latest（fonts-noto-cjk インストール後）
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJKjp-Bold.otf",
    "/usr/share/fonts/noto-cjk/NotoSansCJKjp-Bold.otf",
    "/usr/share/fonts/truetype/noto/NotoSansCJK-Bold.ttc",
    # macOS
    "/System/Library/Fonts/ヒラギノ角ゴシック W6.ttc",
    "/Library/Fonts/NotoSansCJKjp-Bold.otf",
]
_font_cache: dict[int, ImageFont.FreeTypeFont] = {}


def _font(size: int) -> ImageFont.FreeTypeFont:
    if size in _font_cache:
        return _font_cache[size]
    for path in _FONT_CANDIDATES:
        if os.path.exists(path):
            f = ImageFont.truetype(path, size)
            _font_cache[size] = f
            return f
    # フォールバック（日本語非対応）
    print("[VideoAgent] 警告: 日本語フォントが見つかりません。apt install fonts-noto-cjk を実行してください。")
    f = ImageFont.load_default()
    _font_cache[size] = f
    return f


# ─── 描画ヘルパー ─────────────────────────────────────────────────────────────

def _gradient_bg(draw: ImageDraw.ImageDraw) -> None:
    for y in range(HEIGHT):
        t = y / HEIGHT
        r = int(NAVY[0] + (NAVY_DARK[0] - NAVY[0]) * t)
        g = int(NAVY[1] + (NAVY_DARK[1] - NAVY[1]) * t)
        b = int(NAVY[2] + (NAVY_DARK[2] - NAVY[2]) * t)
        draw.line([(0, y), (WIDTH, y)], fill=(r, g, b))


def _wrap(draw: ImageDraw.ImageDraw, text: str, font, max_w: int) -> list[str]:
    """文字単位で折り返す（日本語対応・改行文字対応）"""
    all_lines = []
    for paragraph in text.split('\n'):
        lines, cur = [], ""
        for ch in paragraph:
            test = cur + ch
            if draw.textlength(test, font=font) > max_w and cur:
                lines.append(cur)
                cur = ch
            else:
                cur = test
        if cur:
            lines.append(cur)
        all_lines.extend(lines)
    return all_lines


def _draw_centered(
    draw: ImageDraw.ImageDraw,
    text: str,
    cy: int,
    font,
    color: tuple,
    max_w: int = WIDTH - 100,
) -> None:
    lines = _wrap(draw, text, font, max_w)
    lh = font.size * 1.35
    y = cy - (len(lines) * lh) / 2
    for line in lines:
        w = draw.textlength(line, font=font)
        draw.text(((WIDTH - w) / 2, y), line, font=font, fill=color)
        y += lh


def _draw_progress(
    draw: ImageDraw.ImageDraw, idx: int, total: int
) -> None:
    bx, by, bh = 60, int(HEIGHT * 0.89), 6
    bw = WIDTH - 120
    draw.rounded_rectangle([bx, by, bx + bw, by + bh], radius=3,
                            fill=(255, 255, 255, 38))
    filled = int(bw * (idx + 1) / total)
    if filled > 0:
        draw.rounded_rectangle([bx, by, bx + filled, by + bh], radius=3,
                                fill=GOLD)


# ─── シーン別レンダリング ─────────────────────────────────────────────────────

def _render_scene(
    scene: dict, script: dict, idx: int, total: int
) -> Image.Image:
    img = Image.new("RGB", (WIDTH, HEIGHT))
    draw = ImageDraw.Draw(img, "RGBA")
    _gradient_bg(draw)

    title   = script.get("title", "")
    telop   = scene.get("telop") or scene.get("voice", "")
    sid     = scene.get("id", "")
    account = script.get("account", "@ryo_money_fp")
    is_hook = idx == 0

    # タイトル（全シーン共通・上部・金色）
    _draw_centered(draw, title, 115, _font(34), GOLD)

    if is_hook:
        hook_sub = script.get("hook_sub", "")

        # 金バッジ「元銀行員が言います」
        f_badge = _font(30)
        badge = "元銀行員が言います"
        bw = int(draw.textlength(badge, font=f_badge)) + 64
        bh = f_badge.size + 20
        bx = (WIDTH - bw) // 2
        by = int(HEIGHT * 0.20)
        draw.rounded_rectangle([bx, by, bx + bw, by + bh], radius=bh // 2,
                                fill=GOLD)
        draw.text((bx + 32, by + 10), badge, font=f_badge, fill=NAVY_DARK)

        # hook_sub（実績サブテキスト）
        if hook_sub:
            _draw_centered(draw, hook_sub, int(HEIGHT * 0.305), _font(28), GOLD)

        # メインテキスト（大・中央・白）
        _draw_centered(draw, telop, int(HEIGHT * 0.50), _font(84), WHITE,
                       max_w=WIDTH - 100)

    else:
        # ストーリーラベル枠
        if sid in STORY_LABELS:
            f_lbl = _font(28)
            lbl = STORY_LABELS[sid]
            lw = int(draw.textlength(lbl, font=f_lbl)) + 40
            lh = f_lbl.size + 16
            lx = 40
            ly = int(HEIGHT * 0.43)
            draw.rounded_rectangle([lx, ly, lx + lw, ly + lh], radius=6,
                                    outline=GOLD, width=2)
            draw.text((lx + 20, ly + 8), lbl, font=f_lbl, fill=GOLD)

        # 半透明紺パネル
        py1, py2 = int(HEIGHT * 0.50), int(HEIGHT * 0.80)
        draw.rounded_rectangle([40, py1, WIDTH - 40, py2], radius=20,
                                fill=(*NAVY_PANEL, 217))
        # 金左ボーダー
        draw.rounded_rectangle([40, py1, 56, py2], radius=4, fill=GOLD)

        # テキスト
        _draw_centered(draw, telop, (py1 + py2) // 2, _font(58), WHITE,
                       max_w=WIDTH - 160)
        # プログレスバー
        _draw_progress(draw, idx, total)

    # アカウント名（下部）
    _draw_centered(draw, account, int(HEIGHT * 0.945), _font(28),
                   (255, 255, 255, 200))
    return img


# ─── FFmpeg 結合 ──────────────────────────────────────────────────────────────

def _ffmpeg_concat(imgs: list[Path], durs: list[float], out: Path) -> None:
    n = len(imgs)
    args: list[str] = []
    for p, d in zip(imgs, durs):
        args += ["-loop", "1", "-t", str(d), "-i", str(p)]

    scale = (
        f"scale={WIDTH}:{HEIGHT}:force_original_aspect_ratio=disable,"
        "setsar=1"
    )
    filters = [f"[{i}:v]{scale}[s{i}]" for i in range(n)]
    concat_in = "".join(f"[s{i}]" for i in range(n))
    filters.append(f"{concat_in}concat=n={n}:v=1:a=0[out]")

    cmd = (
        ["ffmpeg", "-y"] + args
        + ["-filter_complex", ";".join(filters),
           "-map", "[out]",
           "-c:v", "libx264", "-pix_fmt", "yuv420p", "-r", str(FPS),
           str(out)]
    )
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"FFmpeg 失敗:\n{result.stderr[-800:]}")


# ─── Public API ──────────────────────────────────────────────────────────────

def render_reel_local(script: dict, out_path: Path) -> Path:
    """
    Pillow + FFmpeg でリール動画を生成し out_path に保存する。
    GitHub Actions / Mac 両対応・完全無料。

    script: short_video_agent.generate_short_video_script() の出力 dict
    """
    scenes = script.get("scenes", [])
    if not scenes:
        raise ValueError("script.scenes が空です")

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory() as tmp:
        imgs, durs = [], []
        for i, scene in enumerate(scenes):
            img = _render_scene(scene, script, i, len(scenes))
            p = Path(tmp) / f"s{i:02d}.png"
            img.save(str(p))
            imgs.append(p)
            durs.append(float(scene["end"] - scene["start"]))
            print(f"[VideoAgent] シーン{i+1}/{len(scenes)} 生成: {scene.get('id')}")

        _ffmpeg_concat(imgs, durs, out_path)

    total_sec = sum(durs)
    print(f"[VideoAgent] 完了: {out_path} ({total_sec:.0f}秒)")
    return out_path
