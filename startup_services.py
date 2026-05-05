#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import sys as _sys_enc
if _sys_enc.platform == "win32":
    _sys_enc.stdout.reconfigure(encoding="utf-8", errors="replace")
    _sys_enc.stderr.reconfigure(encoding="utf-8", errors="replace")
"""
Gerenciador de serviços Hyrule.

Uso:
  python startup_services.py            → inicia tudo (bot + supervisor)
  python startup_services.py restart    → para tudo, limpa memória, reinicia
  python startup_services.py stop       → para tudo
  python startup_services.py status     → mostra status dos serviços
"""
import json
import os
import sys
import socket
import subprocess
import time
import urllib.request
from pathlib import Path

# ── Caminhos ──────────────────────────────────────────────────────────────────
BASE         = Path(__file__).parent
DISCORD_DIR  = BASE / "DISCORD"
PYTHON       = sys.executable

BOT_SCRIPT        = DISCORD_DIR / "link_discord.py"
SUPERVISOR_SCRIPT = BASE / "bot_supervisor.py"

BOT_PID_FILE        = DISCORD_DIR / ".bot_pid"
SUPERVISOR_PID_FILE = DISCORD_DIR / ".supervisor_pid"

BOT_ERR_LOG    = DISCORD_DIR / "bot_error.log"
SUP_LOG        = DISCORD_DIR / "supervisor_out.log"
DISCORD_LOG    = DISCORD_DIR / "discord.log"

# WhatsApp bot
WHATSAPP_DIR        = BASE / "link-bot"
WHATSAPP_SCRIPT     = WHATSAPP_DIR / "bot" / "main.py"
WHATSAPP_PID_FILE   = WHATSAPP_DIR / ".whatsapp_pid"
WHATSAPP_LOG        = WHATSAPP_DIR / "whatsapp.log"

# TRIFORCE daemon
TRIFORCE_DAEMON_SCRIPT  = BASE / "triforce_daemon.py"
TRIFORCE_DAEMON_PID     = BASE / ".triforce_daemon_pid"
TRIFORCE_DAEMON_LOG     = BASE / "triforce_daemon.log"

# MAJORA watcher (Codex)
MAJORA_SCRIPT  = BASE / "watch_codex_queue.py"
MAJORA_PID     = BASE / ".majora_pid"
MAJORA_LOG     = BASE / "majora.log"

MEMORY_FILES = [
    BASE / "pedidos_vistos.json",        # supervisor usa Agents/ (não DISCORD/)
    DISCORD_DIR / "pedidos_vistos.json", # compat — limpa os dois
    DISCORD_DIR / "user_context.json",
]
HISTORY_DIR = DISCORD_DIR / "history"

DISCORD_PORT = 7331
BOT_API      = f"http://localhost:{DISCORD_PORT}"

_WIN = sys.platform == "win32"
_NO_WINDOW = subprocess.CREATE_NO_WINDOW if _WIN else 0


# ── Helpers cross-platform ────────────────────────────────────────────────────

def _porta_livre(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(1)
        return s.connect_ex(("127.0.0.1", port)) != 0


def _bot_online() -> bool:
    try:
        with urllib.request.urlopen(f"{BOT_API}/status", timeout=3) as r:
            return r.status == 200
    except Exception:
        return False


def _pid_ativo(pid: int) -> bool:
    """Verifica se um PID está rodando (cross-platform)."""
    if _WIN:
        r = subprocess.run(
            ["tasklist", "/FI", f"PID eq {pid}", "/NH"],
            capture_output=True, text=True, timeout=5
        )
        return str(pid) in r.stdout
    else:
        try:
            os.kill(pid, 0)
            return True
        except (ProcessLookupError, PermissionError):
            return False


def _matar_pid(pid: int):
    try:
        if _WIN:
            subprocess.run(["taskkill", "/PID", str(pid), "/F"],
                           capture_output=True, timeout=5)
        else:
            os.kill(pid, 9)
    except Exception:
        pass


def _matar_por_script(nome_script: str):
    """Mata todos os processos python rodando um script específico."""
    try:
        if _WIN:
            ps = (
                "Get-CimInstance Win32_Process "
                f"| Where-Object {{ $_.Name -eq 'python.exe' -and $_.CommandLine -like '*{nome_script}*' }} "
                "| Select-Object -ExpandProperty ProcessId"
            )
            r = subprocess.run(
                ["powershell", "-NoProfile", "-Command", ps],
                capture_output=True, text=True, timeout=10
            )
        else:
            r = subprocess.run(
                ["pgrep", "-f", nome_script],
                capture_output=True, text=True, timeout=10
            )
        pids = [int(p.strip()) for p in r.stdout.splitlines() if p.strip().isdigit()]
        for pid in pids:
            _matar_pid(pid)
            print(f"  killed PID {pid} ({nome_script})")
        return pids
    except Exception as e:
        print(f"  aviso: não consegui listar processos ({e})")
        return []


def _ler_pid(path: Path) -> int | None:
    try:
        val = path.read_text(encoding="ascii").strip()
        digits = "".join(c for c in val if c.isdigit() or c == "\n")
        primeiro = digits.split()[0] if digits.split() else ""
        return int(primeiro) if primeiro else None
    except Exception:
        return None


# ── Verificar se serviço está rodando ────────────────────────────────────────

def _whatsapp_rodando() -> bool:
    pid = _ler_pid(WHATSAPP_PID_FILE)
    return bool(pid) and _pid_ativo(pid)


def _triforce_daemon_rodando() -> bool:
    pid = _ler_pid(TRIFORCE_DAEMON_PID)
    return bool(pid) and _pid_ativo(pid)


# ── Parar serviços ────────────────────────────────────────────────────────────

def parar_bot():
    print("Parando Discord bot...")
    _matar_por_script("link_discord")
    pid = _ler_pid(BOT_PID_FILE)
    if pid:
        _matar_pid(pid)
    BOT_PID_FILE.unlink(missing_ok=True)
    for _ in range(10):
        if _porta_livre(DISCORD_PORT):
            break
        time.sleep(0.5)


def parar_supervisor():
    print("Parando Supervisor...")
    _matar_por_script("bot_supervisor")
    pid = _ler_pid(SUPERVISOR_PID_FILE)
    if pid:
        _matar_pid(pid)
    SUPERVISOR_PID_FILE.unlink(missing_ok=True)


def parar_whatsapp():
    print("Parando WhatsApp bot...")
    _matar_por_script("bot.main")
    pid = _ler_pid(WHATSAPP_PID_FILE)
    if pid:
        _matar_pid(pid)
    WHATSAPP_PID_FILE.unlink(missing_ok=True)


def parar_triforce_daemon():
    print("Parando TRIFORCE daemon...")
    _matar_por_script("triforce_daemon")
    pid = _ler_pid(TRIFORCE_DAEMON_PID)
    if pid:
        _matar_pid(pid)
    TRIFORCE_DAEMON_PID.unlink(missing_ok=True)


# ── Limpar memória ────────────────────────────────────────────────────────────

def limpar_memoria():
    print("Limpando memória...")
    for f in MEMORY_FILES:
        if f.suffix == ".json":
            content = "{}" if "context" in f.name else "[]"
            f.write_text(content, encoding="utf-8")
            print(f"  {f.name} → {content}")
        else:
            f.unlink(missing_ok=True)
    if HISTORY_DIR.exists():
        for hf in HISTORY_DIR.glob("*.json"):
            hf.write_text("[]", encoding="utf-8")
            print(f"  history/{hf.name} → []")
    DISCORD_LOG.write_text("", encoding="utf-8")
    SUP_LOG.write_text("", encoding="utf-8")
    print("  discord.log e supervisor_out.log zerados")


# ── Iniciar serviços ──────────────────────────────────────────────────────────

def iniciar_bot():
    print("Iniciando Discord bot...")
    log = open(BOT_ERR_LOG, "w", encoding="utf-8")
    proc = subprocess.Popen(
        [PYTHON, "-u", str(BOT_SCRIPT)],
        cwd=str(DISCORD_DIR),
        stdout=log,
        stderr=log,
        creationflags=_NO_WINDOW,
    )
    BOT_PID_FILE.write_text(str(proc.pid), encoding="ascii")
    print(f"  PID {proc.pid}")
    for i in range(20):
        time.sleep(0.5)
        if _bot_online():
            print(f"  online ✓ ({(i+1)*0.5:.1f}s)")
            return True
    print("  aviso: bot não respondeu em 10s (pode ainda estar iniciando)")
    return False


def iniciar_supervisor():
    print("Iniciando Supervisor...")
    log_out = open(SUP_LOG, "w", encoding="utf-8")
    proc = subprocess.Popen(
        [PYTHON, "-u", str(SUPERVISOR_SCRIPT)],
        cwd=str(BASE),
        stdout=log_out,
        stderr=log_out,
        creationflags=_NO_WINDOW,
    )
    SUPERVISOR_PID_FILE.write_text(str(proc.pid), encoding="ascii")
    print(f"  PID {proc.pid}")
    time.sleep(1)
    try:
        linha = SUP_LOG.read_text(encoding="utf-8", errors="replace").strip()
        if linha:
            print(f"  {linha.splitlines()[-1]}")
    except Exception:
        pass
    return True


def iniciar_whatsapp():
    print("Iniciando WhatsApp bot...")
    err_log = WHATSAPP_DIR / ".linkbot" / "whatsapp_err.log"
    out_log = WHATSAPP_DIR / ".linkbot" / "whatsapp.log"
    err_log.parent.mkdir(parents=True, exist_ok=True)
    log_out = open(out_log, "w", encoding="utf-8")
    log_err = open(err_log, "w", encoding="utf-8")
    proc = subprocess.Popen(
        [PYTHON, "-u", "-m", "bot.main"],
        cwd=str(WHATSAPP_DIR),
        stdout=log_out,
        stderr=log_err,
        creationflags=_NO_WINDOW,
    )
    WHATSAPP_PID_FILE.write_text(str(proc.pid), encoding="ascii")
    print(f"  PID {proc.pid}")
    time.sleep(3)
    try:
        linha = open(err_log.name, encoding="utf-8", errors="replace").read().strip()
        if linha:
            print(f"  {linha.splitlines()[-1]}")
    except Exception:
        pass
    return True


def iniciar_triforce_daemon():
    print("Iniciando TRIFORCE daemon...")
    log_out = open(TRIFORCE_DAEMON_LOG, "w", encoding="utf-8")
    proc = subprocess.Popen(
        [PYTHON, "-u", str(TRIFORCE_DAEMON_SCRIPT)],
        cwd=str(BASE),
        stdout=log_out,
        stderr=log_out,
        creationflags=_NO_WINDOW,
    )
    TRIFORCE_DAEMON_PID.write_text(str(proc.pid), encoding="ascii")
    print(f"  PID {proc.pid}")
    return True


def iniciar_majora():
    print("Iniciando MAJORA watcher (Codex)...")
    log_out = open(MAJORA_LOG, "w", encoding="utf-8")
    proc = subprocess.Popen(
        [PYTHON, "-u", str(MAJORA_SCRIPT)],
        cwd=str(BASE),
        stdout=log_out,
        stderr=log_out,
        creationflags=_NO_WINDOW,
    )
    MAJORA_PID.write_text(str(proc.pid), encoding="ascii")
    print(f"  PID {proc.pid}")
    return True


def parar_majora():
    _matar_por_script("watch_codex_queue")
    pid = _ler_pid(MAJORA_PID)
    if pid:
        _matar_pid(pid)
    MAJORA_PID.unlink(missing_ok=True)


# ── Apagar mensagens do Discord (após bot online) ─────────────────────────────

def _apagar_msgs_discord():
    for usuario in ["OWNER", "USER2"]:
        try:
            payload = json.dumps({"to": usuario, "count": 100}).encode()
            req = urllib.request.Request(
                f"{BOT_API}/delete", data=payload,
                headers={"Content-Type": "application/json"}, method="POST"
            )
            with urllib.request.urlopen(req, timeout=10) as r:
                data = json.loads(r.read())
                n = data.get("deletadas", 0)
                if n:
                    print(f"  Discord DM {usuario}: {n} msgs apagadas")
        except Exception as e:
            print(f"  Discord DM {usuario}: erro ao apagar — {e}")


# ── Comandos ──────────────────────────────────────────────────────────────────

def cmd_start():
    """Inicia serviços que estiverem parados."""
    if _bot_online():
        print("Discord bot já está online.")
    else:
        iniciar_bot()

    pid_sup = _ler_pid(SUPERVISOR_PID_FILE)
    if pid_sup and _pid_ativo(pid_sup):
        print(f"Supervisor já rodando (PID {pid_sup}).")
    else:
        iniciar_supervisor()

    if _whatsapp_rodando():
        print("WhatsApp bot já está rodando.")
    else:
        iniciar_whatsapp()

    if _triforce_daemon_rodando():
        print("TRIFORCE daemon já está rodando.")
    else:
        iniciar_triforce_daemon()
    iniciar_majora()


def cmd_restart(limpar: bool = True):
    """Para tudo, opcionalmente limpa memória, reinicia."""
    parar_bot()
    parar_supervisor()
    parar_whatsapp()
    parar_triforce_daemon()
    parar_majora()
    time.sleep(1)
    if limpar:
        limpar_memoria()
    iniciar_bot()
    iniciar_supervisor()
    iniciar_whatsapp()
    iniciar_triforce_daemon()
    iniciar_majora()
    if limpar:
        _apagar_msgs_discord()


def cmd_stop():
    parar_bot()
    parar_supervisor()
    parar_whatsapp()
    parar_triforce_daemon()
    parar_majora()
    print("Serviços parados.")


def cmd_status():
    bot_ok = _bot_online()
    print(f"Discord bot:  {'● online' if bot_ok else '○ offline'}")

    pid_sup = _ler_pid(SUPERVISOR_PID_FILE)
    sup_ok = bool(pid_sup) and _pid_ativo(pid_sup)
    print(f"Supervisor:   {'● rodando' if sup_ok else '○ parado'}")

    print(f"WhatsApp bot: {'● rodando' if _whatsapp_rodando() else '○ parado'}")

    pid_tri = _ler_pid(TRIFORCE_DAEMON_PID)
    tri_ok = bool(pid_tri) and _pid_ativo(pid_tri)
    print(f"Triforce:     {'● rodando' if tri_ok else '○ parado'}")

    try:
        linhas = SUP_LOG.read_text(encoding="utf-8", errors="replace").strip().splitlines()
        if linhas:
            print(f"Último log:   {linhas[-1]}")
    except Exception:
        pass


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    if os.environ.get("TRIFORCE_DAEMON"):
        sys.exit(0)

    cmd = sys.argv[1].lower() if len(sys.argv) > 1 else "start"

    if cmd == "restart":
        print("=== Restart completo (com limpeza) ===")
        cmd_restart(limpar=True)
    elif cmd == "restart-nolimp":
        print("=== Restart sem limpeza ===")
        cmd_restart(limpar=False)
    elif cmd == "stop":
        print("=== Parando serviços ===")
        cmd_stop()
    elif cmd == "status":
        cmd_status()
    elif cmd == "start":
        print("=== Iniciando serviços ===")
        cmd_start()
    else:
        print(__doc__)
        sys.exit(1)

    print("=== Pronto ===")
