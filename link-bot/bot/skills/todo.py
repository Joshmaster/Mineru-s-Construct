"""Skill: TODO list - lista de tarefas pessoais."""

import re
from bot.core.router import Skill
from bot.core.context import MessageContext


async def handle_add(ctx: MessageContext):
    text = ctx.args_text.strip()
    # Remove conectores residuais
    text = re.sub(r"^(?:que|de|para|pra)\s+", "", text)
    text = text.strip(" :,.")

    if not text:
        await ctx.reply(
            "O que adicionar à lista, parceiro? 📝\n"
            "_Ex: 'adiciona comprar pao na lista'_\n"
            "_Ex: 'preciso lavar o carro'_"
        )
        return

    sender = str(ctx.sender_jid).split("@")[0]
    tid = ctx.storage.todo_add(sender, text)
    await ctx.reply(f"📝 Anotado no diário, parceiro!\n#{tid} • {text}")


async def handle_list(ctx: MessageContext):
    sender = str(ctx.sender_jid).split("@")[0]
    items = ctx.storage.todo_list(sender, include_done=False)

    if not items:
        await ctx.reply(
            "🎯 Sem tarefas pendentes, aventureiro!\n"
            "Tudo em paz no reino. 🌿"
        )
        return

    lines = ["📝 *Diário de Missões* 📝", "─────────────────"]
    for t in items[:30]:
        lines.append(f"#{t['id']} • {t['text']}")

    if len(items) > 30:
        lines.append(f"\n_... e mais {len(items) - 30} missões_")

    lines.append(f"\n_Total: {len(items)} pendentes_")
    lines.append("_Marca feito: 'feito 5' / 'concluí 3'_")

    await ctx.reply("\n".join(lines))


async def handle_done(ctx: MessageContext):
    args = ctx.args_text.strip()
    sender = str(ctx.sender_jid).split("@")[0]

    m = re.search(r"\d+", args)
    if not m:
        await ctx.reply(
            "Qual missão concluída, parceiro? ⚔️\n"
            "_Ex: 'feito 5' / 'concluí 3'_"
        )
        return

    tid = int(m.group(0))
    if ctx.storage.todo_mark_done(sender, tid):
        await ctx.reply(f"⚔️ Missão #{tid} concluída! Bem feito, aventureiro. 🏆")
    else:
        await ctx.reply(f"🌀 Não achei missão #{tid}.")


async def handle_remove(ctx: MessageContext):
    args = ctx.args_text.strip()
    sender = str(ctx.sender_jid).split("@")[0]

    m = re.search(r"\d+", args)
    if not m:
        await ctx.reply(
            "Qual missão remover, parceiro? 🔥\n"
            "_Ex: 'remove tarefa 5'_"
        )
        return

    tid = int(m.group(0))
    if ctx.storage.todo_delete(sender, tid):
        await ctx.reply(f"🔥 Missão #{tid} apagada do diário.")
    else:
        await ctx.reply(f"🌀 Não achei missão #{tid}.")


SKILLS = [
    Skill(
        name="todo_add",
        description="*adiciona <tarefa> na lista* — anotar missão",
        triggers=[
            "!todo", "adiciona", "adicionar", "anota tarefa", "nova tarefa",
            "preciso", "tenho que",
        ],
        handler=handle_add,
        category="memoria",
    ),
    Skill(
        name="todo_list",
        description="*minhas tarefas* / *minha lista* — diário de missões",
        triggers=[
            "minhas tarefas", "minha lista", "lista de tarefas",
            "tarefas pendentes", "missoes ativas", "missões ativas",
            "diario de missoes", "diário de missões",
        ],
        handler=handle_list,
        category="memoria",
        priority=10,
    ),
    Skill(
        name="todo_done",
        description="*feito N* — marcar missão concluída",
        triggers=["feito", "concluí", "conclui", "completei", "terminei"],
        handler=handle_done,
        category="memoria",
    ),
    Skill(
        name="todo_remove",
        description="*remove tarefa N* — apagar missão",
        triggers=[
            "remove tarefa", "remover tarefa", "apaga tarefa",
            "apagar tarefa", "deletar tarefa",
        ],
        handler=handle_remove,
        category="memoria",
        priority=9,
    ),
]


SKILL = SKILLS
