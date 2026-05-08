"""Skill: !Z - conversa direta com o modelo local Ollama."""

import asyncio
import os
import re
import tempfile
import time
import urllib.request
from pathlib import Path

from bot.core.router import Skill
from bot.core.context import MessageContext
from bot.core import llm as _llm
from bot.core import access as access_ctl


def _norm(text: str) -> str:
    import unicodedata
    return "".join(
        c for c in unicodedata.normalize("NFD", text.lower())
        if unicodedata.category(c) != "Mn"
    )


def _quer_imagem(text: str) -> bool:
    p = _norm(text)
    return (
        any(x in p for x in ["imagem", "foto", "png", "jpg", "figura", "artwork", "arte", "ilustra"])
        and any(x in p for x in ["busca", "pesquis", "procura", "acha", "web", "internet", "online"])
    )


def _termo_imagem(text: str, usuario: str = "") -> str:
    query = _llm.extract_image_query(text, usuario)
    if query:
        return query
    m = re.search(r"(?:de|do|da|por|sobre)\s+(.+)$", text, re.IGNORECASE)
    termo = (m.group(1) if m else text).strip().strip('"')
    termo = re.sub(
        r"(?i)\b(busca|buscar|pesquisa|pesquisar|procura|procurar|acha|achar|"
        r"encontra|encontrar|pega|manda|envia|baixa|download|na|no|pela|pelo|"
        r"web|internet|google|uma|um|a|o|imagem|foto|figura|artwork|arte|png|jpg|jpeg)\b",
        " ",
        termo,
    )
    termo = " ".join(termo.strip(" \"'.,:;!?").split())
    if not termo or termo.lower() in {"sua", "seu", "voce", "você", "tu", "vc", "link", "dele"}:
        return "Link character portrait"
    return termo


def _baixar_imagem_tool(pedido: str, usuario: str = "") -> tuple[str, str] | None:
    import bot_supervisor as supervisor

    termo = _termo_imagem(pedido, usuario)
    url = supervisor.buscar_imagem(termo)
    if not url.startswith("http"):
        return None

    out = Path(tempfile.gettempdir()) / f"link_zpensa_{supervisor._normalizar(termo).replace(' ', '_')}_{time.time_ns()}.png"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=30) as r:
        data = r.read()
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
    pedido = (ctx.args_text or "").strip()
    if not pedido:
        await ctx.reply("manda o texto depois do !Z ou !zpensa")
        return

    raw_text = (getattr(ctx, "raw_text", "") or "").strip().lower()
    pensar = raw_text.startswith("!zpensa")
    await ctx.typing()
    sender_id = str(getattr(ctx.sender_jid, "User", "") or ctx.sender_jid)
    nome_usuario = access_ctl.display_name(ctx.sender_jid, ctx.chat_jid, sender_id, pushname=ctx.pushname)
    try:
        if _quer_imagem(pedido):
            img = await asyncio.get_event_loop().run_in_executor(None, _baixar_imagem_tool, pedido, nome_usuario)
            if img:
                caminho, termo = img
                try:
                    await ctx.reply_media(caminho, caption=termo)
                finally:
                    try:
                        os.unlink(caminho)
                    except FileNotFoundError:
                        pass
                return

        fn = _llm.chat_local_tools if pensar else _llm.chat_local
        args = (sender_id, pedido, nome_usuario) if pensar else (sender_id, pedido, nome_usuario, False)
        reply = await asyncio.get_event_loop().run_in_executor(None, fn, *args)
    except Exception as e:
        reply = f"não consegui falar com o local agora: {e}"
    await ctx.reply(reply)


SKILL = Skill(
    name="zlocal",
    description="*!Z <mensagem>* — local rápido; *!zpensa <mensagem>* — local com tools/thinking; também busca web/imagem quando pedido claramente",
    triggers=["!zpensa", "!z"],
    handler=handle,
    category="admin",
    priority=100,
)
