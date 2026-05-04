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

CLAUDE_QUEUE = Path(r"C:\Users\OWNER\Agents\claude_queue.json")
CONFIG_PATH  = Path(r"C:\Users\OWNER\Agents\link-bot\config\config.json")


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


def _enfileirar(pedido: str, usuario: str, sender_id: str, canal: str = "whatsapp"):
    fila = []
    if CLAUDE_QUEUE.exists():
        try:
            fila = json.loads(CLAUDE_QUEUE.read_text(encoding="utf-8"))
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
    CLAUDE_QUEUE.write_text(json.dumps(fila, ensure_ascii=False, indent=2), encoding="utf-8")


async def handle_triforce(ctx: MessageContext):
    if not _is_owner(ctx):
        await ctx.reply("🔒 Só o dono pode acionar a TRIFORCE.")
        return

    sid = _sender_id(ctx)

    # Tenta pegar pedido do args ou do padrão [TRIFORCE: ...]
    pedido = ctx.args_text.strip()
    if not pedido:
        m = re.search(r'\[TRIFORCE:\s*(.+?)\]', ctx.raw_text, re.IGNORECASE)
        if m:
            pedido = m.group(1).strip()

    # Sem args → usa a última mensagem do histórico LLM
    if not pedido:
        pedido = _ultimo_pedido_llm(sid)

    if not pedido:
        await ctx.reply("Manda o que quer perguntar pro Claude:\n`!triforce sua mensagem aqui`")
        return

    _enfileirar(pedido, "OWNER", sid, canal="whatsapp")
    await ctx.reply(f"🔱 chamando o Claude...\n_{pedido[:120]}_")


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
]
