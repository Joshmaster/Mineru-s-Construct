"""Skill: !Z - conversa direta com o modelo local Ollama."""

import asyncio

from bot.core.router import Skill
from bot.core.context import MessageContext
from bot.core import llm as _llm


async def handle(ctx: MessageContext):
    pedido = (ctx.args_text or "").strip()
    if not pedido:
        await ctx.reply("manda o texto depois do !Z ou !zpensa")
        return

    raw_text = (getattr(ctx, "raw_text", "") or "").strip().lower()
    pensar = raw_text.startswith("!zpensa")
    await ctx.typing()
    sender_id = str(getattr(ctx.sender_jid, "User", "") or ctx.sender_jid)
    nome_usuario = ctx.pushname or "OWNER"
    try:
        reply = await asyncio.get_event_loop().run_in_executor(
            None, _llm.chat_local, sender_id, pedido, nome_usuario, pensar
        )
    except Exception as e:
        reply = f"não consegui falar com o local agora: {e}"
    await ctx.reply(reply)


SKILL = Skill(
    name="zlocal",
    description="*!Z <mensagem>* — local rápido; *!zpensa <mensagem>* — local com thinking",
    triggers=["!zpensa", "!z"],
    handler=handle,
    category="admin",
    priority=100,
)
