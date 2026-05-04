"""Skill: lembretes - criar, listar, cancelar.

Detecta sub-ação pela trigger:
- 'me lembra X de Y' / 'lembra que Y' / 'agenda X' → criar
- 'meus lembretes' / 'lista lembretes' → listar
- 'cancela lembrete N' / 'apaga lembrete N' → cancelar
"""

import re
import time as _time
from bot.core.router import Skill
from bot.core.context import MessageContext
from bot.core.timeparse import (
    parse_time_expression, format_timestamp, humanize_recurrence
)


async def _criar(ctx: MessageContext, args: str):
    """Cria um lembrete. args contém tempo + texto, ex: 'daqui 30min de tomar agua'."""
    if not args.strip():
        await ctx.reply(
            "Marca o pergaminho como, parceiro? 📜\n"
            "_Ex: me lembra daqui 30 minutos de beber agua_\n"
            "_Ex: me lembra todo dia 22h do remedio_"
        )
        return

    parsed = parse_time_expression(args)
    if parsed is None:
        await ctx.reply(
            "Não entendi quando 🌀. Tenta assim:\n"
            "_'daqui 30 minutos'_ / _'amanhã às 8'_ / _'todo dia 22h'_"
        )
        return

    trigger_at, recurrence = parsed

    # Extrai texto do lembrete: tira expressões de tempo conhecidas
    text = args
    # remove padrões de tempo
    patterns = [
        r"daqui\s+\d+\s*(?:min|minutos?|h|horas?|dias?)",
        r"em\s+\d+\s*(?:min|minutos?|h|horas?)",
        r"todo\s+dia",
        r"todos\s+os\s+dias",
        r"diariamente",
        r"toda\s+(?:segunda|terca|terça|quarta|quinta|sexta|sabado|sábado|domingo)",
        r"amanha",
        r"amanhã",
        r"hoje",
        r"\d{1,2}[h:]\d{2}",
        r"\d{1,2}\s*h(?:oras?)?",
        r"as?\s+\d{1,2}",
        r"^de\s+",
        r"^que\s+",
    ]
    for p in patterns:
        text = re.sub(p, "", text, flags=re.IGNORECASE)
    text = re.sub(r"\s+", " ", text).strip(" ,.")
    text = text.strip()

    if not text:
        text = "(sem descrição)"

    sender = str(ctx.sender_jid).split("@")[0]
    rid = ctx.storage.reminder_add(sender, text, trigger_at, recurrence)

    quando = format_timestamp(trigger_at)
    extra = f"\n📜 Recorrente: {humanize_recurrence(recurrence)}" if recurrence else ""

    await ctx.reply(
        f"📜 Pergaminho marcado, parceiro!\n"
        f"⏰ {quando}\n"
        f"⚔️ {text}\n"
        f"#{rid}{extra}"
    )


async def _listar(ctx: MessageContext):
    sender = str(ctx.sender_jid).split("@")[0]
    items = ctx.storage.reminder_list(sender)

    if not items:
        await ctx.reply("Nenhum pergaminho marcado, aventureiro. 🌀")
        return

    lines = ["📜 *Pergaminhos do Tempo* 📜", "─────────────────"]
    for r in items[:20]:
        quando = format_timestamp(r["trigger_at"])
        rec = ""
        if r["recurrence"]:
            rec = f" 🔁 {humanize_recurrence(r['recurrence'])}"
        lines.append(f"#{r['id']} • {quando}{rec}\n   ⚔️ {r['text']}")

    if len(items) > 20:
        lines.append(f"\n... e mais {len(items) - 20} pergaminhos.")

    lines.append("\n_Pra cancelar: 'cancela lembrete 5'_")
    await ctx.reply("\n".join(lines))


async def _cancelar(ctx: MessageContext, args: str):
    sender = str(ctx.sender_jid).split("@")[0]
    m = re.search(r"\d+", args)
    if not m:
        await ctx.reply(
            "Qual pergaminho destruir, parceiro? 🔥\n"
            "_Ex: 'cancela lembrete 5'_\n"
            "_Lista todos com: 'meus lembretes'_"
        )
        return

    rid = int(m.group(0))
    if ctx.storage.reminder_delete(sender, rid):
        await ctx.reply(f"🔥 Pergaminho #{rid} destruído. Sumiu da agenda.")
    else:
        await ctx.reply(f"🌀 Não achei pergaminho #{rid} pra destruir.")


# ============ Handlers de cada trigger ============

async def handle_criar(ctx: MessageContext):
    await _criar(ctx, ctx.args_text)


async def handle_listar(ctx: MessageContext):
    await _listar(ctx)


async def handle_cancelar(ctx: MessageContext):
    await _cancelar(ctx, ctx.args_text)


# Exporta múltiplas skills (uma por ação)
SKILLS = [
    Skill(
        name="lembrete_criar",
        description="*me lembra <quando> de <o que>* — marcar pergaminho",
        triggers=["!lembra", "me lembra", "lembra de", "lembrar", "agenda", "agendar"],
        handler=handle_criar,
        category="lembretes",
        priority=5,
    ),
    Skill(
        name="lembrete_listar",
        description="*meus lembretes* — listar pergaminhos ativos",
        triggers=[
            "meus lembretes", "lista lembretes", "lembretes ativos",
            "ver lembretes", "pergaminhos ativos", "meus pergaminhos",
        ],
        handler=handle_listar,
        category="lembretes",
        priority=8,  # maior pra ganhar de "lembra"
    ),
    Skill(
        name="lembrete_cancelar",
        description="*cancela lembrete N* — destruir pergaminho",
        triggers=[
            "cancela lembrete", "cancelar lembrete", "apaga lembrete",
            "apagar lembrete", "destroi lembrete", "remove lembrete",
        ],
        handler=handle_cancelar,
        category="lembretes",
        priority=9,
    ),
]


# Compatibilidade: skill loader procura SKILL ou SKILLS
SKILL = SKILLS
