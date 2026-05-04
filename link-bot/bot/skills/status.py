"""Skill: status / como vai - estado atual do bot e do reino."""

import time
import platform
from bot.core.router import Skill
from bot.core.context import MessageContext


_START_TIME = time.time()


def _format_uptime(seconds: float) -> str:
    s = int(seconds)
    days = s // 86400
    s %= 86400
    hours = s // 3600
    s %= 3600
    mins = s // 60
    parts = []
    if days:
        parts.append(f"{days}d")
    if hours:
        parts.append(f"{hours}h")
    if mins or not parts:
        parts.append(f"{mins}min")
    return " ".join(parts)


async def handle(ctx: MessageContext):
    uptime = _format_uptime(time.time() - _START_TIME)

    sender = str(ctx.sender_jid).split("@")[0] if ctx.sender_jid else "?"
    lembretes = ctx.storage.reminder_list(sender)
    todos_abertos = ctx.storage.todo_list(sender, include_done=False)
    koroks = ctx.storage.counter_get(sender, "koroks")

    skills_total = len(ctx.router.list_enabled())
    modo = ctx.config.get("MODE", "TOTK puro (sem LLM)")

    msg = (
        f"🌀 *Status do Reino* 🌀\n"
        f"─────────────────\n"
        f"⚔️ Modo: {modo}\n"
        f"🛡️ Em vigília há: {uptime}\n"
        f"📜 Skills ativas: {skills_total}\n"
        f"🖥️ Sistema: {platform.system()}\n"
        f"─────────────────\n"
        f"⏰ Pergaminhos ativos: {len(lembretes)}\n"
        f"📝 TODOs abertos: {len(todos_abertos)}\n"
        f"🌳 Korok seeds: {koroks}\n"
        f"\nTudo em ordem em Hyrule, parceiro. 🔱"
    )
    await ctx.reply(msg)


SKILL = Skill(
    name="status",
    description="*status* / *como vai* — estado do reino",
    triggers=["status", "como vai", "tudo bem", "como ta", "como esta"],
    handler=handle,
    category="essencial",
)
