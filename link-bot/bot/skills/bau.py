"""Skill: salvar mídia recebida em pasta local - 'guarda no baú'."""

import os
import shutil
import time
from pathlib import Path
from bot.core.router import Skill
from bot.core.context import MessageContext


async def handle(ctx: MessageContext):
    if not ctx.has_media or not ctx.media_path:
        await ctx.reply(
            "Manda a mídia junto com o pedido, parceiro 📦\n"
            "_Ex: foto + legenda 'guarda no baú'_"
        )
        return

    if not os.path.exists(ctx.media_path):
        await ctx.reply("A mídia se perdeu pelo caminho 🌀")
        return

    # Pasta do baú: ~/.linkbot/bau/
    bau = Path.home() / ".linkbot" / "bau"
    bau.mkdir(parents=True, exist_ok=True)

    # Nome com timestamp + extensão original
    ext = Path(ctx.media_path).suffix or ".bin"
    timestamp = time.strftime("%Y%m%d-%H%M%S")
    media_kind = ctx.media_type or "media"
    new_name = f"{timestamp}_{media_kind}{ext}"
    dest = bau / new_name

    try:
        shutil.copy2(ctx.media_path, dest)
        size_kb = dest.stat().st_size / 1024
    except Exception as e:
        await ctx.reply(f"⚡ O baú trancou: {e}")
        return

    msg = (
        f"📦 *Guardado no baú!*\n"
        f"─────────────────\n"
        f"📁 {new_name}\n"
        f"💾 {size_kb:.1f} KB\n"
        f"📍 `{dest}`\n\n"
        f"_Pra ver tudo: 'meu baú'_"
    )
    await ctx.reply(msg)


async def handle_listar_bau(ctx: MessageContext):
    bau = Path.home() / ".linkbot" / "bau"
    if not bau.exists():
        await ctx.reply("📦 O baú está vazio, parceiro.")
        return

    arquivos = sorted(bau.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True)
    if not arquivos:
        await ctx.reply("📦 O baú está vazio, parceiro.")
        return

    total_size = sum(f.stat().st_size for f in arquivos) / (1024 * 1024)

    lines = [f"📦 *Baú do Aventureiro* ({len(arquivos)} itens, {total_size:.1f} MB)",
             "─────────────────"]
    for f in arquivos[:15]:
        size_kb = f.stat().st_size / 1024
        lines.append(f"• {f.name} ({size_kb:.0f} KB)")

    if len(arquivos) > 15:
        lines.append(f"\n_... e mais {len(arquivos) - 15} itens_")

    lines.append(f"\n📍 `{bau}`")
    await ctx.reply("\n".join(lines))


SKILLS = [
    Skill(
        name="bau_save",
        description="*guarda no baú* — salvar mídia recebida (envie mídia)",
        triggers=[
            "!bau", "guarda no bau", "guarda no baú",
            "guardar no bau", "guardar no baú",
            "salva isso", "salvar isso", "guarda isso",
        ],
        handler=handle,
        category="midia",
        requires_media=True,
    ),
    Skill(
        name="bau_list",
        description="*meu baú* — listar arquivos guardados",
        triggers=["meu bau", "meu baú", "ver bau", "ver baú",
                  "lista do bau", "lista do baú"],
        handler=handle_listar_bau,
        category="midia",
        priority=9,
    ),
]


SKILL = SKILLS
