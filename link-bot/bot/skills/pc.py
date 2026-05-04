"""Skill: controle do PC - abrir programa, CPU/RAM, volume, screenshot.

DESATIVADA por padrão. Pra ligar: ENABLE_PC_CONTROL=true no config.

Suporta Windows, Linux e Termux (com adaptações).
Cada comando do PC requer OWNER ter pedido EXPLICITAMENTE.
"""

import asyncio
import os
import platform
import shutil
import sys
import tempfile
from pathlib import Path
from bot.core.router import Skill
from bot.core.context import MessageContext


def is_enabled(ctx: MessageContext) -> bool:
    return bool(ctx.config.get("ENABLE_PC_CONTROL", False))


async def _check_or_warn(ctx: MessageContext) -> bool:
    if not is_enabled(ctx):
        await ctx.reply(
            "💻 Os Zonai constructs estão desativados, parceiro 🔒\n"
            "Pra ligar: edita o config e bota `ENABLE_PC_CONTROL=true`,\n"
            "depois reinicia o bot.\n\n"
            "_Cuidado: liga só se você confia que ninguém mais manda msg_\n"
            "_pro número do bot — comandos do PC são poderosos._"
        )
        return False
    return True


async def _run(cmd: list, timeout: int = 10) -> tuple:
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout, stderr = await asyncio.wait_for(
            proc.communicate(), timeout=timeout
        )
    except asyncio.TimeoutError:
        proc.kill()
        return -1, "", "timeout"
    return (
        proc.returncode,
        stdout.decode(errors="replace"),
        stderr.decode(errors="replace"),
    )


# ============ ABRIR PROGRAMA ============

PROGRAM_ALIASES_WIN = {
    "chrome": "chrome",
    "firefox": "firefox",
    "edge": "msedge",
    "spotify": "spotify",
    "explorador": "explorer",
    "explorer": "explorer",
    "notepad": "notepad",
    "bloco de notas": "notepad",
    "calculadora": "calc",
    "calc": "calc",
    "vscode": "code",
    "vs code": "code",
    "code": "code",
    "terminal": "wt",
    "powershell": "powershell",
    "cmd": "cmd",
    "discord": "discord",
}


async def handle_abrir(ctx: MessageContext):
    if not await _check_or_warn(ctx):
        return

    args = ctx.args_text.lower().strip()
    if not args:
        await ctx.reply("Abrir o quê, parceiro? 💻")
        return

    sysname = platform.system()
    if sysname == "Windows":
        # tenta resolver alias
        prog = PROGRAM_ALIASES_WIN.get(args, args)
        try:
            # start abre como o user esperaria (Spotify, etc)
            os.startfile(prog) if hasattr(os, "startfile") else None
            # fallback shell
            proc = await asyncio.create_subprocess_shell(f"start {prog}")
            await ctx.reply(f"🌀 Ativando {prog}...")
        except Exception as e:
            await ctx.reply(f"⚡ O construct não respondeu: {e}")
    elif sysname == "Linux":
        # Tenta xdg-open
        if shutil.which(args):
            await asyncio.create_subprocess_shell(f"{args} &")
            await ctx.reply(f"🌀 Ativando {args}...")
        else:
            await ctx.reply(f"🌀 '{args}' não tá nos meus constructs Linux.")
    else:
        await ctx.reply("🌀 Esse reino não suporta abrir programas pelo bot.")


# ============ CPU / RAM ============

async def handle_status_pc(ctx: MessageContext):
    if not await _check_or_warn(ctx):
        return

    sysname = platform.system()
    msg_lines = ["💻 *Status do Reino (PC)*", "─────────────────"]

    # Tenta psutil se disponível (mais bonito), senão fallback
    try:
        import psutil
        cpu = psutil.cpu_percent(interval=0.5)
        mem = psutil.virtual_memory()
        mem_used_gb = mem.used / (1024**3)
        mem_total_gb = mem.total / (1024**3)
        disk = psutil.disk_usage("/")
        disk_pct = disk.percent

        msg_lines.append(f"⚙️ CPU: {cpu:.1f}%")
        msg_lines.append(
            f"🧠 RAM: {mem.percent:.1f}% "
            f"({mem_used_gb:.1f} / {mem_total_gb:.1f} GB)"
        )
        msg_lines.append(f"💾 Disco: {disk_pct:.1f}%")
    except ImportError:
        # fallback sem psutil
        if sysname == "Windows":
            rc, out, _ = await _run(
                ["wmic", "OS", "get", "FreePhysicalMemory,TotalVisibleMemorySize", "/value"]
            )
            msg_lines.append("(psutil não instalado — só info básica)")
            msg_lines.append(f"OS: {sysname}")
        else:
            rc, out, _ = await _run(["free", "-h"])
            msg_lines.append("```")
            msg_lines.append(out[:500])
            msg_lines.append("```")

    await ctx.reply("\n".join(msg_lines))


# ============ VOLUME ============

async def handle_volume(ctx: MessageContext):
    if not await _check_or_warn(ctx):
        return

    import re
    m = re.search(r"\d+", ctx.args_text)
    if not m:
        await ctx.reply("Volume pra quanto, parceiro? _Ex: 'volume 50'_")
        return
    target = max(0, min(int(m.group(0)), 100))

    sysname = platform.system()
    if sysname == "Windows":
        # PowerShell + Windows Audio API via NAudio é complicado; vamos via SendKeys
        ps_script = f"""
$wshell = New-Object -ComObject wscript.shell
# Mute primeiro pra zerar
1..50 | %{{ $wshell.SendKeys([char]174) }}
# Sobe pro target (cada step = 2%)
1..({target}/2) | %{{ $wshell.SendKeys([char]175) }}
"""
        rc, _o, _e = await _run(["powershell", "-Command", ps_script], timeout=8)
        if rc == 0:
            await ctx.reply(f"🔊 Volume ajustado pra ~{target}%.")
        else:
            await ctx.reply("🌀 Não consegui ajustar o volume.")
    else:
        await ctx.reply("🌀 Comando de volume só implementado no Windows por enquanto.")


# ============ SCREENSHOT ============

async def handle_screenshot(ctx: MessageContext):
    if not await _check_or_warn(ctx):
        return

    out = str(Path(tempfile.gettempdir()) / "link_screenshot.png")

    sysname = platform.system()
    try:
        if sysname == "Windows":
            ps_script = f"""
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
$bounds = [System.Windows.Forms.Screen]::PrimaryScreen.Bounds
$bmp = New-Object System.Drawing.Bitmap $bounds.Width, $bounds.Height
$g = [System.Drawing.Graphics]::FromImage($bmp)
$g.CopyFromScreen($bounds.Location, [System.Drawing.Point]::Empty, $bounds.Size)
$bmp.Save('{out.replace(chr(92), "/")}', [System.Drawing.Imaging.ImageFormat]::Png)
$g.Dispose(); $bmp.Dispose()
"""
            rc, _o, err = await _run(["powershell", "-Command", ps_script], timeout=15)
        else:
            # Linux: tenta scrot, gnome-screenshot
            for tool in ["scrot", "gnome-screenshot", "import"]:
                if shutil.which(tool):
                    if tool == "import":
                        rc, _, _ = await _run([tool, "-window", "root", out])
                    elif tool == "gnome-screenshot":
                        rc, _, _ = await _run([tool, "-f", out])
                    else:
                        rc, _, _ = await _run([tool, out])
                    if rc == 0:
                        break
            else:
                await ctx.reply("🌀 Sem ferramenta de screenshot (instala scrot ou gnome-screenshot).")
                return
            rc = 0

        if rc != 0 or not os.path.exists(out):
            await ctx.reply("⚡ A runa de captura falhou.")
            return

        await ctx.reply_media(out, caption="📸 Captura do reino")
    except Exception as e:
        await ctx.reply(f"⚡ Erro: {e}")


SKILLS = [
    Skill(
        name="pc_abrir",
        description="*abre <programa>* — ativar Zonai construct (DESATIVADO por padrão)",
        triggers=["abre", "abrir", "executa", "executar", "inicia"],
        handler=handle_abrir,
        category="pc",
        enabled=True,  # skill sempre registrada, mas handler verifica flag
    ),
    Skill(
        name="pc_status",
        description="*cpu* / *ram* / *uso do pc* — espíritos do reino",
        triggers=[
            "cpu", "ram", "memoria do pc", "memória do pc",
            "uso do pc", "status do pc", "como ta a maquina",
        ],
        handler=handle_status_pc,
        category="pc",
    ),
    Skill(
        name="pc_volume",
        description="*volume N* — ajustar som",
        triggers=["volume"],
        handler=handle_volume,
        category="pc",
    ),
    Skill(
        name="pc_screenshot",
        description="*tira print* / *screenshot* — captura da tela",
        triggers=["tira print", "tira screenshot", "screenshot", "captura tela",
                  "print da tela"],
        handler=handle_screenshot,
        category="pc",
    ),
]


SKILL = SKILLS
