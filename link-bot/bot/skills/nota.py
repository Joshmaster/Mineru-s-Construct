"""Skill: notas pessoais - registrar, buscar, apagar."""

import re
from bot.core.router import Skill
from bot.core.context import MessageContext


async def handle_add(ctx: MessageContext):
    text = ctx.args_text.strip()
    text = re.sub(r"^(?:que|de|para|pra)\s+", "", text)
    text = text.strip(" :,.")

    if not text:
        await ctx.reply(
            "O que anotar, parceiro? 🗒️\n"
            "_Ex: 'anota: senha do wifi é xyz'_\n"
            "_Ex: 'lembrete que o Pedro casa em julho'_"
        )
        return

    # Extrai tags com #hashtag
    tags = " ".join(re.findall(r"#(\w+)", text))

    sender = str(ctx.sender_jid).split("@")[0]
    nid = ctx.storage.note_add(sender, text, tags)
    tag_str = f" 🏷️ {tags}" if tags else ""
    await ctx.reply(f"🗒️ Anotado no pergaminho!\n#{nid} • {text[:80]}{tag_str}")


async def handle_search(ctx: MessageContext):
    sender = str(ctx.sender_jid).split("@")[0]
    query = ctx.args_text.strip()
    # Limpa palavra "sobre"
    query = re.sub(r"^sobre\s+", "", query, flags=re.IGNORECASE).strip()

    items = ctx.storage.note_search(sender, query, limit=15)

    if not items:
        if query:
            await ctx.reply(f"🌀 Nada anotado sobre '{query}'.")
        else:
            await ctx.reply("📜 Nenhuma anotação no diário ainda.")
        return

    title = f"🗒️ *Anotações* (sobre '{query}')" if query else "🗒️ *Anotações*"
    lines = [title, "─────────────────"]
    for n in items:
        content = n["content"][:120]
        if len(n["content"]) > 120:
            content += "..."
        lines.append(f"#{n['id']} • {content}")

    await ctx.reply("\n".join(lines))


async def handle_remove(ctx: MessageContext):
    args = ctx.args_text.strip()
    sender = str(ctx.sender_jid).split("@")[0]

    m = re.search(r"\d+", args)
    if not m:
        await ctx.reply(
            "Qual anotação apagar? 🔥\n"
            "_Ex: 'apaga anotacao 5'_"
        )
        return

    nid = int(m.group(0))
    if ctx.storage.note_delete(sender, nid):
        await ctx.reply(f"🔥 Anotação #{nid} apagada do diário.")
    else:
        await ctx.reply(f"🌀 Não achei anotação #{nid}.")


SKILLS = [
    Skill(
        name="nota_add",
        description="*anota: <conteúdo>* — registrar no diário",
        triggers=["!nota", "anota", "anotar", "anotacao", "anotação", "lembrete que",
                  "registra"],
        handler=handle_add,
        category="memoria",
    ),
    Skill(
        name="nota_search",
        description="*minhas anotações* / *anotações sobre X* — buscar",
        triggers=[
            "minhas anotacoes", "minhas anotações",
            "anotacoes sobre", "anotações sobre",
            "lista anotacoes", "lista anotações",
            "ver anotacoes", "ver anotações",
        ],
        handler=handle_search,
        category="memoria",
        priority=10,
    ),
    Skill(
        name="nota_remove",
        description="*apaga anotação N* — destruir registro",
        triggers=[
            "apaga anotacao", "apagar anotacao",
            "apaga anotação", "apagar anotação",
            "remove anotacao", "remove anotação",
        ],
        handler=handle_remove,
        category="memoria",
        priority=9,
    ),
]


SKILL = SKILLS
