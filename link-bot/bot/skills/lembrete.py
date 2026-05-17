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
from bot.core.reminder_art import (
    medication_schedule_caption,
    render_medication_schedule_card,
)
from bot.core.timeparse import (
    parse_time_expression, format_timestamp, humanize_recurrence
)


def _group_jid_from_config(ctx: MessageContext) -> str:
    """Retorna o JID do grupo de lembretes configurado, se houver."""
    cfg = getattr(ctx, 'config', None) or {}
    return str(cfg.get("REMINDERS_GROUP_JID", "") or "").strip()


async def _criar(ctx: MessageContext, args: str):
    """Cria um lembrete. args contém tempo + texto, ex: 'daqui 30min de tomar agua'."""
    # Detecta keyword 'grupo' para enviar ao grupo configurado
    send_to = ""
    args_clean = args.strip()
    grupo_match = re.match(r'^grupo\b\s*', args_clean, re.IGNORECASE)
    if grupo_match:
        args_clean = args_clean[grupo_match.end():]
        send_to = _group_jid_from_config(ctx)
        if not send_to:
            await ctx.reply(
                "grupo de lembretes não configurado 🌀\n"
                "Pede pro dono adicionar REMINDERS_GROUP_JID no config.json"
            )
            return

    if not args_clean:
        await ctx.reply(
            "Marca o pergaminho como, parceiro? 📜\n"
            "_Ex: me lembra daqui 30 minutos de beber agua_\n"
            "_Ex: me lembra grupo todo dia 22h do remedio_"
        )
        return

    parsed = parse_time_expression(args_clean)
    if parsed is None:
        await ctx.reply(
            "Não entendi quando 🌀. Tenta assim:\n"
            "_'daqui 30 minutos'_ / _'amanhã às 8'_ / _'todo dia 22h'_"
        )
        return

    trigger_at, recurrence = parsed

    text = args_clean
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
    rid = ctx.storage.reminder_add(sender, text, trigger_at, recurrence, send_to=send_to)

    quando = format_timestamp(trigger_at)
    extra = f"\n📜 Recorrente: {humanize_recurrence(recurrence)}" if recurrence else ""
    destino = f"\n📍 Grupo: {send_to}" if send_to else ""

    await ctx.reply(
        f"📜 Pergaminho marcado, parceiro!\n"
        f"⏰ {quando}\n"
        f"⚔️ {text}\n"
        f"#{rid}{extra}{destino}"
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


async def _card_remedios(ctx: MessageContext):
    sender = str(ctx.sender_jid).split("@")[0]
    reminders = [
        r for r in ctx.storage.reminder_list(sender)
        if r.get("recurrence")
    ]
    caption = medication_schedule_caption(reminders)
    if caption.strip() == "*Rotina de remédios*":
        await ctx.reply("não achei rotina de remédios ativa")
        return

    await ctx.typing()
    path = render_medication_schedule_card(reminders)
    await ctx.send_image(path, caption="Rotina de remédios")


# ============ Handlers de cada trigger ============

async def handle_criar(ctx: MessageContext):
    await _criar(ctx, ctx.args_text)


async def handle_listar(ctx: MessageContext):
    await _listar(ctx)


async def handle_cancelar(ctx: MessageContext):
    await _cancelar(ctx, ctx.args_text)


async def handle_card_remedios(ctx: MessageContext):
    await _card_remedios(ctx)


# Exporta múltiplas skills (uma por ação)
SKILLS = [
    Skill(
        name="remedios_card",
        description="*card dos remédios* — quadro com todos os horários",
        triggers=[
            "!remedios", "!remédios", "card remedios", "card remédios",
            "card dos remedios", "card dos remédios", "horarios dos remedios",
            "horários dos remédios", "rotina de remedios", "rotina de remédios",
            "todos os remedios", "todos os remédios", "horarios do remedio",
            "horários do remédio", "horario do remedio", "horário do remédio",
            "horarios remedio", "horários remédio", "remedio horarios",
            "remédio horários",
        ],
        handler=handle_card_remedios,
        category="lembretes",
        priority=12,
    ),
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
