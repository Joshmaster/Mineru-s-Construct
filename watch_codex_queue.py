#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Watcher MAJORA — processa pedidos do Codex CLI.
Lê codex_queue.json, spawna 'codex --full-auto', envia resposta via HTTP API.
"""
import json
import os
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

QUEUE_FILE = Path(__file__).parent / "codex_queue.json"
LOCK_FILE  = Path(__file__).parent / ".majora_processing.lock"
POLL_SECS  = 2
STALE_LOCK_SECS = 15 * 60

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


def _pid_ativo(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except (ProcessLookupError, ValueError):
        return False
    except PermissionError:
        return True


def _lock_stale() -> bool:
    try:
        data = json.loads(LOCK_FILE.read_text(encoding="utf-8"))
        pid = int(data.get("pid", 0))
        ts = float(data.get("ts", 0))
        return (not _pid_ativo(pid)) or (time.time() - ts > STALE_LOCK_SECS)
    except Exception:
        return True


def _adquirir_lock() -> bool:
    if LOCK_FILE.exists() and _lock_stale():
        LOCK_FILE.unlink(missing_ok=True)
    payload = json.dumps({"pid": os.getpid(), "ts": time.time()})
    try:
        fd = os.open(str(LOCK_FILE), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(payload)
        return True
    except FileExistsError:
        return False


def _liberar_lock():
    try:
        data = json.loads(LOCK_FILE.read_text(encoding="utf-8"))
        if int(data.get("pid", 0)) == os.getpid():
            LOCK_FILE.unlink(missing_ok=True)
    except Exception:
        pass


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

    if not _adquirir_lock():
        _enviar(usuario, "MAJORA ja esta processando outro pedido. Segura esse por um instante.", canal)
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
    finally:
        _liberar_lock()

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
