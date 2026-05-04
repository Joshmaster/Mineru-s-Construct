#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Injeta no contexto do Claude (SessionStart):
- Conversas recentes do Discord (discord.log)
- Erros recentes do bot (bot_error.log)
- Status do supervisor (supervisor.log)
"""
import json
import sys
from pathlib import Path

AGENTS_DIR     = Path(__file__).parent
DISCORD_DIR    = AGENTS_DIR / "DISCORD"
CONV_LOG       = DISCORD_DIR / "discord.log"
BOT_LOG        = DISCORD_DIR / "bot_error.log"
SUPERVISOR_LOG = DISCORD_DIR / "supervisor.log"


def tail(path: Path, n: int) -> list:
    if not path.exists():
        return [f"(nao encontrado: {path.name})"]
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        return lines[-n:] if lines else ["(vazio)"]
    except Exception as e:
        return [f"(erro ao ler {path.name}: {e})"]


if __name__ == "__main__":
    import os
    if os.environ.get("TRIFORCE_DAEMON"):
        sys.exit(0)

    conv_lines = tail(CONV_LOG, 40)       # ultimas 40 linhas de conversa
    bot_lines  = tail(BOT_LOG, 15)        # ultimos erros do bot
    sup_lines  = tail(SUPERVISOR_LOG, 5)  # status do supervisor

    partes = [
        "=== DISCORD: conversas recentes ===",
        *conv_lines,
        "",
        "=== DISCORD: erros do bot ===",
        *bot_lines,
        "",
        "=== DISCORD: supervisor ===",
        *sup_lines,
        "====================================",
        "Valide se o bot (Link) esta respondendo de forma natural e sem repeticao.",
        "Se houver algo errado, avise proativamente.",
    ]

    out = json.dumps({"systemMessage": "\n".join(partes)}, ensure_ascii=True)
    sys.stdout.buffer.write((out + "\n").encode("utf-8"))
    sys.stdout.buffer.flush()
    sys.exit(0)
