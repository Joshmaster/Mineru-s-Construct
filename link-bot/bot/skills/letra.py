"""Skill: letra de música - via lyrics.ovh (gratuita, sem key)."""

import re
import httpx
from bot.core.router import Skill
from bot.core.context import MessageContext


async def handle(ctx: MessageContext):
    args = ctx.args_text.strip()
    if not args:
        await ctx.reply(
            "Qual música, parceiro? 🎵\n"
            "_Ex: 'letra Imagine - John Lennon'_\n"
            "_Ex: 'letra Bohemian Rhapsody Queen'_"
        )
        return

    # Tenta separar artista e título: "titulo - artista" ou "titulo de artista"
    artist = None
    title = None

    if " - " in args:
        parts = args.split(" - ", 1)
        title = parts[0].strip()
        artist = parts[1].strip()
    elif " de " in args.lower():
        parts = re.split(r"\s+de\s+", args, flags=re.IGNORECASE, maxsplit=1)
        title = parts[0].strip()
        artist = parts[1].strip()
    elif " da " in args.lower():
        parts = re.split(r"\s+da\s+", args, flags=re.IGNORECASE, maxsplit=1)
        title = parts[0].strip()
        artist = parts[1].strip()
    elif " do " in args.lower():
        parts = re.split(r"\s+do\s+", args, flags=re.IGNORECASE, maxsplit=1)
        title = parts[0].strip()
        artist = parts[1].strip()
    else:
        # tenta dividir pelas palavras: últimas 1-2 palavras = artista
        words = args.split()
        if len(words) >= 2:
            # heurística: artista costuma ser 1-2 palavras
            title = " ".join(words[:-2])
            artist = " ".join(words[-2:])
            if not title:  # 1 ou 2 palavras só
                title = " ".join(words[:1])
                artist = " ".join(words[1:])
        else:
            await ctx.reply(
                "Preciso de música E artista, parceiro 🎵\n"
                "_Tenta: 'letra Imagine - John Lennon'_"
            )
            return

    if not artist or not title:
        await ctx.reply("Não entendi música/artista 🌀")
        return

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.get(
                f"https://api.lyrics.ovh/v1/{artist}/{title}"
            )
            if r.status_code == 404:
                await ctx.reply(
                    f"🎵 Não achei a letra de '{title}' do {artist}.\n"
                    "Confere se o nome tá certinho?"
                )
                return
            if r.status_code != 200:
                await ctx.reply("O bardo emudeceu 🌀")
                return
            data = r.json()
    except Exception as e:
        await ctx.reply(f"O portal travou: {e}")
        return

    lyrics = (data.get("lyrics") or "").strip()
    if not lyrics:
        await ctx.reply(f"🎵 Não achei a letra dessa.")
        return

    # WhatsApp tem limite por mensagem (~4000 chars)
    # Se for grande, manda em pedaços
    header = f"🎵 *{title}* — {artist}\n─────────────────\n\n"

    if len(lyrics) > 3500:
        # Trunca + avisa
        truncated = lyrics[:3500].rsplit("\n", 1)[0]
        await ctx.reply(header + truncated +
                        "\n\n_[letra muito longa, mostrei só o começo]_")
    else:
        await ctx.reply(header + lyrics)


SKILL = Skill(
    name="letra",
    description="*letra <música> - <artista>* — bardo de Hyrule",
    triggers=["letra", "letra de", "lyrics"],
    handler=handle,
    category="util",
)
