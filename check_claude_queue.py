#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Lê a fila de pedidos do bot Discord destinados ao Claude Code.
Roda no UserPromptSubmit — injeta pedidos pendentes como systemMessage.
Limpa a fila após leitura.
"""
import json
import sys
from pathlib import Path

QUEUE_FILE = Path(__file__).parent / "claude_queue.json"

if __name__ == "__main__":
    if not QUEUE_FILE.exists():
        sys.exit(0)

    try:
        fila = json.loads(QUEUE_FILE.read_text(encoding="utf-8"))
    except Exception:
        sys.exit(0)

    if not fila:
        sys.exit(0)

    # NÃO limpa a fila — o watcher (asyncRewake) é quem limpa via rename atômico
    # Limpar aqui causava race condition: fila sumia antes do watcher acordar Claude

    partes = ["=== PEDIDOS DO DISCORD AGUARDANDO ==="]
    for item in fila:
        partes.append(f"[{item['ts']}] {item['usuario']}: {item['pedido']}")
    partes.append("=====================================")
    partes.append("Execute cada pedido acima e envie o resultado via /send do bot Discord.")

    out = json.dumps({"systemMessage": "\n".join(partes)}, ensure_ascii=True)
    sys.stdout.buffer.write((out + "\n").encode("utf-8"))
    sys.stdout.buffer.flush()
    sys.exit(0)
