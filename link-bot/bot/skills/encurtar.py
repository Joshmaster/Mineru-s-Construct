"""Skill: encurtador de URL via is.gd (gratuita, sem key)."""

import re
import httpx
from bot.core.router import Skill
from bot.core.context import MessageContext


URL_REGEX = re.compile(r"https?://\S+")


async def handle(ctx: MessageContext):
    args = ctx.args_text.strip()

    m = URL_REGEX.search(args)
    if not m:
        await ctx.reply(
            "Manda a URL pra encurtar, parceiro 🔗\n"
            "_Ex: 'encurta https://exemplo.com.br/caminho/longo'_"
        )
        return

    url = m.group(0).rstrip(".,;)]")

    try:
        async with httpx.AsyncClient(timeout=10, follow_redirects=True) as client:
            r = await client.get(
                "https://is.gd/create.php",
                params={"format": "simple", "url": url}
            )
            if r.status_code != 200:
                await ctx.reply("O encurtador travou 🌀")
                return
            short = r.text.strip()
            if not short.startswith("http"):
                await ctx.reply(f"🌀 {short}")
                return
    except Exception as e:
        await ctx.reply(f"Portal travou: {e}")
        return

    msg = (
        f"🔗 *Pergaminho encurtado*\n"
        f"─────────────────\n"
        f"Original: _{url[:80]}{'...' if len(url) > 80 else ''}_\n"
        f"Curto: *{short}*"
    )
    await ctx.reply(msg)


SKILL = Skill(
    name="encurtar",
    description="*encurta <url>* — pergaminho compactado",
    triggers=["!url", "encurta", "encurtar", "shorten", "url curta"],
    handler=handle,
    category="util",
)
