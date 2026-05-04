"""Skill: bot management - ping, info, reload (avisa que precisa reiniciar)."""

import sys
import platform
from bot.core.router import Skill
from bot.core.context import MessageContext


async def handle_ping(ctx: MessageContext):
    await ctx.reply("⚔️ Pong! Tô vivo, parceiro. 🛡️")


async def handle_info(ctx: MessageContext):
    py_ver = sys.version.split()[0]
    sys_name = platform.system()
    sys_release = platform.release()

    skills = ctx.router.list_enabled()
    cats = ctx.router.list_by_category()

    lines = [
        "⚙️ *Info Técnica do Reino*",
        "─────────────────",
        f"🐍 Python: {py_ver}",
        f"🖥️ Sistema: {sys_name} {sys_release}",
        f"📦 Skills carregadas: {len(skills)}",
        f"📂 Categorias: {len(cats)}",
        "",
        "*Skills por categoria:*",
    ]
    for cat, items in cats.items():
        lines.append(f"  {cat}: {len(items)}")

    await ctx.reply("\n".join(lines))


async def handle_reload(ctx: MessageContext):
    await ctx.reply(
        "⚙️ Pra recarregar skills, parceiro, precisa reiniciar o bot:\n"
        "1. Ctrl+C no terminal\n"
        "2. Roda o launcher de novo\n\n"
        "_Hot-reload tá no roadmap pra próxima dungeon._"
    )


SKILLS = [
    Skill(
        name="ping",
        description="*ping* — testar se Link tá vivo",
        triggers=["ping", "ta vivo", "tá vivo", "ta ai", "tá aí"],
        handler=handle_ping,
        category="bot",
    ),
    Skill(
        name="info",
        description="*info* / *info técnica* — detalhes do sistema",
        triggers=["info tecnica", "info técnica", "info do bot", "bot info",
                  "info"],
        handler=handle_info,
        category="bot",
        priority=2,  # baixa porque "info" é palavra comum
    ),
    Skill(
        name="reload",
        description="*reload* — instruções pra recarregar skills",
        triggers=["reload", "recarrega", "recarregar"],
        handler=handle_reload,
        category="bot",
    ),
]


SKILL = SKILLS
