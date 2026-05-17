"""Visual cards and captions for medication reminders."""

from __future__ import annotations

import io
import logging
import random
import re
import urllib.parse
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import httpx
from PIL import Image, ImageDraw, ImageFilter, ImageFont

log = logging.getLogger("reminder_art")

LOCAL_TZ = ZoneInfo("America/Sao_Paulo")
ROOT = Path(__file__).resolve().parents[3]
OUT_DIR = ROOT / ".linkbot" / "reminder_cards"

FONT_ORBITRON = Path("/home/joshlink/.local/share/fonts/Orbitron-Variable.ttf")
FONT_BOLD     = Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf")
FONT_REGULAR  = Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf")

SW_GOLD  = (255, 232,  26)
SW_CYAN  = (  0, 210, 232)
SW_RED   = (220,  50,  50)
SW_WHITE = (255, 255, 255)
SW_GRAY  = (190, 195, 210)
SW_DARK  = (  0,   4,  18)

# ─────────────────────────────────────────────────────────────────────────────
# Banco de medicamentos
# (keyword_lower → (nome_display, dose_padrão, cor_rgb))
# ─────────────────────────────────────────────────────────────────────────────
_MED_DB: dict[str, tuple[str, str, tuple]] = {
    # Digestivo
    "omeprazol":     ("Omeprazol 20mg",       "1 comp",  (  0, 210, 190)),
    # Nitratos
    "mononitrato":   ("Mononitrato de Isossorbida 20mg",     "1 comp",  (255, 210,   0)),
    "isossorbida":   ("Mononitrato de Isossorbida 20mg",     "1 comp",  (255, 210,   0)),
    # Betabloqueador
    "carvedilol":    ("Carvedilol 3,125mg",   "1 comp",  ( 80, 160, 255)),
    # Diurético
    "furosemida":    ("Furosemida 40mg",      "1 comp",  (100, 200, 255)),
    # Antianginoso
    "trimetazidina": ("Trimetazidina 35mg",   "1 comp",  (160, 100, 255)),
    # Vasodilatador
    "hidralazina":   ("Hidralazina 50mg",     "1 comp",  (100, 225, 140)),
    # Spray broncodilatador fixo
    "symbicort":     ("Symbicort",            "1 jato",  (255, 140,   0)),
    "formoterol":    ("Symbicort",            "1 jato",  (255, 140,   0)),
    "budesonida":    ("Symbicort",            "1 jato",  (255, 140,   0)),
    # Antiagregante plaquetário
    "aas":           ("AAS 100mg",            "1 comp",  (255,  90,  90)),
    # Bloqueador de canal de cálcio
    "anlodipino":    ("Anlodipino 5mg",       "2 comp",  (200,  80, 255)),
    "amlodipino":    ("Anlodipino 5mg",       "2 comp",  (200,  80, 255)),
    # Estatina
    "sinvastatina":  ("Sinvastatina 20mg",    "1 comp",  (255, 175,  40)),
    # Antidiabético
    "gliclazida":    ("Gliclazida 30mg",      "1 comp",  (  0, 200, 120)),
    # Spray SOS
    "aerodini":      ("Aerodini SOS",         "1 jato",  (220,  50,  50)),
    "salbutamol":    ("Aerodini SOS",         "1 jato",  (220,  50,  50)),
    "aerolin":       ("Aerolin SOS",          "1 jato",  (220,  50,  50)),
}

# Separadores aceitos no texto de lembrete
# Vírgula só separa quando NÃO está entre dígitos (evita quebrar "3,125mg")
_SEP_RE = re.compile(r"\n|(?<=\.)\s+|\s*\+\s*|\s*,\s*(?!\d)")


def _medication_lines(text: str) -> list[tuple[str, str, tuple]]:
    """Parse medication list from reminder text.

    Accepts free-form text or newline/dot/plus/comma-separated entries.
    Returns [(display_name, dose_label, color_rgb), ...]
    """
    normalized = (text or "").strip().strip(".")
    entries = [e.strip() for e in _SEP_RE.split(normalized) if e.strip()]
    if not entries:
        entries = [normalized]

    result: list[tuple[str, str, tuple]] = []
    seen: set[str] = set()

    for entry in entries:
        low = entry.lower()
        matched = False
        for keyword, (display, default_dose, color) in _MED_DB.items():
            if keyword in low:
                if display in seen:
                    matched = True
                    break
                seen.add(display)
                m = re.search(r"(\d+)\s*(comp|jato|ml)\w*", entry, re.IGNORECASE)
                dose = f"{m.group(1)} {m.group(2).lower()}" if m else default_dose
                result.append((display, dose, color))
                matched = True
                break
        if not matched and entry:
            # Medicamento desconhecido — exibe como está
            result.append((entry[:40], "", SW_GRAY))

    return result or [(normalized[:40], "", SW_GRAY)]


def _med_color(name: str, color: tuple) -> tuple:
    """Returns the RGB color for a medication (kept for external use)."""
    return color


def _time_from_reminder(reminder: dict) -> str:
    recurrence = str(reminder.get("recurrence") or "")
    match = re.search(r"\b(\d{2}:\d{2})\b", recurrence)
    if match:
        return match.group(1)
    trigger_at = int(reminder.get("trigger_at") or 0)
    if trigger_at:
        return datetime.fromtimestamp(trigger_at, LOCAL_TZ).strftime("%H:%M")
    return datetime.now(LOCAL_TZ).strftime("%H:%M")


def _font(path: Path, size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    try:
        return ImageFont.truetype(str(path), size=size)
    except Exception:
        return ImageFont.load_default()


def _wrap(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont, width: int) -> list[str]:
    words = text.split()
    lines: list[str] = []
    current = ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if draw.textlength(candidate, font=font) <= width:
            current = candidate
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines or [text]


def _pill(draw: ImageDraw.ImageDraw, xy: tuple, fill: str, outline: str | None = None):
    draw.rounded_rectangle(xy, radius=26, fill=fill, outline=outline, width=3 if outline else 1)


def _sw_brackets(draw: ImageDraw.ImageDraw, x1: int, y1: int, x2: int, y2: int,
                 size: int = 50, color: tuple = SW_GOLD, w: int = 4) -> None:
    draw.line([(x1, y1 + size), (x1, y1), (x1 + size, y1)], fill=color, width=w)
    draw.line([(x2 - size, y1), (x2, y1), (x2, y1 + size)], fill=color, width=w)
    draw.line([(x1, y2 - size), (x1, y2), (x1 + size, y2)], fill=color, width=w)
    draw.line([(x2 - size, y2), (x2, y2), (x2, y2 - size)], fill=color, width=w)


def _card_layout(n: int) -> tuple[int, int, int, int, int]:
    """(row_h, font_med, font_dose, dot_r, font_num) sized to fill panel."""
    # Panel content area: y=558 to y=935 → 377px
    if n <= 2:   return 140, 44, 38, 14, 26
    elif n <= 3: return 125, 42, 36, 13, 24
    elif n <= 4: return  94, 36, 30, 11, 20
    elif n <= 5: return  75, 30, 25, 10, 18
    elif n <= 6: return  63, 26, 21,  9, 16
    else:        return  53, 22, 18,  8, 14


# ─────────────────────────────────────────────────────────────────────────────
# Basic fallback card (sync, no network)
# ─────────────────────────────────────────────────────────────────────────────

def render_reminder_card(reminder: dict) -> str:
    """Create a basic PNG card. Sync fallback when Star Wars card fails."""
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    rid = int(reminder.get("id") or 0)
    time_label = _time_from_reminder(reminder)
    meds = _medication_lines(str(reminder.get("text") or ""))
    n = len(meds)
    row_h, fs_med, fs_dose, dot_r, fs_num = _card_layout(n)

    img = Image.new("RGB", (1080, 1080), "#071c22")
    draw = ImageDraw.Draw(img)
    for y in range(1080):
        ratio = y / 1080
        draw.line([(0, y), (1080, y)],
                  fill=(int(7 + ratio * 18), int(28 + ratio * 35), int(34 + ratio * 22)))

    draw.ellipse((-180, -160, 360, 360), fill="#0f766e")
    draw.ellipse((790, 730, 1240, 1180), fill="#b45309")
    draw.rectangle((0, 0, 1080, 1080), outline="#fbbf24", width=10)
    draw.rounded_rectangle((46, 46, 1034, 1034), radius=54, outline="#2dd4bf", width=4)

    f_title = _font(FONT_BOLD, 62)
    f_time  = _font(FONT_BOLD, 184)
    f_med   = _font(FONT_BOLD, fs_med)
    f_dose  = _font(FONT_BOLD, fs_dose)
    f_num   = _font(FONT_BOLD, fs_num)
    f_small = _font(FONT_REGULAR, 31)

    draw.text((90, 92), "HORA DO REMÉDIO", fill="#fef3c7", font=f_title)
    draw.text((90, 160), "confere a dose e marca como tomado", fill="#b8f7ee", font=f_small)

    draw.rounded_rectangle((90, 245, 990, 460), radius=42, fill="#fff7ed", outline="#fbbf24", width=5)
    tw = draw.textlength(time_label, font=f_time)
    draw.text(((1080 - tw) / 2, 250), time_label, fill="#9a3412", font=f_time)

    y = 500
    for idx, (name, dose, color) in enumerate(meds[:8], 1):
        _pill(draw, (90, y, 990, y + row_h - 8), fill="#f8fafc", outline=f"#{color[0]:02x}{color[1]:02x}{color[2]:02x}")
        draw.ellipse((115, y + (row_h - dot_r * 2) // 2,
                      115 + dot_r * 2, y + (row_h - dot_r * 2) // 2 + dot_r * 2), fill=color)
        nw = draw.textlength(str(idx), font=f_num)
        draw.text((115 + dot_r - nw // 2, y + (row_h - fs_num) // 2), str(idx),
                  fill="#ffffff", font=f_num)
        for li, line in enumerate(_wrap(draw, name, f_med, 530)[:2]):
            draw.text((160, y + (row_h - fs_med) // 2 + li * (fs_med + 2)), line,
                      fill="#0f172a", font=f_med)
        if dose:
            dw = draw.textlength(dose, font=f_dose)
            draw.text((948 - dw, y + (row_h - fs_dose) // 2), dose, fill=color, font=f_dose)
        y += row_h

    path = OUT_DIR / f"reminder_{rid}_{int(datetime.now(LOCAL_TZ).timestamp())}.png"
    img.save(path, "PNG", optimize=True)
    return str(path)


# ─────────────────────────────────────────────────────────────────────────────
# Star Wars card
# ─────────────────────────────────────────────────────────────────────────────

_SW_PROMPTS = [
    "Star Wars X-wing fighter squadron attacking Death Star, laser blasts, massive explosions, deep space, dramatic cinematic lighting, photorealistic, film still, epic scale",
    "Star Wars lightsaber duel Jedi versus Sith, blue blade versus red blade, heavy rain at night, plasma sparks, dramatic underlighting, dark cinematic, photorealistic, 8k",
    "Star Wars Mandalorian warrior beskar armor standing on Tatooine cliff, twin suns sunset, golden silhouette, volumetric light rays, cinematic, photorealistic, epic",
    "Star Wars Millennium Falcon jumping to hyperspace, swirling blue white tunnel, cockpit view, dramatic, cinematic, photorealistic",
    "Star Wars TIE fighters chasing X-wings through asteroid field, explosions, laser fire, epic space battle, cinematic wide angle, photorealistic",
    "Star Wars Jedi master meditating in ancient temple, force energy glowing, mystical golden light, dramatic shadows, cinematic portrait, photorealistic",
    "Star Wars Darth Vader standing on bridge of Star Destroyer, deep space backdrop, dramatic lighting, imposing silhouette, cinematic, photorealistic",
    "Star Wars clone trooper army marching on alien planet, dramatic sky, two moons, epic scale, cinematic, photorealistic",
    "Star Wars rebel fleet battle, Star Destroyers versus Mon Calamari cruisers, laser fire everywhere, epic space opera, cinematic, photorealistic",
    "Star Wars Coruscant city at night, towering skyscrapers, flying speeders, neon lights, rain-slicked streets, blade runner aesthetic, cinematic",
]

_SW_FLAVOR = [
    "Que a Força esteja com você.",
    "Use a Força, jovem padawan.",
    "Este é o caminho.",
    "A Força é forte em você.",
    "Faça ou não faça, não existe tentar.",
    "Um Jedi usa a Força para o conhecimento e defesa.",
    "A galáxia não pode esperar. Toma seu remédio.",
    "Até o lado sombrio cuida da saúde.",
]

# ─────────────────────────────────────────────────────────────────────────────
# Layout 1080×1080:
#  [  0–165]  Header band   — título, tick separator
#  [165–490]  Image zone    — fundo visível, horário gigante com glow
#  [490–510]  Transição
#  [510–935]  Painel médico — cards de remédio (escala com quantidade)
#  [935–1080] Footer        — separador, quote Star Wars
# ─────────────────────────────────────────────────────────────────────────────

_IMG_TAG_RE = re.compile(r"^\[IMG:\s*(.+?)\]\n?", re.IGNORECASE)


def _extract_img_prompt(text: str) -> tuple[str, str | None]:
    """Remove [IMG: prompt] da primeira linha do texto. Retorna (texto_limpo, prompt|None)."""
    m = _IMG_TAG_RE.match(text or "")
    if m:
        return text[m.end():].strip(), m.group(1).strip()
    return text, None


async def render_starwars_card(reminder: dict) -> str:
    """Cinematic card with AI background. Returns PNG path."""
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    rid        = int(reminder.get("id") or 0)
    time_label = _time_from_reminder(reminder)
    raw_text   = str(reminder.get("text") or "")
    clean_text, custom_prompt = _extract_img_prompt(raw_text)
    meds       = _medication_lines(clean_text)
    n          = len(meds)
    seed       = random.randint(1, 99999)

    row_h, fs_med, fs_dose, dot_r, fs_num = _card_layout(n)

    f_title  = _font(FONT_ORBITRON, 52)
    f_time   = _font(FONT_ORBITRON, 190)
    f_label  = _font(FONT_ORBITRON, 24)
    f_med    = _font(FONT_ORBITRON, fs_med)
    f_dose   = _font(FONT_ORBITRON, fs_dose)
    f_num    = _font(FONT_ORBITRON, fs_num)
    f_flavor = _font(FONT_ORBITRON, 26)

    _probe = ImageDraw.Draw(Image.new("RGB", (1, 1)))
    tw = int(_probe.textlength(time_label, font=f_time))
    tx, ty = (1080 - tw) // 2, 205

    # ── Background via Cloudflare Worker (flux-schnell) ────────────────────────
    prompt = custom_prompt if custom_prompt else random.choice(_SW_PROMPTS)
    try:
        from hyrule_env import CF_WORKER_IMG_URL as _worker_url
    except ImportError:
        _worker_url = None

    bg: Image.Image | None = None
    if _worker_url:
        try:
            async with httpx.AsyncClient(timeout=90) as client:
                resp = await client.post(_worker_url, json={"prompt": prompt, "model": "flux-schnell"})
                if resp.status_code == 200:
                    bg = Image.open(io.BytesIO(resp.content)).convert("RGBA").resize((1080, 1080))
        except Exception:
            pass

    if bg is None:
        bg = Image.new("RGBA", (1080, 1080), (0, 0, 12, 255))
        _d = ImageDraw.Draw(bg)
        for _ in range(350):
            sx, sy = random.randint(0, 1079), random.randint(0, 1079)
            br = random.randint(120, 255)
            r  = random.randint(1, 2)
            _d.ellipse((sx, sy, sx + r, sy + r), fill=(br, br, br, 255))

    canvas = bg.copy()

    # ── Layer A: bandas escuras ────────────────────────────────────────────────
    bands = Image.new("RGBA", (1080, 1080), (0, 0, 0, 0))
    bd = ImageDraw.Draw(bands)
    for y in range(175):
        a = int(245 * (1 - y / 175) ** 0.55)
        bd.line([(0, y), (1080, y)], fill=(0, 0, 10, a))
    for y in range(483, 1080):
        a_base = 220 if y > 535 else int(220 * (y - 483) / 52)
        bd.line([(0, y), (1080, y)], fill=(*SW_DARK, a_base))
    canvas = Image.alpha_composite(canvas, bands)

    # ── Layer B: glow (blur) ───────────────────────────────────────────────────
    glow = Image.new("RGBA", (1080, 1080), (0, 0, 0, 0))
    gl   = ImageDraw.Draw(glow)
    gl.text((tx, ty), time_label, fill=(*SW_GOLD, 120), font=f_time)
    py = 558
    for name, dose, color in meds[:8]:
        cx, cy = 132, py + row_h // 2
        gl.ellipse((cx - dot_r * 2 - 4, cy - dot_r * 2 - 4,
                    cx + dot_r * 2 + 4, cy + dot_r * 2 + 4), fill=(*color, 80))
        gl.ellipse((cx - dot_r - 2, cy - dot_r - 2,
                    cx + dot_r + 2, cy + dot_r + 2), fill=(*color, 190))
        py += row_h
    canvas = Image.alpha_composite(canvas, glow.filter(ImageFilter.GaussianBlur(radius=20)))

    # ── Layer C: backgrounds dos cards ─────────────────────────────────────────
    cards = Image.new("RGBA", (1080, 1080), (0, 0, 0, 0))
    cd = ImageDraw.Draw(cards)
    py = 558
    for name, dose, color in meds[:8]:
        cd.rounded_rectangle(
            (80, py, 1000, py + row_h - 4),
            radius=14,
            fill=(3, 10, 32, 215),
            outline=(*color, 225),
            width=2,
        )
        py += row_h
    canvas = Image.alpha_composite(canvas, cards)

    # ── Elementos fixos ────────────────────────────────────────────────────────
    draw = ImageDraw.Draw(canvas)

    # Título
    draw.text((80, 42), "HORA DO REMÉDIO", fill=SW_GOLD, font=f_title,
              stroke_width=3, stroke_fill=(0, 0, 0))

    # Separador header
    draw.line([(58, 150), (1022, 150)], fill=SW_GOLD, width=2)
    for x in range(58, 1023, 46):
        h = 7 if x % 230 < 5 else 3
        draw.line([(x, 150 - h), (x, 150 + h)], fill=SW_GOLD, width=1)

    # "MISSÃO AGENDADA"
    mission = "MISSÃO AGENDADA"
    mw = int(draw.textlength(mission, font=f_label))
    draw.text(((1080 - mw) // 2, 170), mission, fill=SW_CYAN, font=f_label,
              stroke_width=1, stroke_fill=(0, 0, 0))

    # Horário
    draw.text((tx, ty), time_label, fill=SW_GOLD, font=f_time,
              stroke_width=10, stroke_fill=(0, 0, 0))

    # Divisor com diamantes
    draw.line([(55, 504), (1025, 504)], fill=SW_GOLD, width=3)
    for dx in [180, 540, 900]:
        draw.polygon([(dx, 496), (dx + 8, 504), (dx, 512), (dx - 8, 504)], fill=SW_GOLD)

    # Header do painel
    status = "STATUS: MEDICAMENTOS"
    sw = int(draw.textlength(status, font=f_label))
    draw.text(((1080 - sw) // 2, 513), status, fill=SW_CYAN, font=f_label,
              stroke_width=1, stroke_fill=(0, 0, 0))

    # Cards de remédio
    py = 558
    for idx, (name, dose, color) in enumerate(meds[:8], 1):
        mid_y = py + row_h // 2
        cx, cy = 132, mid_y

        # Ponto brilhante
        draw.ellipse((cx - dot_r, cy - dot_r, cx + dot_r, cy + dot_r), fill=color)

        # Número dentro do ponto (só se couber)
        if dot_r >= 9:
            num_str = str(idx)
            nw = int(draw.textlength(num_str, font=f_num))
            draw.text((cx - nw // 2, cy - fs_num // 2), num_str,
                      fill=SW_WHITE, font=f_num,
                      stroke_width=1, stroke_fill=(0, 0, 0))

        # Nome do remédio
        for li, line in enumerate(_wrap(draw, name, f_med, 560)[:2]):
            draw.text((165, py + (row_h - fs_med) // 2 + li * (fs_med + 1)), line,
                      fill=SW_WHITE, font=f_med,
                      stroke_width=2, stroke_fill=(0, 0, 0))

        # Dose (direita)
        if dose:
            dw = int(draw.textlength(dose, font=f_dose))
            draw.text((988 - dw, py + (row_h - fs_dose) // 2), dose,
                      fill=color, font=f_dose,
                      stroke_width=2, stroke_fill=(0, 0, 0))

        py += row_h

    # Footer
    draw.line([(58, 937), (1022, 937)], fill=SW_GOLD, width=2)
    flavor = random.choice(_SW_FLAVOR)
    fw = int(draw.textlength(flavor, font=f_flavor))
    draw.text(((1080 - fw) // 2, 960), flavor, fill=SW_GRAY, font=f_flavor,
              stroke_width=1, stroke_fill=(0, 0, 0))

    # Borda + brackets
    draw.rectangle((0, 0, 1079, 1079), outline=SW_GOLD, width=6)
    _sw_brackets(draw, 22, 22, 1058, 1058, size=50, color=SW_GOLD, w=4)

    path = OUT_DIR / f"sw_reminder_{rid}_{seed}.png"
    canvas.convert("RGB").save(path, "PNG", optimize=True)
    return str(path)


def reminder_caption(reminder: dict) -> str:
    time_label = _time_from_reminder(reminder)
    meds = _medication_lines(str(reminder.get("text") or ""))
    lines = [f"*Lembrete das {time_label}*"]
    for name, dose, _ in meds:
        lines.append(f"- {name}: {dose}" if dose else f"- {name}")
    return "\n".join(lines)


def plain_reminder_text(reminder: dict) -> str:
    time_label = _time_from_reminder(reminder)
    text = str(reminder.get("text") or "").strip()
    return f"Lembrete das {time_label}: {text}"


def _schedule_time_key(reminder: dict) -> tuple[int, int, str]:
    label = _time_from_reminder(reminder)
    try:
        hh, mm = [int(x) for x in label.split(":", 1)]
        return hh, mm, label
    except Exception:
        return 99, 99, label


def medication_schedule_items(reminders: list[dict]) -> list[tuple[str, list[tuple[str, str, tuple]]]]:
    items: list[tuple[str, list[tuple[str, str, tuple]]]] = []
    for reminder in sorted(reminders, key=_schedule_time_key):
        text = str(reminder.get("text") or "")
        meds = _medication_lines(text)
        if not meds or not any(color != SW_GRAY for _, _, color in meds):
            continue
        items.append((_time_from_reminder(reminder), meds))
    return items


def medication_schedule_caption(reminders: list[dict]) -> str:
    items = medication_schedule_items(reminders)
    lines = ["*Rotina de remédios*"]
    for time_label, meds in items:
        med_line = "; ".join(
            f"{name}: {dose}" if dose else name
            for name, dose, _ in meds
        )
        lines.append(f"- {time_label} - {med_line}")
    return "\n".join(lines)


def render_medication_schedule_card(reminders: list[dict]) -> str:
    """Create a Star-Wars-style routine card with all medication times."""
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    items = medication_schedule_items(reminders)
    seed = random.randint(1, 99999)

    W, H = 1080, 1520
    img = Image.new("RGBA", (W, H), SW_DARK + (255,))
    draw = ImageDraw.Draw(img)

    for y in range(H):
        ratio = y / H
        draw.line(
            [(0, y), (W, y)],
            fill=(
                int(0 + ratio * 5),
                int(4 + ratio * 12),
                int(18 + ratio * 34),
                255,
            ),
        )
    for _ in range(430):
        sx, sy = random.randint(0, W - 1), random.randint(0, H - 1)
        br = random.randint(90, 240)
        r = random.randint(1, 2)
        draw.ellipse((sx, sy, sx + r, sy + r), fill=(br, br, br, 180))

    top_glow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    gd = ImageDraw.Draw(top_glow)
    gd.ellipse((-230, -230, 520, 520), fill=(0, 210, 232, 46))
    gd.ellipse((720, 900, 1350, 1530), fill=(255, 232, 26, 28))
    img = Image.alpha_composite(img, top_glow.filter(ImageFilter.GaussianBlur(radius=46)))
    draw = ImageDraw.Draw(img)

    f_title = _font(FONT_ORBITRON, 48)
    f_sub = _font(FONT_ORBITRON, 25)
    f_time = _font(FONT_ORBITRON, 48)
    f_med = _font(FONT_ORBITRON, 27)
    f_dose = _font(FONT_ORBITRON, 23)
    f_small = _font(FONT_ORBITRON, 20)

    draw.text((80, 48), "ROTINA DE REMÉDIOS", fill=SW_GOLD, font=f_title,
              stroke_width=3, stroke_fill=(0, 0, 0))
    subtitle = "TODOS OS HORÁRIOS"
    sw = int(draw.textlength(subtitle, font=f_sub))
    draw.text((W - 80 - sw, 66), subtitle, fill=SW_CYAN, font=f_sub,
              stroke_width=1, stroke_fill=(0, 0, 0))
    draw.line([(58, 130), (1022, 130)], fill=SW_GOLD, width=2)
    for x in range(58, 1023, 46):
        draw.line([(x, 126), (x, 134)], fill=SW_GOLD, width=1)

    if not items:
        msg = "Nenhuma rotina de remédio ativa."
        mw = int(draw.textlength(msg, font=f_time))
        draw.text(((W - mw) // 2, H // 2 - 30), msg, fill=SW_GRAY, font=f_time)
    else:
        gap = 16
        top = 172
        y = top

        for time_label, meds in items:
            row_h = max(112, 48 + min(len(meds), 7) * 31)
            colors = [color for _, _, color in meds if color != SW_GRAY]
            accent = colors[0] if colors else SW_CYAN
            card = Image.new("RGBA", (W, H), (0, 0, 0, 0))
            cd = ImageDraw.Draw(card)
            cd.rounded_rectangle(
                (64, y, 1016, y + row_h),
                radius=16,
                fill=(3, 10, 32, 220),
                outline=(*accent, 230),
                width=2,
            )
            img = Image.alpha_composite(img, card)
            draw = ImageDraw.Draw(img)

            draw.rounded_rectangle((88, y + 22, 252, y + row_h - 22),
                                   radius=14, fill=(0, 0, 0, 165),
                                   outline=SW_GOLD, width=2)
            tw = int(draw.textlength(time_label, font=f_time))
            draw.text((88 + (164 - tw) // 2, y + (row_h - 48) // 2 - 4),
                      time_label, fill=SW_GOLD, font=f_time,
                      stroke_width=3, stroke_fill=(0, 0, 0))

            med_y = y + 18
            col_x = 286
            line_h = max(30, min(35, (row_h - 30) // max(1, len(meds))))
            for idx, (name, dose, color) in enumerate(meds[:7]):
                yy = med_y + idx * line_h
                dot_r = 7
                draw.ellipse((col_x, yy + 8, col_x + dot_r * 2, yy + 8 + dot_r * 2),
                             fill=color)
                label = name
                draw.text((col_x + 26, yy), label, fill=SW_WHITE, font=f_med,
                          stroke_width=2, stroke_fill=(0, 0, 0))
                if dose:
                    dw = int(draw.textlength(dose, font=f_dose))
                    draw.text((980 - dw, yy + 2), dose, fill=color, font=f_dose,
                              stroke_width=2, stroke_fill=(0, 0, 0))

            y += row_h + gap

    footer = "confere a rotina antes de marcar como tomado"
    fw = int(draw.textlength(footer, font=f_small))
    draw.line([(58, H - 78), (1022, H - 78)], fill=SW_GOLD, width=2)
    draw.text(((W - fw) // 2, H - 54), footer, fill=SW_GRAY, font=f_small,
              stroke_width=1, stroke_fill=(0, 0, 0))
    draw.rectangle((0, 0, W - 1, H - 1), outline=SW_GOLD, width=6)
    _sw_brackets(draw, 22, 22, W - 22, H - 22, size=50, color=SW_GOLD, w=4)

    path = OUT_DIR / f"sw_med_schedule_{seed}.png"
    img.convert("RGB").save(path, "PNG", optimize=True)
    return str(path)
