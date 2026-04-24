"""
Creatomate エージェント
Creatomate REST API でショート動画（Instagram Reels 用）を生成する。
紺（#0d1b3e）× 金（#c9a227）デザインを維持する。
"""
import time
import requests

CREATOMATE_API = "https://api.creatomate.com/v1"

# ─── カラーパレット ───────────────────────────────────────────────────────────
NAVY       = "#0d1b3e"
NAVY_DARK  = "#060c20"
NAVY_PANEL = "rgba(10,22,40,0.85)"
GOLD       = "#c9a227"
GOLD_LIGHT = "#e8b830"
WHITE      = "#ffffff"
WHITE_DIM  = "rgba(255,255,255,0.8)"
FONT       = "Noto Sans JP"

STORY_LABELS = {
    "story1": "していた",
    "story2": "損をした",
    "story3": "だから話す",
}


# ─── Public API ──────────────────────────────────────────────────────────────

def render_reel(script: dict, api_key: str, timeout: int = 300) -> str:
    """
    Creatomate でリール動画をレンダリングし、完成した MP4 の URL を返す。
    script: short_video_agent.generate_short_video_script() の出力 dict
    """
    source = _build_source(script)
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    r = requests.post(
        f"{CREATOMATE_API}/renders",
        headers=headers,
        json={"source": source},
        timeout=30,
    )
    r.raise_for_status()
    render_id = r.json()[0]["id"]
    print(f"[CreatomateAgent] レンダリング開始: {render_id}")

    deadline = time.time() + timeout
    while time.time() < deadline:
        time.sleep(10)
        res = requests.get(
            f"{CREATOMATE_API}/renders/{render_id}",
            headers=headers,
            timeout=30,
        )
        res.raise_for_status()
        data = res.json()
        status = data.get("status", "")
        print(f"[CreatomateAgent] 状態: {status}")
        if status == "succeeded":
            url = data["url"]
            print(f"[CreatomateAgent] 完了: {url}")
            return url
        if status in ("failed", "canceled"):
            raise RuntimeError(
                f"Creatomateレンダリング失敗: {data.get('error_message', status)}"
            )

    raise TimeoutError(f"Creatomateレンダリングがタイムアウトしました（{timeout}秒）")


# ─── Composition builder ──────────────────────────────────────────────────────

def _build_source(script: dict) -> dict:
    scenes   = script.get("scenes", [])
    title    = script.get("title", "")
    hook_sub = script.get("hook_sub", "")
    account  = script.get("account", "@ryo_money_fp")
    total    = float(max((s["end"] for s in scenes), default=60))

    elements: list[dict] = [
        _background(total),
        _title_text(title, total),
        _account_text(account, total),
        _progress_track(total),
    ]

    for i, scene in enumerate(scenes):
        elements.extend(_scene_elements(scene, i, len(scenes), hook_sub))
        elements.append(_progress_fill(scene, i, len(scenes)))

    return {
        "output_format": "mp4",
        "width": 1080,
        "height": 1920,
        "frame_rate": 30,
        "duration": total,
        "elements": elements,
    }


def _fade(dur: float = 0.5) -> dict:
    return {"time": "start", "type": "fade-in", "duration": dur}


def _background(total: float) -> dict:
    return {
        "type": "shape",
        "shape": "rectangle",
        "x": "50%",
        "y": "50%",
        "width": "100%",
        "height": "100%",
        "fill_color": [NAVY, NAVY_DARK],
        "fill_rotation": 180,
        "duration": total,
    }


def _title_text(text: str, total: float) -> dict:
    return {
        "type": "text",
        "text": text or "",
        "duration": total,
        "x": "50%",
        "y": "5%",
        "width": "88%",
        "color": GOLD,
        "font_family": FONT,
        "font_size": "32 px",
        "font_weight": "700",
        "x_alignment": "50%",
        "y_alignment": "50%",
        "line_height": "1.3 em",
    }


def _account_text(text: str, total: float) -> dict:
    return {
        "type": "text",
        "text": text,
        "duration": total,
        "x": "50%",
        "y": "95%",
        "color": WHITE_DIM,
        "font_family": FONT,
        "font_size": "26 px",
        "font_weight": "700",
        "x_alignment": "50%",
    }


def _progress_track(total: float) -> dict:
    return {
        "type": "shape",
        "shape": "rectangle",
        "duration": total,
        "x": "50%",
        "y": "90%",
        "width": "88%",
        "height": "6 px",
        "fill_color": "rgba(255,255,255,0.15)",
        "border_radius": "3 px",
    }


def _progress_fill(scene: dict, index: int, total_scenes: int) -> dict:
    width_pct = (index + 1) / total_scenes * 88
    x_pct = (100 - 88) / 2 + width_pct / 2
    return {
        "type": "shape",
        "shape": "rectangle",
        "time": float(scene["start"]),
        "duration": float(scene["end"] - scene["start"]),
        "x": f"{x_pct:.2f}%",
        "y": "90%",
        "width": f"{width_pct:.2f}%",
        "height": "6 px",
        "fill_color": [GOLD, GOLD_LIGHT],
        "fill_rotation": 90,
        "border_radius": "3 px",
    }


def _scene_elements(
    scene: dict, index: int, total: int, hook_sub: str
) -> list[dict]:
    start    = float(scene["start"])
    dur      = float(scene["end"] - scene["start"])
    telop    = scene.get("telop") or scene.get("voice", "")
    sid      = scene.get("id", "")
    is_hook  = index == 0
    is_story = sid.startswith("story")

    base = {"time": start, "duration": dur}
    fade = [_fade(0.5)]

    if is_hook:
        elems: list[dict] = [
            # 金バッジ「元銀行員が言います」
            {**base,
             "type": "text",
             "text": "元銀行員が言います",
             "x": "50%", "y": "22%",
             "color": NAVY_DARK,
             "background_color": GOLD,
             "background_border_radius": "100 px",
             "background_x_padding": "32 px",
             "background_y_padding": "10 px",
             "font_family": FONT,
             "font_size": "28 px",
             "font_weight": "900",
             "x_alignment": "50%",
             "animations": fade},
        ]
        if hook_sub:
            elems.append(
                {**base,
                 "type": "text",
                 "text": hook_sub,
                 "x": "50%", "y": "30%",
                 "color": GOLD,
                 "font_family": FONT,
                 "font_size": "24 px",
                 "font_weight": "700",
                 "x_alignment": "50%",
                 "animations": fade}
            )
        # フックメインテキスト（大・スケールイン）
        elems.append(
            {**base,
             "type": "text",
             "text": telop,
             "x": "50%", "y": "50%",
             "width": "88%",
             "color": WHITE,
             "font_family": FONT,
             "font_size": "76 px",
             "font_weight": "900",
             "x_alignment": "50%",
             "y_alignment": "50%",
             "line_height": "1.2 em",
             "animations": [
                 {"time": "start", "type": "scale-in", "duration": 0.8},
                 _fade(0.5),
             ]}
        )
        return elems

    # ─── ストーリー / CTA シーン ──────────────────────────────────────────────
    elems = [
        # 半透明紺パネル
        {**base,
         "type": "shape", "shape": "rectangle",
         "x": "50%", "y": "62%",
         "width": "90%", "height": "36%",
         "fill_color": NAVY_PANEL,
         "border_radius": "20 px",
         "animations": fade},
        # 金左ボーダー
        {**base,
         "type": "shape", "shape": "rectangle",
         "x": "6.2%", "y": "62%",
         "width": "8 px", "height": "36%",
         "fill_color": GOLD,
         "border_radius": "4 px",
         "animations": fade},
    ]
    if is_story and sid in STORY_LABELS:
        elems.append(
            {**base,
             "type": "text",
             "text": STORY_LABELS[sid],
             "x": "50%", "y": "46%",
             "color": GOLD,
             "font_family": FONT,
             "font_size": "26 px",
             "font_weight": "700",
             "x_alignment": "50%",
             "animations": fade}
        )
    elems.append(
        {**base,
         "type": "text",
         "text": telop,
         "x": "50%", "y": "62%",
         "width": "82%",
         "color": WHITE,
         "font_family": FONT,
         "font_size": "54 px",
         "font_weight": "900",
         "x_alignment": "50%",
         "y_alignment": "50%",
         "line_height": "1.35 em",
         "animations": fade}
    )
    return elems
