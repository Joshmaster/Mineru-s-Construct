"""Skill: encaminhar midia recebida no WhatsApp para DM no Discord."""

import json
import os
import urllib.error
import urllib.request
from pathlib import Path

from bot.core.context import MessageContext
from bot.core.router import Skill


DISCORD_API = "http://localhost:7331/send-file"


def _target_from_text(text: str) -> str:
    t = (text or "").lower()
    if any(x in t for x in ("manu", "ela", "namorada")):
        return "manu"
    return "josh"


def _kind_label(kind: str | None, path: str) -> str:
    kind = (kind or "").lower()
    if kind == "audio":
        return "audio"
    if kind == "image":
        return "imagem"
    if kind == "video":
        return "video"
    if kind == "sticker":
        return "figurinha"
    if kind == "document":
        return "arquivo"
    return Path(path).suffix.lstrip(".") or "arquivo"


def _send_discord_file(target: str, path: str, msg: str) -> dict:
    payload = json.dumps({"to": target, "file": path, "msg": msg}).encode("utf-8")
    req = urllib.request.Request(
        DISCORD_API,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            return json.loads(raw or "{}")
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", errors="replace")
        try:
            return json.loads(raw or "{}")
        except Exception:
            return {"ok": False, "error": raw or str(e)}
    except Exception as e:
        return {"ok": False, "error": str(e)}


async def handle(ctx: MessageContext):
    if not ctx.has_media or not ctx.media_path:
        await ctx.reply("manda a midia junto nessa mensagem, que eu passo pro Discord")
        return

    if not os.path.exists(ctx.media_path):
        await ctx.reply("a midia se perdeu no caminho. tenta mandar de novo")
        return

    target = _target_from_text(f"{ctx.raw_text} {ctx.args_text}")
    label = _kind_label(ctx.media_type, ctx.media_path)
    caption = f"{label} recebido pelo WhatsApp"

    result = _send_discord_file(target, ctx.media_path, caption)
    if result.get("ok"):
        await ctx.reply("mandei pro Discord")
        return

    await ctx.reply(f"nao consegui mandar pro Discord: {result.get('error') or result}")


SKILL = Skill(
    name="discord_forward",
    description="encaminhar audio, foto, video ou arquivo recebido no WhatsApp para DM no Discord",
    triggers=[
        "!discord",
        "!manda-discord",
        "manda pro discord",
        "envia pro discord",
        "passa pro discord",
        "manda no discord",
        "envia no discord",
        "manda esse audio",
        "manda esse áudio",
        "manda essa foto",
        "manda essa imagem",
        "manda esse video",
        "manda esse vídeo",
        "manda esse arquivo",
    ],
    handler=handle,
    category="midia",
    requires_media=True,
    priority=40,
)
