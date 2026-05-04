"""Skill: korok seed - sistema de gamificação leve."""

import secrets
from bot.core.router import Skill
from bot.core.context import MessageContext


REACOES = [
    "🌳 *YA-HA-HA!* Mais um Korok seed pra coleção!",
    "🌿 Hestu vai dançar feliz com mais essa! 🎵",
    "🍃 Você tem olho de aventureiro de verdade, parceiro.",
    "🌳 Mais uma sementinha. Daqui a pouco a Hestu maraca encheu!",
    "🌿 *YA-HA-HA!* Korok escondido descoberto.",
    "🍂 Bem visto, OWNER. Os Koroks são craques em se esconder.",
]

MARCOS = {
    1: "🌱 Primeira semente! Bem-vindo à caça aos Koroks.",
    5: "🌿 5 Koroks! Hestu já te conhece.",
    10: "🌳 10 Koroks! Maraca de Hestu cresceu.",
    25: "🍃 25 Koroks! Tá virando profissional.",
    50: "🏆 50 Koroks! Hyrule ergue um brinde a você.",
    100: "🌟 100 KOROKS! HEROIC! Hestu dança em sua honra! 🎉",
    200: "👑 200 Koroks! Mestre dos Koroks de Hyrule. 🔱",
    500: "💎 500 Koroks! Lendário. Os Sages cantam seu nome.",
    900: "✨ 900 KOROKS! Você é insano, parceiro. Insano. 🤯",
}


async def handle_achei(ctx: MessageContext):
    sender = str(ctx.sender_jid).split("@")[0]
    novo_total = ctx.storage.counter_inc(sender, "koroks", 1)

    reacao = secrets.choice(REACOES)
    msg = f"{reacao}\n\n📊 Total de Koroks: *{novo_total}* 🌳"

    # Marco?
    if novo_total in MARCOS:
        msg += f"\n\n{MARCOS[novo_total]}"

    await ctx.reply(msg)


async def handle_quantos(ctx: MessageContext):
    sender = str(ctx.sender_jid).split("@")[0]
    total = ctx.storage.counter_get(sender, "koroks")

    if total == 0:
        await ctx.reply(
            "🌳 Você ainda não achou nenhum Korok, parceiro.\n"
            "_Quando achar um, manda 'achei um korok!' que eu marco._"
        )
        return

    msg = f"🌳 Você já encontrou *{total}* Korok seeds!"

    # Próximo marco
    proximos_marcos = sorted([k for k in MARCOS.keys() if k > total])
    if proximos_marcos:
        prox = proximos_marcos[0]
        falta = prox - total
        msg += f"\n🎯 Faltam *{falta}* pro próximo marco ({prox})."

    await ctx.reply(msg)


SKILLS = [
    Skill(
        name="korok_achei",
        description="*achei um korok!* — registrar Korok seed",
        triggers=[
            "achei um korok", "achei korok", "korok achado",
            "encontrei um korok", "encontrei korok",
        ],
        handler=handle_achei,
        category="totk",
        priority=8,
    ),
    Skill(
        name="korok_quantos",
        description="*quantos koroks tenho* — contagem de Korok seeds",
        triggers=[
            "quantos koroks", "meus koroks", "total de koroks",
            "quantos korok",
        ],
        handler=handle_quantos,
        category="totk",
        priority=9,
    ),
]


SKILL = SKILLS
