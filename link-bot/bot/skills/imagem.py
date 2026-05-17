"""Busca imagem na web e envia como mídia no WhatsApp."""

import asyncio
import os
import re
import tempfile
import time
import urllib.request
from pathlib import Path

from bot.core.context import MessageContext
from bot.core.router import Skill
from bot.core import llm as _llm


def _fallback_termo(text: str) -> str:
    termo = (text or "").strip()
    termo = re.sub(
        r"(?i)\b(busca|buscar|pesquisa|pesquisar|procura|procurar|acha|achar|"
        r"encontra|encontrar|pega|manda|envia|baixa|download|na|no|pela|pelo|"
        r"web|internet|google|uma|um|a|o|imagem|foto|figura|artwork|arte|png|jpg|jpeg)\b",
        " ",
        termo,
    )
    termo = re.sub(r"(?i)^(de|do|da|por|sobre)\s+", "", termo.strip())
    termo = re.sub(r"(?i)\s+e\s+(?:me\s+)?(?:manda|envia|enviar|mande|envie)\b.*$", " ", termo)
    termo = " ".join(termo.strip(" \"'.,:;!?").split())

    if not termo or termo.lower() in {"sua", "seu", "voce", "você", "tu", "vc", "link", "dele"}:
        return "Link character portrait"
    return termo


def _normalizar_termo(text: str, usuario: str = "") -> str:
    return _llm.extract_image_query(text, usuario) or _fallback_termo(text)


def _baixar_imagem(termo: str, usuario: str = "") -> tuple[str, str] | tuple[None, str]:
    import bot_supervisor as supervisor

    termo = _normalizar_termo(termo, usuario)
    url = supervisor.buscar_imagem(termo)
    if not url.startswith("http"):
        return None, url

    filename = f"link_imagem_{supervisor._normalizar(termo).replace(' ', '_')}_{time.time_ns()}.png"
    out = Path(tempfile.gettempdir()) / filename

    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = resp.read()

    try:
        from io import BytesIO
        from PIL import Image

        img = Image.open(BytesIO(data))
        if img.mode not in ("RGB", "RGBA"):
            img = img.convert("RGB")
        img.save(out, format="PNG")
    except Exception:
        out.write_bytes(data)
    return str(out), termo


async def handle(ctx: MessageContext):
    pedido = (ctx.args_text or ctx.raw_text or "").strip()
    if not pedido:
        await ctx.reply("qual imagem eu busco?")
        return

    await ctx.typing()
    path, info = await asyncio.get_event_loop().run_in_executor(None, _baixar_imagem, pedido, ctx.pushname or "")
    if not path:
        await ctx.reply(info)
        return
    try:
        await ctx.reply_media(path, caption=info)
    finally:
        try:
            os.unlink(path)
        except FileNotFoundError:
            pass


SKILL = Skill(
    name="imagem_buscar",
    description="buscar foto/imagem na web e enviar a imagem baixada no WhatsApp",
    triggers=[
        "!imagem", "!foto", "imagem", "imagens", "foto", "fotos",
        "busca imagem", "buscar imagem", "baixa imagem", "baixar imagem",
        "manda imagem", "manda foto", "procura imagem", "acha imagem",
    ],
    handler=handle,
    category="web",
    priority=120,
)
