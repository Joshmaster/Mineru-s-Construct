"""Skill: TRIFORCE — linha direta com o Claude Code.

Triggers:
  !triforce <texto>   → encaminha o texto
  !triforce           → usa a última mensagem enviada pelo dono
  [TRIFORCE: texto]   → formato inline
"""

import json
import re
import time
from pathlib import Path
from bot.core.router import Skill
from bot.core.context import MessageContext

_AGENTS_DIR  = Path(__file__).resolve().parents[3]
CLAUDE_QUEUE = _AGENTS_DIR / "claude_queue.json"
CODEX_QUEUE  = _AGENTS_DIR / "codex_queue.json"
MASTERSWORD_QUEUE = _AGENTS_DIR / "mastersword_queue.json"
CONFIG_PATH  = _AGENTS_DIR / "link-bot" / "config" / "config.json"


def _is_owner(ctx: MessageContext) -> bool:
    try:
        cfg = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        sid = str(getattr(ctx.sender_jid, "User", "") or ctx.sender_jid)
        return sid == str(cfg.get("OWNER", ""))
    except Exception:
        return False


def _sender_id(ctx: MessageContext) -> str:
    return str(getattr(ctx.sender_jid, "User", "") or ctx.sender_jid)


def _ultimo_pedido_llm(sender_id: str) -> str:
    """Retorna a última mensagem do usuário no histórico LLM."""
    try:
        from bot.core import llm as _llm
        history = _llm._get_history(sender_id)
        for item in reversed(history):
            if item.get("role") == "user":
                return item.get("content", "").strip()
    except Exception:
        pass
    return ""


def _enfileirar(pedido: str, usuario: str, sender_id: str, canal: str = "whatsapp", fila_path: Path = None):
    if fila_path is None:
        fila_path = CLAUDE_QUEUE
    fila = []
    if fila_path.exists():
        try:
            fila = json.loads(fila_path.read_text(encoding="utf-8"))
        except Exception:
            fila = []
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    fila.append({
        "ts":        ts,
        "id":        f"{int(time.time())}_{usuario}",
        "pedido":    pedido,
        "usuario":   usuario,
        "sender_id": sender_id,
        "canal":     canal,
    })
    fila_path.write_text(json.dumps(fila, ensure_ascii=False, indent=2), encoding="utf-8")


async def handle_triforce(ctx: MessageContext):
    if not _is_owner(ctx):
        await ctx.reply("🔒 Só o dono pode acionar a TRIFORCE.")
        return

    sid = _sender_id(ctx)

    pedido = ctx.args_text.strip()
    if not pedido:
        m = re.search(r'\[TRIFORCE:\s*(.+?)\]', ctx.raw_text, re.IGNORECASE)
        if m:
            pedido = m.group(1).strip()

    if not pedido:
        pedido = _ultimo_pedido_llm(sid)

    if not pedido:
        await ctx.reply("Manda o que quer perguntar pro Claude:\n`!triforce sua mensagem aqui`")
        return

    # usuario = sid (número do telefone) para o supervisor rotear de volta via WPP
    _enfileirar(pedido, sid, sid, canal="whatsapp", fila_path=CLAUDE_QUEUE)
    await ctx.reply("✨ acionando triforce...")


async def handle_majora(ctx: MessageContext):
    if not _is_owner(ctx):
        await ctx.reply("🔒 Só o dono pode acionar a MAJORA.")
        return

    sid = _sender_id(ctx)

    pedido = ctx.args_text.strip()
    if not pedido:
        m = re.search(r'\[MAJORA:\s*(.+?)\]', ctx.raw_text, re.IGNORECASE)
        if m:
            pedido = m.group(1).strip()

    if not pedido:
        pedido = _ultimo_pedido_llm(sid)

    if not pedido:
        await ctx.reply("Manda o que quer perguntar pro Codex:\n`!majora sua mensagem aqui`")
        return

    _enfileirar(pedido, sid, sid, canal="whatsapp", fila_path=CODEX_QUEUE)
    await ctx.reply("🌑 acionando majora...")


async def handle_mastersword(ctx: MessageContext):
    if not _is_owner(ctx):
        await ctx.reply("🔒 Só o dono pode acionar a MASTERSWORD.")
        return

    sid = _sender_id(ctx)

    pedido = ctx.args_text.strip()
    if not pedido:
        m = re.search(r'\[MASTERSWORD:\s*(.+?)\]', ctx.raw_text, re.IGNORECASE)
        if m:
            pedido = m.group(1).strip()

    if not pedido:
        pedido = _ultimo_pedido_llm(sid)

    if not pedido:
        await ctx.reply("Manda o que quer perguntar pro OpenCode:\n`!mastersword sua mensagem aqui`")
        return

    _enfileirar(pedido, sid, sid, canal="whatsapp", fila_path=MASTERSWORD_QUEUE)
    await ctx.reply("🗡️ acionando mastersword...")


SKILL = [
    Skill(
        name="triforce_cmd",
        description="*!triforce <pedido>* — fala direto com o Claude (só dono)",
        triggers=["!triforce"],
        handler=handle_triforce,
        category="admin",
        priority=20,
    ),
    Skill(
        name="triforce_inline",
        description="*[TRIFORCE: pedido]* — acionar Claude inline",
        triggers=["[triforce"],
        handler=handle_triforce,
        category="admin",
        priority=20,
    ),
    Skill(
        name="majora_cmd",
        description="*!majora <pedido>* — fala direto com o Codex (só dono)",
        triggers=["!majora"],
        handler=handle_majora,
        category="admin",
        priority=20,
    ),
    Skill(
        name="majora_inline",
        description="*[MAJORA: pedido]* — acionar Codex inline",
        triggers=["[majora"],
        handler=handle_majora,
        category="admin",
        priority=20,
    ),
    Skill(
        name="mastersword_cmd",
        description="*!mastersword <pedido>* — fala direto com o OpenCode (só dono)",
        triggers=["!mastersword", "!opencode"],
        handler=handle_mastersword,
        category="admin",
        priority=20,
    ),
    Skill(
        name="mastersword_inline",
        description="*[MASTERSWORD: pedido]* — acionar OpenCode inline",
        triggers=["[mastersword"],
        handler=handle_mastersword,
        category="admin",
        priority=20,
    ),
]
