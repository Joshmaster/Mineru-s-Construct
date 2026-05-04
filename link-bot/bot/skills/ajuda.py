"""Skill: !ajuda - pergaminho de comandos estilo TOTK."""

import json
from pathlib import Path
from bot.core.router import Skill
from bot.core.context import MessageContext

CONFIG_PATH = Path(__file__).resolve().parents[2] / "config" / "config.json"


def _is_owner(ctx: MessageContext) -> bool:
    try:
        cfg = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        sid = str(getattr(ctx.sender_jid, "User", "") or ctx.sender_jid)
        return sid == str(cfg.get("OWNER", ""))
    except Exception:
        return False


async def handle(ctx: MessageContext):
    owner = _is_owner(ctx)

    linhas = [
        "⚔️ *LINK — HERÓI DE HYRULE* ⚔️",
        "_Pergaminho do Aventureiro · TOTK_",
        "▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬",
        "",
        "⏰ *PERGAMINHOS DO TEMPO*",
        "  ▸ *!lembra* daqui 30min de X",
        "  ▸ *!lembra* todo dia 22h de X",
        "  ▸ *!lembra* toda segunda 9h de X",
        "  ▸ meus lembretes",
        "  ▸ cancela lembrete 3",
        "",
        "🗺️ *CONSULTAR O REINO*",
        "  ▸ *!clima* Porto Alegre",
        "  ▸ *!cotacao* dólar · bitcoin",
        "  ▸ *!cep* 01310100",
        "  ▸ *!hora* Tóquio",
        "  ▸ *!news* · *!news* tecnologia",
        "",
        "🎨 *FORJA DE RUNAS*",
        "  ▸ *!fig* _— envia a imagem junto_",
        "  ▸ guarda no baú _— envia a mídia_",
        "  ▸ meu baú",
        "",
        "📜 *DIÁRIO DO AVENTUREIRO*",
        "  ▸ adiciona <missão> na lista",
        "  ▸ minhas tarefas · feito 2",
        "  ▸ remove tarefa 2",
        "  ▸ anota: <texto>",
        "  ▸ minhas anotações",
        "",
        "🧰 *RELÍQUIAS DO HERÓI*",
        "  ▸ *!calc* 150 * 38",
        "  ▸ converte 10km em milhas",
        "  ▸ *!trad* pra inglês: bom dia",
        "  ▸ *!letra* Imagine - John Lennon",
        "  ▸ *!url* https://... · *!qr* <texto>",
        "  ▸ joga dado · d20 · cara ou coroa",
        "  ▸ sorteia entre A, B, C",
        "  ▸ gera senha 16",
        "",
        "🌿 *ESPÍRITO DE HYRULE*",
        "  ▸ achei um korok! · quantos koroks",
        "  ▸ frase épica · citação",
        "",
        "💻 *ZONAI CONSTRUCTS*",
        "  ▸ abre spotify · cpu · ram",
        "  ▸ volume 50 · tira print",
        "",
        "⚙️ *PURAH PAD — SISTEMA*",
        "  ▸ ping · *!status* · info técnica",
    ]

    if owner:
        linhas += [
            "",
            "🔱 *TRIFORCE — ADMIN*",
            "  ▸ *!acesso* lista / add / del",
            "  ▸ *!triforce* <pedido ao Claude>",
            "  ▸ *!dono*",
        ]

    linhas += [
        "",
        "▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬",
        "_Fala natural também funciona:_",
        "_↳ 'clima em Curitiba?'_",
        "_↳ 'me lembra daqui 1h de beber água'_",
        "_↳ 'converte 100 dólares em reais'_",
    ]

    await ctx.reply("\n".join(linhas))


SKILL = Skill(
    name="ajuda",
    description="*!ajuda* / *menu* — pergaminho do aventureiro",
    triggers=["!ajuda", "ajuda", "menu", "comandos", "help", "?"],
    handler=handle,
    category="essencial",
    priority=10,
)
