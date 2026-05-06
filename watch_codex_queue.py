#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Watcher MAJORA — processa pedidos do Codex CLI.
Lê codex_queue.json, spawna 'codex --full-auto', envia resposta via HTTP API.
"""
import json
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

QUEUE_FILE = Path(__file__).parent / "codex_queue.json"
POLL_SECS  = 2

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def _ler_e_limpar() -> list:
    if not QUEUE_FILE.exists():
        return []
    try:
        itens = json.loads(QUEUE_FILE.read_text(encoding="utf-8"))
        if itens:
            QUEUE_FILE.write_text("[]", encoding="utf-8")
        return itens
    except Exception:
        return []


def _enviar(usuario: str, msg: str, canal: str = "discord"):
    porta = 7332 if canal == "whatsapp" else 7331
    payload = json.dumps({"to": usuario, "msg": msg}).encode("utf-8")
    req = urllib.request.Request(
        f"http://localhost:{porta}/send", data=payload,
        headers={"Content-Type": "application/json"}, method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            pass
        print(f"ENVIADO ({canal}:{porta}) -> {usuario}: {msg[:60]}", flush=True)
    except Exception as e:
        print(f"Erro enviar ({canal}): {e}", flush=True)


def _processar(item: dict):
    pedido  = item.get("pedido", "").strip()
    usuario = item.get("usuario", "OWNER")
    canal   = item.get("canal", "discord")

    if not pedido:
        return

    print(f"MAJORA processando: {pedido[:80]}", flush=True)

    try:
        result = subprocess.run(
            ["codex", "exec", pedido],
            capture_output=True, text=True, timeout=180,
            encoding="utf-8", errors="replace",
            cwd="~/Agents",
        )
        resposta = (result.stdout or "").strip()
        if not resposta:
            resposta = (result.stderr or "").strip()
        if not resposta:
            resposta = "🌀 sem resposta do Codex"
    except subprocess.TimeoutExpired:
        resposta = "⚠️ majora demorou demais — timeout 3min"
    except FileNotFoundError:
        resposta = "⚠️ codex não encontrado no PATH"
    except Exception as e:
        resposta = f"⚠️ erro majora: {e}"

    _enviar(usuario, f"🌑 {resposta}"[:2000], canal)


if __name__ == "__main__":
    print(f"🌑 MAJORA watcher iniciado. Monitorando {QUEUE_FILE}", flush=True)
    while True:
        time.sleep(POLL_SECS)
        itens = _ler_e_limpar()
        for item in itens:
            try:
                _processar(item)
            except Exception as e:
                print(f"Erro item MAJORA: {e}", flush=True)
