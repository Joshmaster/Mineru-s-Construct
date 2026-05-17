"""Skill: !img — gera imagem via Cloudflare Worker (flux-schnell) ou OpenRouter (fallback)."""

import asyncio
import base64
import json
import os
import re
import tempfile
import time
import urllib.parse
import urllib.request
from pathlib import Path

from bot.core.router import Skill
from bot.core.context import MessageContext
from bot.core import access as access_ctl

try:
    from hyrule_env import OPENROUTER_KEYS
except Exception:
    OPENROUTER_KEYS = []


OPENROUTER_MODELOS = {
    "gemini": {
        "nome": "Gemini / Nano Banana",
        "id": "google/gemini-2.5-flash-image",
    },
    "openai": {
        "nome": "ChatGPT / OpenAI Image",
        "id": "openai/gpt-5-image",
    },
}
DEFAULT_OPENROUTER_MODEL = "gemini"
DEFAULT_ASPECT = "1:1"
ASPECT_RE = re.compile(r"^(1:1|16:9|9:16|4:3|3:4)$")

ASPECT_TO_SIZE = {
    "1:1":  (1080, 1080),
    "16:9": (1280, 720),
    "9:16": (720, 1280),
    "4:3":  (1080, 810),
    "3:4":  (810, 1080),
}


def _load_dotenv_keys() -> list[str]:
    keys = []
    for env_path in [Path.cwd() / ".env", Path(__file__).resolve().parents[3] / ".env", Path(__file__).resolve().parents[2] / ".env"]:
        if not env_path.exists():
            continue
        try:
            for line in env_path.read_text(encoding="utf-8", errors="ignore").splitlines():
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                name, value = line.split("=", 1)
                name = name.strip()
                value = value.strip().strip('"').strip("'")
                if name in {"OPENROUTER_API_KEY", "OPENROUTER_KEY"} and value:
                    keys.append(value)
        except Exception:
            pass
    return keys


def _openrouter_keys() -> list[str]:
    seen = set()
    keys = []
    candidates = [
        os.getenv("OPENROUTER_API_KEY", ""),
        os.getenv("OPENROUTER_KEY", ""),
        *(_load_dotenv_keys()),
        *(OPENROUTER_KEYS or []),
    ]
    for key in candidates:
        key = str(key or "").strip()
        if not key or key in seen:
            continue
        seen.add(key)
        keys.append(key)
    return keys


def _is_owner(ctx: MessageContext) -> bool:
    try:
        sid = str(getattr(ctx.sender_jid, "User", "") or ctx.sender_jid)
        return access_ctl.is_admin(ctx.sender_jid, ctx.chat_jid, sid, cfg=access_ctl.load_config())
    except Exception:
        return False


def _parse_args(text: str) -> tuple[str, str, str, bool]:
    """Retorna (modelo_openrouter, aspect, prompt, forcar_openrouter)."""
    prompt = (text or "").strip()
    modelo = DEFAULT_OPENROUTER_MODEL
    aspect = DEFAULT_ASPECT
    forcar_openrouter = False

    def repl_model(m):
        nonlocal modelo, forcar_openrouter
        raw = m.group(1).strip().lower()
        if raw in {"1", "gemini", "nano", "banana", "nanobanana"}:
            modelo = "gemini"
            forcar_openrouter = True
        elif raw in {"2", "openai", "chatgpt", "gpt"}:
            modelo = "openai"
            forcar_openrouter = True
        elif raw in {"openrouter", "or"}:
            forcar_openrouter = True
        return " "

    prompt = re.sub(r"(?i)\b(?:modelo|model)\s*[:=]\s*(gemini|nano|banana|nanobanana|openai|chatgpt|gpt|openrouter|or|1|2)\b", repl_model, prompt)
    prompt = re.sub(r"(?i)(?:^|\s)--?(gemini|nano|banana|nanobanana|openai|chatgpt|gpt|openrouter|or)\b", repl_model, prompt)

    def repl_aspect(m):
        nonlocal aspect
        val = m.group(1).strip()
        if ASPECT_RE.match(val):
            aspect = val
        return " "

    prompt = re.sub(r"(?i)\b(?:ar|aspect|aspect_ratio|formato)\s*[:=]\s*(1:1|16:9|9:16|4:3|3:4)\b", repl_aspect, prompt)
    prompt = re.sub(r"(?<!\S)(1:1|16:9|9:16|4:3|3:4)(?!\S)", repl_aspect, prompt)
    prompt = re.sub(r"\s+", " ", prompt).strip(" -.,;:")
    return modelo, aspect, prompt, forcar_openrouter


def _gerar_cloudflare(prompt: str, aspect: str) -> tuple[str | None, str]:
    try:
        from hyrule_env import CF_WORKER_IMG_URL as _url
    except ImportError:
        return None, "CF_WORKER_IMG_URL não configurado em hyrule_env.py"
    width, height = ASPECT_TO_SIZE.get(aspect, (1080, 1080))
    payload = json.dumps({"prompt": prompt, "model": "flux-schnell", "width": width, "height": height}).encode()
    try:
        req = urllib.request.Request(
            _url, data=payload,
            headers={"Content-Type": "application/json", "User-Agent": "HyruleBot/1.0"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=90) as resp:
            if resp.status != 200:
                return None, f"Cloudflare Worker retornou {resp.status}"
            data = resp.read()
        out = Path(tempfile.gettempdir()) / f"hyrule_img_{int(time.time())}_{time.time_ns()}.jpg"
        out.write_bytes(data)
        return str(out), f"Cloudflare Flux · {aspect}"
    except Exception as e:
        return None, str(e)


def _extract_data_url(data: dict) -> tuple[str | None, str]:
    try:
        message = data["choices"][0]["message"]
    except Exception:
        return None, ""

    text = str(message.get("content") or "").strip()
    images = message.get("images") or []
    for image_obj in images:
        if not isinstance(image_obj, dict):
            continue
        image_url = image_obj.get("image_url") or {}
        if isinstance(image_url, dict):
            url = image_url.get("url") or ""
            if url.startswith("data:image/"):
                return url, text
    return None, text


def _save_data_url(data_url: str, output_file: Path):
    if "," not in data_url:
        raise ValueError("data URL inválida")
    _, encoded = data_url.split(",", 1)
    output_file.write_bytes(base64.b64decode(encoded))


def _gerar_openrouter(prompt: str, modelo_key: str, aspect_ratio: str) -> tuple[str | None, str]:
    keys = _openrouter_keys()
    if not keys:
        return None, "OPENROUTER_API_KEY/OPENROUTER_KEYS não configurado."

    modelo = OPENROUTER_MODELOS[modelo_key]
    payload = {
        "model": modelo["id"],
        "messages": [{"role": "user", "content": prompt}],
        "modalities": ["image", "text"],
        "image_config": {
            "aspect_ratio": aspect_ratio,
        },
    }
    body = json.dumps(payload).encode("utf-8")
    last_error = ""
    unauthorized = 0

    for key in keys:
        req = urllib.request.Request(
            "https://openrouter.ai/api/v1/chat/completions",
            data=body,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {key}",
                "HTTP-Referer": "http://localhost",
                "X-Title": "Hyrule Image Generator",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            data_url, text = _extract_data_url(data)
            if not data_url:
                return None, text or "nenhuma imagem voltou do modelo."
            out = Path(tempfile.gettempdir()) / f"hyrule_img_{int(time.time())}_{time.time_ns()}.png"
            _save_data_url(data_url, out)
            return str(out), f"{modelo['nome']} · {aspect_ratio}"
        except urllib.error.HTTPError as e:
            last_error = f"HTTP {e.code}: {e.reason}"
            if e.code in (401, 403):
                unauthorized += 1
            try:
                body_err = e.read().decode("utf-8", errors="ignore")
                if body_err:
                    last_error = f"{last_error} · {body_err[:300]}"
            except Exception:
                pass
            continue
        except Exception as e:
            last_error = str(e)
            continue

    if unauthorized == len(keys):
        return None, "OpenRouter recusou todas as chaves configuradas para gerar imagem (401/403)."
    return None, f"não consegui gerar a imagem agora: {last_error}"


import logging as _log_mod
log = _log_mod.getLogger("img_gerar")


def _apply_overlay(path: str, text: str):
    try:
        from PIL import Image, ImageDraw, ImageFont
        _FONT = Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf")
        img = Image.open(path).convert("RGB")
        w, h = img.size
        draw = ImageDraw.Draw(img)
        try:
            font = ImageFont.truetype(str(_FONT), size=max(32, h // 20))
        except Exception:
            font = ImageFont.load_default()
        tw = int(draw.textlength(text, font=font))
        draw.text(
            ((w - tw) // 2, h - int(h * 0.12)),
            text, fill=(255, 255, 255),
            font=font, stroke_width=4, stroke_fill=(0, 0, 0),
        )
        img.save(path, "PNG")
    except Exception as e:
        log.warning(f"Overlay PIL falhou: {e}")


async def handle(ctx: MessageContext):
    if not _is_owner(ctx):
        await ctx.reply("🔒 geração de imagem fica só pro dono.")
        return

    raw = (ctx.args_text or "").strip()
    if not raw:
        await ctx.reply("manda assim: `!img um castelo de Hyrule ao pôr do sol`")
        return

    overlay_text = ""
    if "::" in raw:
        parts = raw.split("::", 1)
        raw = parts[0].strip()
        overlay_text = parts[1].strip()

    await ctx.typing()

    modelo_key, aspect, prompt_clean, forcar_openrouter = _parse_args(raw)
    prompt = prompt_clean or raw

    path = info = None

    if not forcar_openrouter:
        path, info = await asyncio.get_event_loop().run_in_executor(
            None, _gerar_cloudflare, prompt, aspect
        )
        if not path:
            log.warning(f"Cloudflare Worker falhou ({info}), tentando OpenRouter...")

    if not path:
        path, info = await asyncio.get_event_loop().run_in_executor(
            None, _gerar_openrouter, prompt, modelo_key, aspect
        )

    if not path:
        await ctx.reply(info or "não consegui gerar a imagem agora")
        return

    if overlay_text:
        _apply_overlay(path, overlay_text)

    try:
        caption = f"🎨 {raw[:80]}" + (f"\n_{overlay_text}_" if overlay_text else "")
        await ctx.reply_media(path, caption=caption)
    finally:
        try:
            os.unlink(path)
        except FileNotFoundError:
            pass


SKILL = Skill(
    name="img_gerar",
    description="Gera imagem com IA a partir de um prompt — use quando pedir pra criar, gerar, desenhar ou ilustrar algo.",
    triggers=[
        "!img", "gera imagem", "gerar imagem", "cria imagem", "criar imagem",
        "desenha", "desenhe", "ilustra", "ilustre", "faz uma imagem",
    ],
    handler=handle,
    category="midia",
    priority=120,
)
