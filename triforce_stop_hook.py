#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Stop hook — roda após cada resposta do Claude Code.
Verifica se há pedidos TRIFORCE na fila e injeta como systemMessage
para Claude processar autonomamente no próximo turn.
"""
import json
import sys
from pathlib import Path

QUEUE_FILE = Path(__file__).parent / "claude_queue.json"
CLAIMING   = Path(__file__).parent / "claude_queue.stop_claiming.json"

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

if __name__ == "__main__":
    if not QUEUE_FILE.exists():
        sys.exit(0)

    # Claim atômico — evita conflito com o watcher
    try:
        QUEUE_FILE.rename(CLAIMING)
    except (FileNotFoundError, OSError):
        sys.exit(0)

    try:
        fila = json.loads(CLAIMING.read_text(encoding="utf-8"))
    except Exception:
        fila = []

    # Restaura fila vazia imediatamente
    QUEUE_FILE.write_text("[]", encoding="utf-8")
    CLAIMING.unlink(missing_ok=True)

    if not fila:
        sys.exit(0)

    usuario = fila[0].get("usuario", "OWNER")
    pedidos = "\n".join(
        f"[{it.get('ts','')}] {it.get('usuario','?')}: {it.get('pedido','')}"
        for it in fila
    )

    msg = (
        f"=== TRIFORCE — PEDIDO DO DISCORD ===\n"
        f"{pedidos}\n"
        f"=====================================\n"
        f"Processe o pedido acima e envie a resposta via:\n"
        f"POST http://localhost:7331/send  body: {{\"to\": \"{usuario}\", \"msg\": \"sua resposta\"}}"
    )

    out = json.dumps({"systemMessage": msg}, ensure_ascii=False)
    sys.stdout.buffer.write((out + "\n").encode("utf-8"))
    sys.stdout.buffer.flush()
    sys.exit(0)
