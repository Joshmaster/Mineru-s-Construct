"""Skill: menu de comandos estilo TOTK — com imagem e seções organizadas."""

import json
from pathlib import Path
from bot.core.router import Skill
from bot.core.context import MessageContext

CONFIG_PATH = Path(__file__).resolve().parents[2] / "config" / "config.json"
MENU_IMG    = Path(__file__).resolve().parents[2] / ".linkbot" / "menu.jpg"


def _is_owner(ctx: MessageContext) -> bool:
    try:
        cfg = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        sid = str(getattr(ctx.sender_jid, "User", "") or ctx.sender_jid)
        return sid == str(cfg.get("OWNER", ""))
    except Exception:
        return False


def _gerar_imagem():
    """Gera banner do menu via PIL se não existir."""
    try:
        from PIL import Image, ImageDraw, ImageFont
        import textwrap

        W, H = 800, 420
        BG       = (10, 10, 20)
        GOLD     = (212, 175, 55)
        TEAL     = (0, 200, 180)
        WHITE    = (240, 240, 240)
        DIM      = (100, 100, 110)

        img  = Image.new("RGB", (W, H), BG)
        draw = ImageDraw.Draw(img)

        # Borda dourada
        for t in range(3):
            draw.rectangle([t, t, W - 1 - t, H - 1 - t], outline=GOLD)

        # Triforce simples (triângulos)
        cx = W // 2
        def tri(draw, x, y, size, color):
            draw.polygon([(x, y - size), (x - size, y + size), (x + size, y + size)], fill=color)

        tri(draw, cx,      38, 18, GOLD)
        tri(draw, cx - 22, 70, 18, GOLD)
        tri(draw, cx + 22, 70, 18, GOLD)

        # Título
        try:
            font_big   = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 36)
            font_med   = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 18)
            font_small = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 14)
        except Exception:
            font_big = font_med = font_small = ImageFont.load_default()

        draw.text((cx, 105), "⚔  LINK  ⚔", font=font_big, fill=GOLD, anchor="mm")
        draw.text((cx, 145), "Herói de Hyrule · Seu assistente no zap", font=font_small, fill=DIM, anchor="mm")

        # Linha divisória
        draw.line([(60, 165), (W - 60, 165)], fill=GOLD, width=1)

        # Colunas de comandos
        col1 = [
            ("⏰ Lembretes",  TEAL),
            ("  !lembra daqui 30min de X", WHITE),
            ("  !lembra todo dia 22h de X", WHITE),
            ("  meus lembretes", WHITE),
            ("", None),
            ("🗺️ Consultas",  TEAL),
            ("  !clima Porto Alegre", WHITE),
            ("  !cotacao dólar / bitcoin", WHITE),
            ("  !cep 01310100", WHITE),
            ("  !hora Tóquio", WHITE),
            ("  !news · !news tecnologia", WHITE),
            ("", None),
            ("📜 Diário",  TEAL),
            ("  adiciona <missão> na lista", WHITE),
            ("  minhas tarefas · feito 2", WHITE),
            ("  anota: <texto>", WHITE),
        ]
        col2 = [
            ("🎨 Forja",  TEAL),
            ("  !fig  (envia imagem junto)", WHITE),
            ("  guarda no baú", WHITE),
            ("  meu baú", WHITE),
            ("", None),
            ("🧰 Relíquias",  TEAL),
            ("  !calc 150 * 38", WHITE),
            ("  converte 10km em milhas", WHITE),
            ("  !trad pra inglês: oi", WHITE),
            ("  !letra Imagine - Beatles", WHITE),
            ("  !url <link> · !qr <texto>", WHITE),
            ("  joga dado · d20", WHITE),
            ("", None),
            ("💻 Zonai",  TEAL),
            ("  cpu · ram · tira print", WHITE),
            ("  abre spotify · volume 50", WHITE),
        ]

        y0 = 180
        dy = 14
        x1, x2 = 60, W // 2 + 10

        for i, (txt, color) in enumerate(col1):
            if color:
                draw.text((x1, y0 + i * dy), txt, font=font_small if color == WHITE else font_med, fill=color)
        for i, (txt, color) in enumerate(col2):
            if color:
                draw.text((x2, y0 + i * dy), txt, font=font_small if color == WHITE else font_med, fill=color)

        # Rodapé
        draw.line([(60, H - 40), (W - 60, H - 40)], fill=GOLD, width=1)
        draw.text((cx, H - 22), "Fala natural também funciona  ·  ex: 'clima em SP'", font=font_small, fill=DIM, anchor="mm")

        MENU_IMG.parent.mkdir(parents=True, exist_ok=True)
        img.save(str(MENU_IMG), "JPEG", quality=88)
        return True
    except Exception:
        return False


async def handle(ctx: MessageContext):
    owner = _is_owner(ctx)
    nome  = ctx.pushname or "aventureiro"

    # Cabeçalho com saudação personalizada
    header = (
        f"⚔️ *LINK — HERÓI DE HYRULE* ⚔️\n"
        f"_Olá, {nome}! Seu pergaminho de comandos:_\n"
        f"{'▬' * 18}"
    )

    secoes = [
        ("⏰", "*PERGAMINHOS DO TEMPO*", [
            "`!lembra` daqui 30min de X",
            "`!lembra` todo dia 22h de X",
            "`!lembra` toda segunda 9h de X",
            "meus lembretes · cancela lembrete 3",
        ]),
        ("🗺️", "*CONSULTAR O REINO*", [
            "`!clima` Porto Alegre",
            "`!cotacao` dólar · euro · bitcoin",
            "`!cep` 01310100",
            "`!hora` Tóquio",
            "`!news` · `!news` tecnologia",
        ]),
        ("🎨", "*FORJA DE RUNAS*", [
            "`!fig`  _— envia a imagem junto_",
            "guarda no baú  _— envia a mídia_",
            "meu baú",
        ]),
        ("📜", "*DIÁRIO DO AVENTUREIRO*", [
            "adiciona <missão> na lista",
            "minhas tarefas · feito 2 · remove tarefa 2",
            "anota: <texto> · minhas anotações",
        ]),
        ("🧰", "*RELÍQUIAS DO HERÓI*", [
            "`!calc` 150 * 38",
            "converte 10km em milhas",
            "`!trad` pra inglês: bom dia",
            "`!letra` Imagine - John Lennon",
            "`!url` <link> · `!qr` <texto>",
            "joga dado · d20 · cara ou coroa",
            "sorteia entre A, B, C · gera senha 16",
        ]),
        ("🌿", "*ESPÍRITO DE HYRULE*", [
            "achei um korok! · quantos koroks",
            "frase épica · citação aleatória",
        ]),
        ("💻", "*ZONAI CONSTRUCTS*", [
            "abre spotify · volume 50 · tira print",
            "cpu · ram · info técnica",
        ]),
        ("⚙️", "*PURAH PAD — SISTEMA*", [
            "ping · `!status` · info técnica",
        ]),
    ]

    if owner:
        secoes.append(("🔱", "*TRIFORCE — ADMIN*", [
            "`!acesso` lista / add / del",
            "`!triforce` <pedido ao Claude>",
            "`!dono`",
        ]))

    linhas = [header, ""]
    for emoji, titulo, cmds in secoes:
        linhas.append(f"{emoji} {titulo}")
        for c in cmds:
            linhas.append(f"  ▸ {c}")
        linhas.append("")

    linhas += [
        f"{'▬' * 18}",
        "_Fala natural também funciona:_",
        "_↳ 'clima em Curitiba hoje?'_",
        "_↳ 'me lembra daqui 1h de beber água'_",
        "_↳ 'quanto é 200 dólares em reais?'_",
    ]

    texto = "\n".join(linhas)

    # Tenta enviar com imagem; gera se não existir
    if not MENU_IMG.exists():
        _gerar_imagem()

    if MENU_IMG.exists():
        await ctx.send_image(str(MENU_IMG), caption=texto)
    else:
        await ctx.reply(texto)


SKILL = Skill(
    name="ajuda",
    description="*!ajuda* / *menu* — pergaminho do aventureiro",
    triggers=["!ajuda", "ajuda", "menu", "comandos", "help", "?"],
    handler=handle,
    category="essencial",
    priority=10,
)
