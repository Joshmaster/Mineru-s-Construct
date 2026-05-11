"""Visual cards and captions for medication reminders."""

from __future__ import annotations

import re
import tempfile
import textwrap
from datetime import datetime
from pathlib import Path
from typing import Iterable
from zoneinfo import ZoneInfo

from PIL import Image, ImageDraw, ImageFont


LOCAL_TZ = ZoneInfo("America/Sao_Paulo")
ROOT = Path(__file__).resolve().parents[3]
OUT_DIR = ROOT / ".linkbot" / "reminder_cards"

FONT_BOLD = Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf")
FONT_REGULAR = Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf")


def _font(path: Path, size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    try:
        return ImageFont.truetype(str(path), size=size)
    except Exception:
        return ImageFont.load_default()


def _time_from_reminder(reminder: dict) -> str:
    recurrence = str(reminder.get("recurrence") or "")
    match = re.search(r"\b(\d{2}:\d{2})\b", recurrence)
    if match:
        return match.group(1)

    trigger_at = int(reminder.get("trigger_at") or 0)
    if trigger_at:
        return datetime.fromtimestamp(trigger_at, LOCAL_TZ).strftime("%H:%M")
    return datetime.now(LOCAL_TZ).strftime("%H:%M")


def _medication_lines(text: str) -> list[tuple[str, str]]:
    parts: list[tuple[str, str]] = []
    normalized = (text or "").strip().strip(".")

    patterns = [
        (r"Aerolin\s*:?\s*([0-9]+)\s*jatos?", "Aerolin"),
        (r"Formoterol\s*/\s*Budesonida\s*:?\s*([0-9]+)\s*jatos?", "Formoterol/Budesonida"),
        (r"Formoterol\s*\+\s*Budesonida\s*:?\s*([0-9]+)\s*jatos?", "Formoterol/Budesonida"),
    ]
    for pattern, name in patterns:
        match = re.search(pattern, normalized, flags=re.IGNORECASE)
        if match:
            parts.append((name, f"{match.group(1)} jatos"))

    if parts:
        return parts

    return [(line.strip(), "") for line in re.split(r"\.\s*", normalized) if line.strip()]


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


def _pill(draw: ImageDraw.ImageDraw, xy: tuple[int, int, int, int], fill: str, outline: str | None = None):
    draw.rounded_rectangle(xy, radius=26, fill=fill, outline=outline, width=3 if outline else 1)


def render_reminder_card(reminder: dict) -> str:
    """Create a PNG card for a reminder and return its path."""

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    rid = int(reminder.get("id") or 0)
    time_label = _time_from_reminder(reminder)
    meds = _medication_lines(str(reminder.get("text") or ""))

    img = Image.new("RGB", (1080, 1080), "#071c22")
    draw = ImageDraw.Draw(img)

    # Layered bold background, kept deterministic for medical reminders.
    for y in range(1080):
        ratio = y / 1080
        r = int(7 + ratio * 18)
        g = int(28 + ratio * 35)
        b = int(34 + ratio * 22)
        draw.line([(0, y), (1080, y)], fill=(r, g, b))

    draw.ellipse((-180, -160, 360, 360), fill="#0f766e")
    draw.ellipse((790, 730, 1240, 1180), fill="#b45309")
    draw.rectangle((0, 0, 1080, 1080), outline="#fbbf24", width=10)
    draw.rounded_rectangle((46, 46, 1034, 1034), radius=54, outline="#2dd4bf", width=4)

    title_font = _font(FONT_BOLD, 62)
    time_font = _font(FONT_BOLD, 184)
    label_font = _font(FONT_BOLD, 36)
    med_font = _font(FONT_BOLD, 58)
    dose_font = _font(FONT_BOLD, 50)
    small_font = _font(FONT_REGULAR, 31)

    draw.text((90, 92), "HORA DO REMÉDIO", fill="#fef3c7", font=title_font)
    draw.text((90, 160), "respira fundo, pega a bombinha e confere a dose", fill="#b8f7ee", font=small_font)

    draw.rounded_rectangle((90, 250, 990, 465), radius=42, fill="#fff7ed", outline="#fbbf24", width=5)
    time_w = draw.textlength(time_label, font=time_font)
    draw.text(((1080 - time_w) / 2, 253), time_label, fill="#9a3412", font=time_font)

    y = 540
    for idx, (name, dose) in enumerate(meds[:3], start=1):
        color = "#dc2626" if "Aerolin" in name else "#0891b2"
        _pill(draw, (90, y, 990, y + 118), fill="#f8fafc", outline=color)
        draw.ellipse((120, y + 30, 178, y + 88), fill=color)
        num = str(idx)
        num_w = draw.textlength(num, font=label_font)
        draw.text((149 - num_w / 2, y + 34), num, fill="#ffffff", font=label_font)

        for line_idx, line in enumerate(_wrap(draw, name, med_font, 520)[:2]):
            draw.text((205, y + 22 + line_idx * 52), line, fill="#0f172a", font=med_font)
        if dose:
            dose_w = draw.textlength(dose, font=dose_font)
            draw.text((940 - dose_w, y + 34), dose, fill=color, font=dose_font)
        y += 145

    footer = "Marca como tomado depois que usar."
    draw.rounded_rectangle((90, 932, 990, 998), radius=26, fill="#0f172a", outline="#2dd4bf", width=2)
    footer_w = draw.textlength(footer, font=small_font)
    draw.text(((1080 - footer_w) / 2, 949), footer, fill="#e0f2fe", font=small_font)

    path = OUT_DIR / f"reminder_{rid}_{int(datetime.now(LOCAL_TZ).timestamp())}.png"
    img.save(path, "PNG", optimize=True)
    return str(path)


def reminder_caption(reminder: dict) -> str:
    time_label = _time_from_reminder(reminder)
    meds = _medication_lines(str(reminder.get("text") or ""))
    lines = [f"*Lembrete das {time_label}*"]
    for name, dose in meds:
        lines.append(f"- {name}: {dose}" if dose else f"- {name}")
    return "\n".join(lines)


def plain_reminder_text(reminder: dict) -> str:
    time_label = _time_from_reminder(reminder)
    text = str(reminder.get("text") or "").strip()
    return f"Lembrete das {time_label}: {text}"
