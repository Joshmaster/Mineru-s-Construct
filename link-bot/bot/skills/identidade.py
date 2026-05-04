"""Skill: 'quem é você' / 'se apresenta' - identidade do Link."""

import random
from bot.core.router import Skill
from bot.core.context import MessageContext


APRESENTACOES = [
    "Sou Link 🗡️ — herói de Hyrule, atravessei Sky Islands, mergulhei nas "
    "Depths e despertei os Sages. Aqui no zap, sou seu aliado, parceiro. "
    "Manda *ajuda* pra ver o que posso fazer. ⚔️",

    "Link, ao seu serviço 🛡️. Se sobrevivi a Ganondorf no coração de Hyrule "
    "Castle, sobrevivo aos seus desafios do dia. Me chama com *ajuda* "
    "que mostro o pergaminho de comandos. 🔱",

    "Eu? Link de Hyrule. ⚔️ Mesmo guerreiro que ergueu a Master Sword, agora "
    "no seu bolso pelo zap. Manda *menu* que te mostro como te ajudo. 📜",
]


async def handle(ctx: MessageContext):
    await ctx.reply(random.choice(APRESENTACOES))


SKILL = Skill(
    name="identidade",
    description="*quem é você* / *se apresenta* — Link se apresenta",
    triggers=[
        "quem e voce", "quem voce e", "se apresenta", "sua identidade",
        "como te chama", "qual seu nome", "quem es tu",
    ],
    handler=handle,
    category="essencial",
    priority=8,
)
