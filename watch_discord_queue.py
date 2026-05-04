#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Watcher de pedidos do Discord para o Claude Code.
Roda em N instâncias paralelas via asyncRewake (uma por slot).
Quando pega item: imprime systemMessage e sai com código 2 → injeta na sessão Claude Code ativa.
"""
import json
import sys
import time
from pathlib import Path

QUEUE_FILE      = Path(__file__).parent / "claude_queue.json"
CLAIMING_PREFIX = "claude_queue.claiming_"
POLL_SECS       = 1

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def _contar() -> int:
    try:
        return len(json.loads(QUEUE_FILE.read_text(encoding="utf-8")))
    except Exception:
        return 0


def _tentar_pegar(slot: int) -> list:
    claiming = QUEUE_FILE.parent / f"{CLAIMING_PREFIX}{slot}.json"
    try:
        QUEUE_FILE.rename(claiming)
    except (FileNotFoundError, OSError):
        return []
    try:
        itens = json.loads(claiming.read_text(encoding="utf-8"))
    except Exception:
        itens = []
    QUEUE_FILE.write_text("[]", encoding="utf-8")
    claiming.unlink(missing_ok=True)
    return itens


def _limpar_claiming_antigos():
    for f in QUEUE_FILE.parent.glob(f"{CLAIMING_PREFIX}*.json"):
        try:
            age = time.time() - f.stat().st_mtime
            if age > 10:
                try:
                    itens = json.loads(f.read_text(encoding="utf-8"))
                    if itens:
                        fila = []
                        try:
                            fila = json.loads(QUEUE_FILE.read_text(encoding="utf-8"))
                        except Exception:
                            pass
                        QUEUE_FILE.write_text(json.dumps(fila + itens), encoding="utf-8")
                except Exception:
                    pass
                f.unlink(missing_ok=True)
        except Exception:
            pass


if __name__ == "__main__":
    import os
    if os.environ.get("TRIFORCE_DAEMON"):
        sys.exit(0)

    slot = int(sys.argv[1]) if len(sys.argv) > 1 else 0
    # Delay escalonado: slots reiniciam em momentos diferentes, nunca todos juntos
    time.sleep(slot * 2)
    _limpar_claiming_antigos()

    while True:
        time.sleep(POLL_SECS)

        if _contar() == 0:
            continue

        itens = _tentar_pegar(slot)
        if not itens:
            continue

        usuario = itens[0].get("usuario", "OWNER") if itens else "OWNER"
        pedidos = "\n".join(
            f"[{it.get('ts','')}] {it.get('usuario','?')}: {it.get('pedido','')}"
            for it in itens
        )

        msg = (
            f"=== TRIFORCE — PEDIDO DO DISCORD (slot {slot}) ===\n"
            f"{pedidos}\n"
            f"{'=' * 48}\n"
            f"Processe o pedido acima e responda via:\n"
            f"POST http://localhost:7331/send  body: {{\"to\": \"{usuario}\", \"msg\": \"sua resposta\"}}"
        )

        out = json.dumps({"systemMessage": msg}, ensure_ascii=False)
        sys.stdout.buffer.write((out + "\n").encode("utf-8"))
        sys.stdout.buffer.flush()
        sys.exit(2)  # acorda Claude Code (asyncRewake reinicia este watcher automaticamente)
