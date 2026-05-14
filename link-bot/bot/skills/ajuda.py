"""Skill: menu de comandos estilo TOTK — com imagem e seções organizadas."""

import json
from pathlib import Path
from bot.core.router import Skill
from bot.core.context import MessageContext
from bot.core import access as access_ctl

CONFIG_PATH = Path(__file__).resolve().parents[2] / "config" / "config.json"
MENU_IMG    = Path(__file__).resolve().parents[3] / "assets" / "banner.jpg"


def _is_owner(ctx: MessageContext) -> bool:
    try:
        cfg = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        sid = str(getattr(ctx.sender_jid, "User", "") or ctx.sender_jid)
        return access_ctl.is_admin(ctx.sender_jid, ctx.chat_jid, sid, cfg=cfg)
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
            ("🎨 Mídia",  TEAL),
            ("  !yt  !spot  !ig  !img", WHITE),
            ("  !fala · !tt · !gif · !print", WHITE),
            ("  !fig  (envia imagem junto)", WHITE),
            ("", None),
            ("📜 Memória",  TEAL),
            ("  adiciona missão na lista", WHITE),
            ("  minhas tarefas · feito 2", WHITE),
            ("  anota: texto", WHITE),
            ("  minhas anotações", WHITE),
            ("", None),
            ("🔱 Dono",  TEAL),
            ("  menu admin", WHITE),
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
    admin_mode = ctx.args_text.strip().lower() in {"admin", "adm", "dono"}

    if admin_mode and not owner:
        await ctx.reply("🔒 Esse menu é só do dono.")
        return

    if admin_mode:
        header = (
            f"🔱 *MENU ADMIN — HYRULE*\n"
            f"_Comandos restritos ao dono:_\n"
            f"{'▬' * 18}"
        )
        secoes = [
            ("🔐", "*ACESSO*", [
                "`!acesso pendentes`",
                "`!acesso lista`",
                "`!acesso add [número/ID]`",
                "`!acesso del [número/ID]`",
                "`!acesso codigo [ID] [codigo]`",
            ]),
            ("⚔️", "*AGENTES*", [
                "`!triforce <pedido>`",
                "`!majora <pedido>`",
                "`!mastersword <pedido>`",
            ]),
            ("🖥️", "*PC*", [
                "abre <programa>",
                "volume 50",
                "tira print",
                "cpu · ram · info técnica",
            ]),
            ("🧭", "*SISTEMA*", [
                "`!dono`",
                "ping · status",
            ]),
        ]
    else:
        header = (
        f"⚔️ *LINK — HERÓI DE HYRULE* ⚔️\n"
        f"_Olá, {nome}! Seu pergaminho de comandos:_\n"
        f"{'▬' * 18}"
        )

        secoes = [
            ("⏰", "*LEMBRETES*", [
                "me lembra daqui 30min de X",
                "me lembra todo dia 22h de X",
                "meus lembretes · cancela lembrete 3",
            ]),
            ("🎨", "*MÍDIA*", [
                "!img <prompt>  _— gera imagem_",
                "!yt <link>  _— áudio YouTube_",
                "!spot <busca ou link>  _— baixar Spotify_",
                "!ig <link>  _— baixar Instagram_",
                "!fala <texto>  _— voz (TTS)_",
                "!tt <texto>  _— sticker com texto_",
                "!gif <busca>  _— GIF do Tenor_",
                "!print <url>  _— screenshot de site_",
                "!fig  _— sticker (envia mídia junto)_",
            ]),
            ("📜", "*MEMÓRIA*", [
                "adiciona <missão> na lista",
                "minhas tarefas · feito 2 · remove tarefa 2",
                "anota: <texto> · minhas anotações",
            ]),
            ("🌿", "*HYRULE*", [
                "achei um korok! · quantos koroks",
                "frase épica · citação aleatória",
            ]),
        ]
        if owner:
            secoes.append(("🔱", "*DONO*", [
                "`menu admin`",
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

    await ctx.reply(texto)

    if MENU_IMG.exists():
        await ctx.send_image(str(MENU_IMG))


SKILL = Skill(
    name="ajuda",
    description="*!ajuda* / *menu* — pergaminho do aventureiro",
    triggers=["!ajuda", "ajuda", "menu", "comandos", "help", "?"],
    handler=handle,
    category="essencial",
    priority=10,
)
