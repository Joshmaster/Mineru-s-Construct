"""Gera card visual de Boss Mundial — estilo Diablo 4 dark fantasy."""

import asyncio
import datetime
import io
import json
import math
import random
import tempfile
import time
import urllib.request
from pathlib import Path
from zoneinfo import ZoneInfo

from PIL import Image, ImageDraw, ImageFont, ImageFilter

# ── Config ────────────────────────────────────────────────────────────────────
ANCHOR_ISO      = "2026-05-16T22:00:00-03:00"
INTERVAL_MIN    = 210
REMINDER_MIN    = 5
BOSS_DURATION_MIN = 15
TZ              = ZoneInfo("America/Sao_Paulo")

anchorMs   = int(datetime.datetime.fromisoformat(ANCHOR_ISO).timestamp() * 1000)
intervalMs = INTERVAL_MIN * 60 * 1000

FONT_PATH = Path("/home/joshlink/.local/share/fonts/Orbitron-Variable.ttf")
W, H = 1080, 1080

BOSS_PROMPTS = [
    "Diablo 4 hell gate opening in a dark medieval landscape, fire and brimstone, demonic atmosphere, cinematic",
    "Dark fantasy demon boss emerging from portal, Diablo style, hellish red sky, dramatic lighting",
    "Ancient corrupted cathedral in darkness, demonic runes glowing red, Diablo 4 art style, ominous",
    "Hellish battlefield with burning souls, dark fantasy, Diablo 4, crimson sky, epic cinematic",
    "Demonic portal ritual dark stone altar, fire sparks, blood moon, Diablo style, dramatic",
    "Massive demon lord silhouette against burning horizon, dark fantasy, lava rivers, Diablo 4",
    "Apocalyptic dark sky with falling meteors and demonic wings, hellscape, Diablo style, cinematic",
    "Cursed dungeon entrance with glowing skulls and hellfire, dark gothic, Diablo 4 atmosphere",
    "Ancient demon summoning circle cracked stone floor, red energy, darkness, dramatic lighting",
    "Dark fantasy war ruins with demonic creatures, ash falling, blood red moon, epic cinematic",
]

# ── Lógica ────────────────────────────────────────────────────────────────────
def get_next_boss(now_ms: int) -> int:
    elapsed = now_ms - anchorMs
    intervals = math.ceil(elapsed / intervalMs)
    return anchorMs + intervals * intervalMs

def upcoming_bosses(now_ms: int, qty: int = 4) -> list[int]:
    result, nb = [], get_next_boss(now_ms)
    for _ in range(qty):
        result.append(nb)
        nb += intervalMs
    return result

def fmt_time(ts_ms: int) -> str:
    return datetime.datetime.fromtimestamp(ts_ms / 1000, tz=TZ).strftime("%d/%m %H:%M")

def fmt_date(ts_ms: int) -> str:
    return datetime.datetime.fromtimestamp(ts_ms / 1000, tz=TZ).strftime("%d/%m")

def fmt_hour(ts_ms: int) -> str:
    return datetime.datetime.fromtimestamp(ts_ms / 1000, tz=TZ).strftime("%H:%M")

def fmt_countdown(ms: int) -> str:
    if ms <= 0: return "AGORA"
    s = ms // 1000
    h, rem = divmod(s, 3600)
    m, ss  = divmod(rem, 60)
    if h: return f"{h:02d}:{m:02d}:{ss:02d}"
    return f"{m:02d}:{ss:02d}"

# ── Fontes ────────────────────────────────────────────────────────────────────
def _font(size: int) -> ImageFont.FreeTypeFont:
    try:
        return ImageFont.truetype(str(FONT_PATH), size)
    except Exception:
        return ImageFont.load_default()

# ── Background via CF Worker ──────────────────────────────────────────────────
def _fetch_bg() -> Image.Image | None:
    try:
        from hyrule_env import CF_WORKER_IMG_URL as url
    except ImportError:
        return None
    prompt = random.choice(BOSS_PROMPTS)
    payload = json.dumps({"prompt": prompt, "model": "flux-schnell"}).encode()
    req = urllib.request.Request(url, data=payload,
        headers={"Content-Type": "application/json", "User-Agent": "HyruleBot/1.0"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=90) as r:
            if r.status != 200: return None
            return Image.open(io.BytesIO(r.read())).convert("RGBA").resize((W, H))
    except Exception:
        return None

# ── Fundo fallback: gradiente infernal ────────────────────────────────────────
def _fallback_bg() -> Image.Image:
    bg = Image.new("RGBA", (W, H), (0, 0, 0, 255))
    draw = ImageDraw.Draw(bg)
    for y in range(H):
        t = y / H
        r = int(20 + 60 * (1 - t))
        g = int(0 + 5 * (1 - t))
        b = 0
        draw.line([(0, y), (W, y)], fill=(r, g, b, 255))
    # faíscas
    for _ in range(120):
        x, y = random.randint(0, W-1), random.randint(0, H-1)
        br = random.randint(100, 220)
        r2 = random.randint(1, 3)
        draw.ellipse((x, y, x+r2, y+r2), fill=(br, br//3, 0, 255))
    return bg

# ── Texto com sombra ──────────────────────────────────────────────────────────
def _text(draw: ImageDraw.ImageDraw, pos: tuple, text: str, font, color, shadow=(0,0,0)):
    x, y = pos
    for ox, oy in [(-2,-2),(2,-2),(-2,2),(2,2),(0,3),(0,-3)]:
        draw.text((x+ox, y+oy), text, font=font, fill=(*shadow, 220))
    draw.text((x, y), text, font=font, fill=color)

def _text_center(draw: ImageDraw.ImageDraw, y: int, text: str, font, color, shadow=(0,0,0)):
    tw = int(draw.textlength(text, font=font))
    _text(draw, ((W - tw) // 2, y), text, font, color, shadow)

# ── Borda ornamentada ─────────────────────────────────────────────────────────
def _draw_border(draw: ImageDraw.ImageDraw):
    pad = 24
    gold = (180, 140, 0, 200)
    red  = (160, 30, 0, 180)
    draw.rectangle([pad, pad, W-pad, H-pad], outline=gold, width=2)
    draw.rectangle([pad+6, pad+6, W-pad-6, H-pad-6], outline=red, width=1)
    # cantos
    cs = 40
    for cx, cy, dx, dy in [(pad, pad, 1, 1), (W-pad, pad, -1, 1),
                             (pad, H-pad, 1, -1), (W-pad, H-pad, -1, -1)]:
        draw.line([(cx, cy), (cx + dx*cs, cy)], fill=gold, width=3)
        draw.line([(cx, cy), (cx, cy + dy*cs)], fill=gold, width=3)
        draw.ellipse([cx-4, cy-4, cx+4, cy+4], fill=gold)

# ── Separador ────────────────────────────────────────────────────────────────
def _draw_sep(draw: ImageDraw.ImageDraw, y: int):
    gold = (160, 120, 0, 160)
    draw.line([(80, y), (W-80, y)], fill=gold, width=1)
    cx = W // 2
    draw.polygon([(cx, y-6), (cx+6, y), (cx, y+6), (cx-6, y)], fill=(160, 60, 0, 200))

# ── Glow overlay ──────────────────────────────────────────────────────────────
def _glow_overlay(base: Image.Image, warning: bool) -> Image.Image:
    glow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(glow)
    color = (200, 30, 0, 60) if warning else (120, 20, 0, 35)
    for r in range(300, 0, -30):
        alpha = max(0, 60 - r // 5) if warning else max(0, 35 - r // 8)
        d.ellipse([(W//2 - r, H//2 - r), (W//2 + r, H//2 + r)],
                  fill=(*color[:3], alpha))
    blurred = glow.filter(ImageFilter.GaussianBlur(40))
    return Image.alpha_composite(base, blurred)

# ── Escurecimento do background ───────────────────────────────────────────────
def _darken(img: Image.Image, alpha: int = 160) -> Image.Image:
    overlay = Image.new("RGBA", (W, H), (0, 0, 0, alpha))
    return Image.alpha_composite(img, overlay)

# ── Card principal ────────────────────────────────────────────────────────────
def render_boss_card(warning: bool = False) -> str:
    now_ms  = int(time.time() * 1000)
    bosses  = upcoming_bosses(now_ms, 4)
    next_ms = bosses[0]
    ms_left = next_ms - now_ms
    is_active = ms_left <= 0 and ms_left > -(BOSS_DURATION_MIN * 60 * 1000)

    # Background
    bg = _fetch_bg() or _fallback_bg()
    bg = _darken(bg, 155)
    bg = _glow_overlay(bg, warning or is_active)
    canvas = bg.copy()
    draw   = ImageDraw.Draw(canvas)

    # Fontes
    f_title    = _font(54)
    f_subtitle = _font(22)
    f_big      = _font(130)
    f_date     = _font(48)
    f_label    = _font(20)
    f_small    = _font(20)

    GOLD  = (200, 160, 20, 255)
    RED   = (220, 40, 20, 255)
    DRED  = (210, 90, 30, 255)
    WHITE = (230, 220, 200, 255)
    GRAY  = (150, 120, 90, 255)

    # Borda
    _draw_border(draw)

    # Título
    _text_center(draw, 60,  ">> BOSS MUNDIAL <<", f_title, GOLD, (40, 0, 0))
    _text_center(draw, 128, "SANTUARIO AGUARDA...",  f_subtitle, DRED)

    _draw_sep(draw, 175)

    # Data em cima, hora grande abaixo, countdown menor
    boss_date_str = fmt_date(next_ms)  # ex: "17/05"
    boss_hour_str = fmt_hour(next_ms)  # ex: "01:30"
    if is_active:
        _text_center(draw, 192, "[ BOSS ATIVO AGORA ]", f_subtitle, RED)
        _text_center(draw, 225, boss_date_str, f_date, RED, (60, 0, 0))
        _text_center(draw, 278, boss_hour_str, f_big, RED, (60, 0, 0))
        remaining = BOSS_DURATION_MIN * 60_000 + ms_left
        _text_center(draw, 430, f"Encerra em  {fmt_countdown(remaining)}", f_label, GRAY)
    elif warning:
        _text_center(draw, 192, "!! PREPARE-SE - BOSS EM BREVE !!", f_subtitle, RED)
        _text_center(draw, 225, boss_date_str, f_date, RED, (60, 0, 0))
        _text_center(draw, 278, boss_hour_str, f_big, RED, (60, 0, 0))
        _text_center(draw, 430, f"Em  {fmt_countdown(ms_left)}", f_label, GOLD)
    else:
        _text_center(draw, 192, "Proximo boss", f_label, GRAY)
        _text_center(draw, 225, boss_date_str, f_date, GOLD, (40, 0, 0))
        _text_center(draw, 278, boss_hour_str, f_big, GOLD, (40, 0, 0))
        _text_center(draw, 430, f"Em  {fmt_countdown(ms_left)}", f_label, WHITE)

    # Rodapé
    _text_center(draw, H - 65, f"Intervalo: {INTERVAL_MIN}min  |  Aviso: {REMINDER_MIN}min antes", f_small, (190, 150, 80, 255))

    # Salva
    out = Path(tempfile.gettempdir()) / f"boss_card_{int(time.time())}.jpg"
    canvas.convert("RGB").save(str(out), quality=92)
    return str(out)


# ── CLI de teste ──────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import sys
    warning = "--warning" in sys.argv
    print("Gerando card...", flush=True)
    path = render_boss_card(warning=warning)
    print(f"Salvo: {path}")
