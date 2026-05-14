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
import shutil
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

# WhatsApp Bridge (Baileys Node.js)
BRIDGE_DIR          = BASE / "whatsapp-bridge"
BRIDGE_SCRIPT       = BRIDGE_DIR / "index.js"
BRIDGE_PID_FILE     = BRIDGE_DIR / ".bridge_pid"
BRIDGE_LOG          = BRIDGE_DIR / "bridge.log"
BRIDGE_PORT         = 7334

# TRIFORCE daemon
TRIFORCE_DAEMON_SCRIPT  = BASE / "triforce_daemon.py"
TRIFORCE_DAEMON_PID     = BASE / ".triforce_daemon_pid"
TRIFORCE_DAEMON_LOG     = BASE / "triforce_daemon.log"

# MAJORA watcher (Codex)
MAJORA_SCRIPT  = BASE / "watch_codex_queue.py"
MAJORA_PID     = BASE / ".majora_pid"
MAJORA_LOG     = BASE / "majora.log"

# MASTERSWORD watcher (OpenCode)
MASTERSWORD_SCRIPT = BASE / "watch_mastersword_queue.py"
MASTERSWORD_PID    = BASE / ".mastersword_pid"
MASTERSWORD_LOG    = BASE / "mastersword.log"

# itch-monitor daemon
ITCH_SCRIPT = BASE / "itch_monitor.py"
ITCH_PID    = BASE / ".itch_monitor_pid"
ITCH_LOG    = BASE / "itch_monitor.log"

# Hyrule proxy
PROXY_SCRIPT = BASE / "CLAUDE CODE" / "proxy.py"
PROXY_PID    = BASE / ".proxy_pid"
PROXY_LOG    = BASE / "CLAUDE CODE" / "proxy_runtime.log"
PROXY_PORT   = 8765

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


def _porta_ativa(port: int) -> bool:
    return not _porta_livre(port)


def _ffmpeg_disponivel() -> bool:
    if shutil.which("ffmpeg"):
        return True
    return os.path.isfile("/usr/bin/ffmpeg") and os.access("/usr/bin/ffmpeg", os.X_OK)


def _spawn(args: list[str], cwd: Path, stdout_path: Path, pid_path: Path, stderr_path: Path | None = None):
    """Sobe processo persistente, independente do shell que chamou o gerenciador."""
    stdout_path.parent.mkdir(parents=True, exist_ok=True)
    log_out = open(stdout_path, "w", encoding="utf-8")
    log_err = open(stderr_path, "w", encoding="utf-8") if stderr_path else log_out
    kwargs = {
        "cwd": str(cwd),
        "stdout": log_out,
        "stderr": log_err,
        "creationflags": _NO_WINDOW,
    }
    if not _WIN:
        kwargs["start_new_session"] = True
    proc = subprocess.Popen(args, **kwargs)
    pid_path.write_text(str(proc.pid), encoding="ascii")
    return proc


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

def _bridge_rodando() -> bool:
    pid = _ler_pid(BRIDGE_PID_FILE)
    return bool(pid) and _pid_ativo(pid) and _porta_ativa(BRIDGE_PORT)


def _whatsapp_rodando() -> bool:
    pid = _ler_pid(WHATSAPP_PID_FILE)
    return bool(pid) and _pid_ativo(pid)


def _triforce_daemon_rodando() -> bool:
    pid = _ler_pid(TRIFORCE_DAEMON_PID)
    return bool(pid) and _pid_ativo(pid)


def _majora_rodando() -> bool:
    pid = _ler_pid(MAJORA_PID)
    return bool(pid) and _pid_ativo(pid)


def _mastersword_rodando() -> bool:
    pid = _ler_pid(MASTERSWORD_PID)
    return bool(pid) and _pid_ativo(pid)


def _itch_monitor_rodando() -> bool:
    pid = _ler_pid(ITCH_PID)
    return bool(pid) and _pid_ativo(pid)


def _proxy_rodando() -> bool:
    pid = _ler_pid(PROXY_PID)
    return bool(pid) and _pid_ativo(pid) and _porta_ativa(PROXY_PORT)


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


def parar_bridge():
    print("Parando WhatsApp Bridge (Baileys)...")
    # Mata processo node rodando o bridge
    try:
        if _WIN:
            r = subprocess.run(
                ["powershell", "-NoProfile", "-Command",
                 f"Get-CimInstance Win32_Process | Where-Object {{ $_.Name -eq 'node.exe' -and $_.CommandLine -like '*whatsapp-bridge*' }} | Select-Object -ExpandProperty ProcessId"],
                capture_output=True, text=True, timeout=10
            )
        else:
            r = subprocess.run(["pgrep", "-f", "whatsapp-bridge"], capture_output=True, text=True, timeout=10)
        pids = [int(p.strip()) for p in r.stdout.splitlines() if p.strip().isdigit()]
        for pid in pids:
            _matar_pid(pid)
    except Exception:
        pass
    pid = _ler_pid(BRIDGE_PID_FILE)
    if pid:
        _matar_pid(pid)
    BRIDGE_PID_FILE.unlink(missing_ok=True)
    for _ in range(10):
        if _porta_livre(BRIDGE_PORT):
            break
        time.sleep(0.5)


def parar_whatsapp():
    print("Parando WhatsApp bot...")
    _matar_por_script("bot.main")
    pid = _ler_pid(WHATSAPP_PID_FILE)
    if pid:
        _matar_pid(pid)
    WHATSAPP_PID_FILE.unlink(missing_ok=True)


def parar_itch_monitor():
    print("Parando itch-monitor...")
    _matar_por_script("itch_monitor")
    pid = _ler_pid(ITCH_PID)
    if pid:
        _matar_pid(pid, "itch_monitor")
    ITCH_PID.unlink(missing_ok=True)


def parar_triforce_daemon():
    print("Parando TRIFORCE daemon...")
    _matar_por_script("triforce_daemon")
    pid = _ler_pid(TRIFORCE_DAEMON_PID)
    if pid:
        _matar_pid(pid)
    TRIFORCE_DAEMON_PID.unlink(missing_ok=True)


def parar_proxy():
    print("Parando Hyrule Proxy...")
    _matar_por_script("proxy.py --serve")
    pid = _ler_pid(PROXY_PID)
    if pid:
        _matar_pid(pid)
    PROXY_PID.unlink(missing_ok=True)
    for _ in range(10):
        if _porta_livre(PROXY_PORT):
            break
        time.sleep(0.5)


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
    proc = _spawn(
        [PYTHON, "-u", str(BOT_SCRIPT)],
        DISCORD_DIR,
        BOT_ERR_LOG,
        BOT_PID_FILE,
    )
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
    proc = _spawn(
        [PYTHON, "-u", str(SUPERVISOR_SCRIPT)],
        BASE,
        SUP_LOG,
        SUPERVISOR_PID_FILE,
    )
    print(f"  PID {proc.pid}")
    time.sleep(1)
    try:
        linha = SUP_LOG.read_text(encoding="utf-8", errors="replace").strip()
        if linha:
            print(f"  {linha.splitlines()[-1]}")
    except Exception:
        pass
    return True


def iniciar_bridge():
    if not BRIDGE_SCRIPT.exists():
        print(f"  ⚠️  Bridge não encontrado em {BRIDGE_SCRIPT}. Rode: cd whatsapp-bridge && npm install")
        return False
    node = shutil.which("node")
    if not node:
        print("  ⚠️  Node.js não encontrado no PATH.")
        return False
    print("Iniciando WhatsApp Bridge (Baileys)...")
    proc = _spawn(
        [node, str(BRIDGE_SCRIPT)],
        BRIDGE_DIR,
        BRIDGE_LOG,
        BRIDGE_PID_FILE,
    )
    print(f"  PID {proc.pid}")
    # Aguarda porta subir (até 15s)
    for i in range(30):
        time.sleep(0.5)
        if _porta_ativa(BRIDGE_PORT):
            print(f"  porta {BRIDGE_PORT} online ✓ ({(i+1)*0.5:.1f}s)")
            print(f"  QR disponível em: http://localhost:{BRIDGE_PORT}/qr")
            return True
    print(f"  aviso: bridge não abriu porta {BRIDGE_PORT} em 15s")
    return False


def iniciar_whatsapp():
    print("Iniciando WhatsApp bot...")
    err_log = WHATSAPP_DIR / ".linkbot" / "whatsapp_err.log"
    out_log = WHATSAPP_DIR / ".linkbot" / "whatsapp.log"
    proc = _spawn(
        [PYTHON, "-u", "-m", "bot.main"],
        WHATSAPP_DIR,
        out_log,
        WHATSAPP_PID_FILE,
        err_log,
    )
    print(f"  PID {proc.pid}")
    time.sleep(3)
    try:
        linha = open(err_log.name if hasattr(err_log, 'name') else str(err_log), encoding="utf-8", errors="replace").read().strip()
        if linha:
            print(f"  {linha.splitlines()[-1]}")
    except Exception:
        pass
    return True


def iniciar_itch_monitor():
    print("Iniciando itch-monitor daemon...")
    proc = _spawn(
        [PYTHON, "-u", str(ITCH_SCRIPT)],
        BASE,
        ITCH_LOG,
        ITCH_PID,
    )
    print(f"  PID {proc.pid}")
    return True


def iniciar_triforce_daemon():
    print("Iniciando TRIFORCE daemon...")
    proc = _spawn(
        [PYTHON, "-u", str(TRIFORCE_DAEMON_SCRIPT)],
        BASE,
        TRIFORCE_DAEMON_LOG,
        TRIFORCE_DAEMON_PID,
    )
    print(f"  PID {proc.pid}")
    return True


def iniciar_majora():
    print("Iniciando MAJORA watcher (Codex)...")
    proc = _spawn(
        [PYTHON, "-u", str(MAJORA_SCRIPT)],
        BASE,
        MAJORA_LOG,
        MAJORA_PID,
    )
    print(f"  PID {proc.pid}")
    return True


def iniciar_mastersword():
    print("Iniciando MASTERSWORD watcher (OpenCode)...")
    proc = _spawn(
        [PYTHON, "-u", str(MASTERSWORD_SCRIPT)],
        BASE,
        MASTERSWORD_LOG,
        MASTERSWORD_PID,
    )
    print(f"  PID {proc.pid}")
    return True


def iniciar_proxy():
    if not PROXY_SCRIPT.exists():
        print("Hyrule Proxy não encontrado.")
        return False
    print("Iniciando Hyrule Proxy...")
    proc = _spawn(
        [PYTHON, "-u", str(PROXY_SCRIPT), "--serve"],
        PROXY_SCRIPT.parent,
        PROXY_LOG,
        PROXY_PID,
    )
    print(f"  PID {proc.pid}")
    for i in range(20):
        time.sleep(0.5)
        if _porta_ativa(PROXY_PORT):
            print(f"  porta {PROXY_PORT} online ✓ ({(i+1)*0.5:.1f}s)")
            return True
    print(f"  aviso: proxy não abriu porta {PROXY_PORT} em 10s")
    return False


def parar_majora():
    _matar_por_script("watch_codex_queue")
    pid = _ler_pid(MAJORA_PID)
    if pid:
        _matar_pid(pid)
    MAJORA_PID.unlink(missing_ok=True)


def parar_mastersword():
    _matar_por_script("watch_mastersword_queue")
    pid = _ler_pid(MASTERSWORD_PID)
    if pid:
        _matar_pid(pid)
    MASTERSWORD_PID.unlink(missing_ok=True)


# ── Apagar mensagens do Discord (após bot online) ─────────────────────────────

def _apagar_msgs_discord():
    for usuario in ["josh", "manu"]:
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
    if _proxy_rodando():
        print(f"Hyrule Proxy já rodando (PID {_ler_pid(PROXY_PID)}).")
    else:
        iniciar_proxy()

    if _bot_online():
        print("Discord bot já está online.")
    else:
        iniciar_bot()

    pid_sup = _ler_pid(SUPERVISOR_PID_FILE)
    if pid_sup and _pid_ativo(pid_sup):
        print(f"Supervisor já rodando (PID {pid_sup}).")
    else:
        iniciar_supervisor()

    # Bridge deve subir antes do bot WhatsApp
    if _bridge_rodando():
        print(f"WhatsApp Bridge já rodando (PID {_ler_pid(BRIDGE_PID_FILE)}).")
    else:
        iniciar_bridge()

    if _whatsapp_rodando():
        print("WhatsApp bot já está rodando.")
    else:
        iniciar_whatsapp()

    if _triforce_daemon_rodando():
        print("TRIFORCE daemon já está rodando.")
    else:
        iniciar_triforce_daemon()

    if _majora_rodando():
        print(f"MAJORA watcher já rodando (PID {_ler_pid(MAJORA_PID)}).")
    else:
        iniciar_majora()

    if _mastersword_rodando():
        print(f"MASTERSWORD watcher já rodando (PID {_ler_pid(MASTERSWORD_PID)}).")
    else:
        iniciar_mastersword()

    if _itch_monitor_rodando():
        print(f"itch-monitor já rodando (PID {_ler_pid(ITCH_PID)}).")
    else:
        iniciar_itch_monitor()


def cmd_restart(limpar: bool = True):
    """Para tudo, opcionalmente limpa memória, reinicia."""
    parar_bot()
    parar_supervisor()
    parar_whatsapp()
    parar_bridge()
    parar_triforce_daemon()
    parar_majora()
    parar_mastersword()
    parar_itch_monitor()
    parar_proxy()
    time.sleep(1)
    if limpar:
        limpar_memoria()
    iniciar_proxy()
    iniciar_bot()
    iniciar_supervisor()
    iniciar_bridge()      # bridge antes do bot WA
    iniciar_whatsapp()
    iniciar_triforce_daemon()
    iniciar_majora()
    iniciar_mastersword()
    iniciar_itch_monitor()
    if limpar:
        _apagar_msgs_discord()


def cmd_stop():
    parar_bot()
    parar_supervisor()
    parar_whatsapp()
    parar_bridge()
    parar_triforce_daemon()
    parar_majora()
    parar_mastersword()
    parar_itch_monitor()
    parar_proxy()
    print("Serviços parados.")


def cmd_status():
    print(f"Hyrule Proxy: {'● rodando' if _proxy_rodando() else '○ parado'}")

    bot_ok = _bot_online()
    print(f"Discord bot:  {'● online' if bot_ok else '○ offline'}")

    pid_sup = _ler_pid(SUPERVISOR_PID_FILE)
    sup_ok = bool(pid_sup) and _pid_ativo(pid_sup)
    print(f"Supervisor:   {'● rodando' if sup_ok else '○ parado'}")

    print(f"WA Bridge:    {'● rodando' if _bridge_rodando() else '○ parado'} (porta {BRIDGE_PORT})")
    print(f"WhatsApp bot: {'● rodando' if _whatsapp_rodando() else '○ parado'}")
    print(f"FFmpeg:       {'● instalado' if _ffmpeg_disponivel() else '○ ausente'}")

    pid_tri = _ler_pid(TRIFORCE_DAEMON_PID)
    tri_ok = bool(pid_tri) and _pid_ativo(pid_tri)
    print(f"Triforce:     {'● rodando' if tri_ok else '○ parado'}")

    pid_mx = _ler_pid(MAJORA_PID)
    mx_ok = bool(pid_mx) and _pid_ativo(pid_mx)
    print(f"Majora:       {'● rodando' if mx_ok else '○ parado'}")

    pid_ms = _ler_pid(MASTERSWORD_PID)
    ms_ok = bool(pid_ms) and _pid_ativo(pid_ms)
    print(f"Mastersword:  {'● rodando' if ms_ok else '○ parado'}")

    itch_ok = _itch_monitor_rodando()
    print(f"itch-monitor: {'● rodando' if itch_ok else '○ parado'}")

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
