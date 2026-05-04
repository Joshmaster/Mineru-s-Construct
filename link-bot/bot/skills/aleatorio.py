"""Skill: dados, sorteio, moeda, senha aleatória."""

import re
import secrets
import random
from bot.core.router import Skill
from bot.core.context import MessageContext


async def handle_dados(ctx: MessageContext):
    args = ctx.args_text.lower().strip()

    # Detecta dXX (d6, d20, d100)
    m = re.search(r"d(\d+)", args)
    n_dados = 1
    n_lados = 6 if not m else int(m.group(1))

    # Detecta "X dados"
    m2 = re.search(r"(\d+)\s*d", args)
    if m2:
        n_dados = min(int(m2.group(1)), 20)  # max 20 dados

    if n_lados < 2 or n_lados > 1000:
        n_lados = 6

    rolls = [secrets.randbelow(n_lados) + 1 for _ in range(n_dados)]
    total = sum(rolls)

    if n_dados == 1:
        msg = f"🎲 d{n_lados}: *{rolls[0]}*"
    else:
        msg = f"🎲 {n_dados}d{n_lados}: {rolls} = *{total}*"

    # Crítico/falha pra d20
    if n_dados == 1 and n_lados == 20:
        if rolls[0] == 20:
            msg += "\n⚔️ *CRÍTICO!* A Master Sword brilha!"
        elif rolls[0] == 1:
            msg += "\n💀 *FALHA CRÍTICA!* Tropeçou no Bokoblin..."

    await ctx.reply(msg)


async def handle_moeda(ctx: MessageContext):
    result = secrets.choice(["Cara 👑", "Coroa 🪙"])
    await ctx.reply(f"🪙 Joguei a moeda... *{result}*")


async def handle_sortear(ctx: MessageContext):
    args = ctx.args_text.strip()
    if not args:
        await ctx.reply(
            "Sortear o quê, parceiro? 🎲\n"
            "_Ex: 'sorteia entre pizza, sushi, lasanha'_"
        )
        return

    # Remove "entre" se tiver
    args = re.sub(r"^\s*entre\s+", "", args, flags=re.IGNORECASE)

    # Separa por vírgula, "ou", "/"
    options = re.split(r",|\s+ou\s+|/", args)
    options = [o.strip() for o in options if o.strip()]

    if len(options) < 2:
        await ctx.reply(
            "Preciso de pelo menos 2 opções, parceiro 🎲\n"
            "_Ex: 'sorteia entre A, B, C'_"
        )
        return

    chosen = secrets.choice(options)
    await ctx.reply(f"🎲 As Sages decidiram: *{chosen}* ⚔️")


async def handle_senha(ctx: MessageContext):
    args = ctx.args_text.lower().strip()

    # Tamanho default 16, customizável
    m = re.search(r"\d+", args)
    length = int(m.group(0)) if m else 16
    length = max(8, min(length, 64))  # entre 8 e 64

    incluir_simbolos = "simples" not in args and "sem simbolo" not in args

    chars = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
    if incluir_simbolos:
        chars += "!@#$%^&*()-_=+[]{}"

    pwd = "".join(secrets.choice(chars) for _ in range(length))

    msg = (
        f"🔐 *Senha forjada nas Depths*\n"
        f"─────────────────\n"
        f"`{pwd}`\n"
        f"_({length} chars{'+ simbolos' if incluir_simbolos else ', simples'})_\n\n"
        f"⚠️ Apaga essa msg depois de salvar!"
    )
    await ctx.reply(msg)


SKILLS = [
    Skill(
        name="dados",
        description="*joga dado* / *d20* — runa de aleatoriedade",
        triggers=["joga dado", "rola dado", "rolar dado", "dado", "d20",
                  "d6", "d100", "rolar"],
        handler=handle_dados,
        category="util",
    ),
    Skill(
        name="moeda",
        description="*cara ou coroa* — runa da moeda",
        triggers=["cara ou coroa", "moeda", "joga moeda", "lança moeda"],
        handler=handle_moeda,
        category="util",
        priority=8,
    ),
    Skill(
        name="sortear",
        description="*sorteia entre A, B, C* — Sages decidem",
        triggers=["sorteia", "sortear", "escolhe", "decide entre"],
        handler=handle_sortear,
        category="util",
    ),
    Skill(
        name="senha",
        description="*gera senha* — forjar senha das Depths",
        triggers=["gera senha", "gerar senha", "senha aleatoria",
                  "senha forte", "password"],
        handler=handle_senha,
        category="util",
    ),
]


SKILL = SKILLS
