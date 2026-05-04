"""Skill: citação épica - frases temáticas TOTK aleatórias."""

import secrets
from bot.core.router import Skill
from bot.core.context import MessageContext


CITACOES = [
    "⚔️ _\"It's dangerous to go alone! Take this.\"_\n— Velho da caverna",
    "🗡️ _\"The Master Sword chose me. I just had to be worthy.\"_\n— Link",
    "🔱 _\"Courage need not be remembered, for it is never forgotten.\"_\n— Princesa Zelda",
    "🌿 _\"Hyrule sempre encontra o herói que precisa.\"_\n— Sabedoria antiga",
    "🏰 _\"You must defeat Ganon!\"_\n— Eco em todos os Sages",
    "⚡ _\"A coragem nunca dorme. Só descansa entre batalhas.\"_\n— Link",
    "🛡️ _\"Mesmo a Master Sword precisa ser reparada às vezes.\"_\n— Korok do bosque",
    "🌀 _\"Os Korok seeds não são prêmio. São o caminho de volta pra casa.\"_\n— Hestu",
    "📜 _\"Cada shrine ensina algo que nenhuma batalha ensina.\"_\n— Monge ancião",
    "🔥 _\"The Demon King returns. But so does the hero.\"_\n— Profecia Sheikah",
    "🌊 _\"O Templo da Água não é sobre nadar. É sobre fluir com as correntes.\"_\n— Sage do Vento",
    "⛰️ _\"Sobe a montanha. Não pelo cume — pela jornada.\"_\n— Goron das Death Mountain",
    "🗺️ _\"Mapa não é território. Mas sem ele, você se perde.\"_\n— Cartógrafo de Hateno",
    "🦅 _\"Salta. O paraglider sempre abre a tempo, se você tem stamina.\"_\n— Lição da torre Skyview",
    "🌙 _\"As Depths são escuras só pra quem chega sem Lightroot.\"_\n— Yunobo",
    "💎 _\"Um Korok seed achado é uma promessa cumprida.\"_\n— Hestu, dançando",
    "⚔️ _\"Ganondorf voltou. Mas você também voltou. Empate? Não. Vitória.\"_\n— Rauru",
    "🎯 _\"Foco no inimigo, não na espada.\"_\n— Mestre da escola Yiga (sim, eles ensinam bem)",
    "🌳 _\"A Great Deku Tree não fala por enigma. Fala por paciência.\"_\n— Folha solta",
    "🐉 _\"Os dragões não te perseguem. Eles te esperam.\"_\n— Sábio do Templo do Tempo",
]


async def handle(ctx: MessageContext):
    citacao = secrets.choice(CITACOES)
    await ctx.reply(citacao)


SKILL = Skill(
    name="citacao",
    description="*frase épica* / *citação* — sabedoria de Hyrule",
    triggers=[
        "frase epica", "frase épica", "citacao", "citação",
        "fala uma frase", "frase do dia", "fala epica", "fala épica",
        "diga algo epico", "sabedoria",
    ],
    handler=handle,
    category="totk",
)
