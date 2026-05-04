#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Link Console — monitor + chat direto com o Link Discord.

Uso:
  python link_console.py          → abre o console
  python link_console.py "oi"    → envia mensagem e sai

Comandos no console:
  /status   → mostra status dos serviços
  /limpar   → limpa a tela
  /sair     → encerra
  (qualquer outro texto) → envia mensagem pro Link como OWNER
"""
import sys
import os
import threading
import time
import json
import urllib.request
import subprocess
from pathlib import Path
from datetime import datetime

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    os.system("chcp 65001 > nul 2>&1")

# ── Caminhos ──────────────────────────────────────────────────────────────────
AGENTS_DIR   = Path(__file__).parent
DISCORD_DIR  = AGENTS_DIR / "DISCORD"
LOG_FILE     = DISCORD_DIR / "discord.log"
SUP_LOG      = AGENTS_DIR / "supervisor.log"
BOT_API      = "http://localhost:7331"

# ── Cores ANSI ────────────────────────────────────────────────────────────────
R  = "\033[0m"        # reset
B  = "\033[1m"        # bold
DIM = "\033[2m"       # dim

C_IN    = "\033[96m"  # ciano   — mensagens recebidas (IN)
C_OUT   = "\033[92m"  # verde   — mensagens enviadas (OUT)
C_SYS   = "\033[93m"  # amarelo — sistema/SHEIKAH_SLATE
C_ERR   = "\033[91m"  # vermelho — erros
C_INFO  = "\033[90m"  # cinza   — info/timestamp
C_TITLE = "\033[95m"  # magenta — títulos

# ── Estado do tail ────────────────────────────────────────────────────────────
_last_pos = 0
_running  = True


def cor_linha(linha: str) -> str:
    if "[IN]"  in linha: return C_IN  + linha + R
    if "[OUT]" in linha: return C_OUT + linha + R
    if "[SYS]" in linha: return C_SYS + linha + R
    if "ERRO"  in linha.upper() or "Error" in linha: return C_ERR + linha + R
    return DIM + linha + R


def tail_log():
    """Thread que monitora discord.log e imprime novas linhas."""
    global _last_pos
    if LOG_FILE.exists():
        _last_pos = LOG_FILE.stat().st_size
    while _running:
        try:
            if LOG_FILE.exists():
                size = LOG_FILE.stat().st_size
                if size > _last_pos:
                    with open(LOG_FILE, encoding="utf-8", errors="replace") as f:
                        f.seek(_last_pos)
                        novas = f.read()
                    _last_pos = size
                    for linha in novas.splitlines():
                        if linha.strip():
                            print(cor_linha(linha))
        except Exception:
            pass
        time.sleep(0.4)


SERVICOS = [
    {
        "key":    "link_discord",
        "label":  "Link Discord   ",
        "script": str(AGENTS_DIR / "DISCORD" / "link_discord.py"),
    },
    {
        "key":    "bot_supervisor",
        "label":  "Bot Supervisor ",
        "script": str(AGENTS_DIR / "bot_supervisor.py"),
    },
]


def _bot_online() -> bool:
    """Checa se o bot HTTP está respondendo na porta 7331."""
    try:
        with urllib.request.urlopen(f"{BOT_API}/status", timeout=2) as r:
            return r.status == 200
    except Exception:
        return False


def _supervisor_rodando() -> bool:
    """Checa se o supervisor está rodando pelo arquivo de log."""
    try:
        sup_log = AGENTS_DIR / "DISCORD" / "supervisor_out.log"
        if not sup_log.exists():
            return False
        mtime = sup_log.stat().st_mtime
        return (time.time() - mtime) < 30  # atualizado nos últimos 30s
    except Exception:
        return False


def _script_rodando(script_key: str) -> bool:
    """Verifica se um script está rodando."""
    try:
        if script_key == "link_discord":
            return _bot_online()
        if script_key == "bot_supervisor":
            log = AGENTS_DIR / "DISCORD" / "supervisor_out.log"
            if not log.exists():
                return False
            return (time.time() - log.stat().st_mtime) < 300  # 5 min
        return False
    except Exception:
        return False


def acordar_servicos():
    """Inicia serviços que estiverem parados."""
    iniciados = []
    for s in SERVICOS:
        if not _script_rodando(s["key"]):
            try:
                log_out = subprocess.DEVNULL
                if s["key"] == "link_discord":
                    log_out = open(DISCORD_DIR / "discord.log", "w", encoding="utf-8")
                elif s["key"] == "bot_supervisor":
                    log_out = open(DISCORD_DIR / "supervisor_out.log", "a", encoding="utf-8")
                subprocess.Popen(
                    ["python", "-u", s["script"]],
                    cwd=str(AGENTS_DIR),
                    creationflags=subprocess.CREATE_NO_WINDOW,
                    stdout=log_out,
                    stderr=log_out,
                )
                iniciados.append(s["label"].strip())
            except Exception as e:
                print(f"{C_ERR}Erro ao iniciar {s['label'].strip()}: {e}{R}")
    if iniciados:
        print(f"{C_SYS}▶ Iniciando: {', '.join(iniciados)}...{R}")
        time.sleep(6)


def status_servicos():
    """Mostra quais processos estão rodando."""
    print(f"\n{C_TITLE}{B}── Serviços ──────────────────────────────{R}")
    for s in SERVICOS:
        ativo = _script_rodando(s["key"])
        status = f"{C_OUT}● rodando{R}" if ativo else f"{C_ERR}○ parado{R}"
        print(f"  {s['label']} {status}")
    print()


def enviar_mensagem(texto: str):
    """Envia mensagem pro Link e recebe resposta no console (sem tocar no Discord)."""
    payload = json.dumps({"from": "OWNER", "msg": texto}).encode("utf-8")
    req = urllib.request.Request(
        f"{BOT_API}/chat",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            data = json.loads(r.read())
            if data.get("ok"):
                print(f"\n{C_OUT}{B}Link:{R} {data['resposta']}\n")
            else:
                print(f"{C_ERR}Erro: {data.get('error')}{R}")
    except Exception as e:
        print(f"{C_ERR}Bot indisponível: {e}{R}")


def cabecalho():
    os.system("cls" if sys.platform == "win32" else "clear")
    print(f"{C_TITLE}{B}")
    print("  ██╗     ██╗███╗   ██╗██╗  ██╗")
    print("  ██║     ██║████╗  ██║██║ ██╔╝")
    print("  ██║     ██║██╔██╗ ██║█████╔╝ ")
    print("  ██║     ██║██║╚██╗██║██╔═██╗ ")
    print("  ███████╗██║██║ ╚████║██║  ██╗")
    print("  ╚══════╝╚═╝╚═╝  ╚═══╝╚═╝  ╚═╝")
    print(f"{R}{DIM}  Console — Sistema Hyrule{R}")
    print(f"{C_INFO}  {datetime.now().strftime('%d/%m/%Y %H:%M')}  |  /status  /limpar  /sair{R}")
    print(f"{C_TITLE}{'─'*50}{R}\n")


def loop_historico():
    """Não imprime histórico — evita feedback loop no Windows terminal."""
    pass


def main():
    global _running

    # Modo one-shot: python link_console.py "mensagem"
    if len(sys.argv) > 1:
        enviar_mensagem(" ".join(sys.argv[1:]))
        return

    cabecalho()
    acordar_servicos()
    status_servicos()
    loop_historico()

    # Inicia thread de monitoramento
    t = threading.Thread(target=tail_log, daemon=True)
    t.start()

    print(f"{C_INFO}Digite uma mensagem pra enviar ao Link, ou um comando (/status, /limpar, /sair):{R}")
    print()

    try:
        while True:
            try:
                entrada = input(f"{B}>{R} ").strip()
            except EOFError:
                break

            if not entrada:
                continue

            if entrada.lower() in ("/sair", "/exit", "/quit"):
                break
            elif entrada.lower() == "/limpar":
                cabecalho()
                loop_historico()
            elif entrada.lower() == "/status":
                status_servicos()
            else:
                enviar_mensagem(entrada)

    except KeyboardInterrupt:
        pass
    finally:
        _running = False
        print(f"\n{C_INFO}Console encerrado.{R}")


if __name__ == "__main__":
    main()
