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

        primeiro    = itens[0] if itens else {}
        usuario     = primeiro.get("usuario", "OWNER")
        canal       = primeiro.get("canal", "discord")
        sender_id   = primeiro.get("sender_id", "")
        porta       = 7332 if canal == "whatsapp" else 7331
        destino     = sender_id if (canal == "whatsapp" and sender_id) else usuario

        pedidos = "\n".join(
            f"[{it.get('ts','')}] {it.get('usuario','?')}: {it.get('pedido','')}"
            for it in itens
        )

        msg = (
            f"=== TRIFORCE — PEDIDO VIA {canal.upper()} (slot {slot}) ===\n"
            f"{pedidos}\n"
            f"{'=' * 48}\n"
            f"AÇÃO OBRIGATÓRIA — faça isso agora sem explicar:\n"
            f"1. Leia o pedido acima\n"
            f"2. Responda como Link: direto, curto, sem formalidade, em português\n"
            f"3. Envie via POST http://localhost:{porta}/send\n"
            f"   body: {{\"to\": \"{destino}\", \"msg\": \"🔱 <sua resposta>\"}}\n"
            f"IMPORTANTE: a resposta DEVE começar com 🔱 para identificar que veio do agente de código.\n"
            f"NÃO explique o que vai fazer. NÃO pergunte se deve configurar algo. Só execute e poste."
        )

        out = json.dumps({"systemMessage": msg}, ensure_ascii=False)
        sys.stdout.buffer.write((out + "\n").encode("utf-8"))
        sys.stdout.buffer.flush()
        sys.exit(2)  # acorda Claude Code (asyncRewake reinicia este watcher automaticamente)
