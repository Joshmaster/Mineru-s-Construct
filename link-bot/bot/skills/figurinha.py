"""Skill: figurinha - cria sticker WhatsApp a partir de imagem/vídeo anexo."""

import os
import tempfile
from pathlib import Path
from bot.core.router import Skill
from bot.core.context import MessageContext
from bot.core.sticker import (
    has_ffmpeg, make_static_sticker, make_animated_sticker
)


def _fit_mode(ctx: MessageContext) -> str:
    text = f"{ctx.raw_text} {ctx.args_text}".lower()
    keep_full = (
        "inteira",
        "sem cortar",
        "sem crop",
        "não corta",
        "nao corta",
        "com borda",
    )
    return "contain" if any(term in text for term in keep_full) else "cover"


async def handle(ctx: MessageContext):
    if not has_ffmpeg():
        await ctx.reply(
            "🔥 A forja tá apagada, parceiro — preciso do FFmpeg instalado.\n"
            "_Windows: `winget install Gyan.FFmpeg`_\n"
            "_Termux: `pkg install ffmpeg`_\n"
            "_Linux: `apt install ffmpeg`_"
        )
        return

    if not ctx.has_media or not ctx.media_path:
        await ctx.reply(
            "Manda a imagem ou vídeo junto, parceiro 🎨\n"
            "_Tipo: foto + legenda 'figurinha'_"
        )
        return

    if not os.path.exists(ctx.media_path):
        await ctx.reply("A imagem se perdeu pelo caminho 🌀")
        return

    media_type = (ctx.media_type or "").lower()

    # Decide entre estática ou animada
    is_video = media_type in ("video", "gif") or ctx.media_path.lower().endswith(
        (".mp4", ".gif", ".webm", ".mov")
    )

    out_path = str(Path(tempfile.gettempdir()) / "link_sticker.webp")
    fit = _fit_mode(ctx)

    await ctx.reply("🗡️ Forjando uma runa Sheikah... aguarda os engenhos.")

    try:
        if is_video:
            ok, msg = await make_animated_sticker(
                ctx.media_path, out_path,
                max_duration=6.0, max_size_kb=500, fit=fit
            )
        else:
            ok, msg = await make_static_sticker(
                ctx.media_path, out_path, max_size_kb=100, fit=fit
            )
    except Exception as e:
        await ctx.reply(f"⚡ A forja explodiu: {e}")
        return

    if not ok:
        await ctx.reply(
            f"🌀 Não consegui forjar essa runa: {msg}\n"
            f"Tenta com uma imagem/vídeo menor."
        )
        return

    try:
        await ctx.reply_media(out_path, as_sticker=True)
    except Exception as e:
        # fallback: envia como mídia normal
        await ctx.reply(f"⚠️ Forjada mas não consegui enviar como sticker: {e}")
        try:
            await ctx.reply_media(out_path, as_sticker=False)
        except Exception:
            pass


SKILL = Skill(
    name="figurinha",
    description="*figurinha* / *vira sticker* — forjar runa Sheikah (envie mídia)",
    triggers=[
        "!fig", "!sticker", "!figurinha",
        "figurinha", "figurinhas", "sticker", "vira sticker",
        "vira figurinha", "stickers",
    ],
    handler=handle,
    category="midia",
    requires_media=True,
)
