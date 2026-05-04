"""Skill: comandos de admin — só o dono pode usar.

O dono é definido diretamente no config.json (campo OWNER).
Não existe auto-registro — só quem já está no config é dono.

!acesso add [id]   → adiciona número/LID à allow_list
!acesso del [id]   → remove número/LID da allow_list
!acesso lista      → mostra quem tem acesso
!dono              → confirma se você é o dono
"""

import json
import re
from pathlib import Path
from bot.core.router import Skill
from bot.core.context import MessageContext

CONFIG_PATH = Path(__file__).resolve().parents[2] / "config" / "config.json"


def _load_config() -> dict:
    return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))


def _save_config(cfg: dict):
    CONFIG_PATH.write_text(
        json.dumps(cfg, indent=2, ensure_ascii=False), encoding="utf-8"
    )


def _sender_id(ctx: MessageContext) -> str:
    return str(getattr(ctx.sender_jid, "User", "")) or str(ctx.sender_jid)


def _is_owner(ctx: MessageContext) -> bool:
    try:
        cfg = _load_config()
        owner = cfg.get("OWNER", "")
        return bool(owner) and _sender_id(ctx) == str(owner)
    except Exception:
        return False


# ── !acesso ──────────────────────────────────────────────────────────────────

async def handle_acesso(ctx: MessageContext):
    if not _is_owner(ctx):
        await ctx.reply("🔒 Só o dono pode mexer no acesso.")
        return

    args = ctx.args_text.strip().lower()
    cfg = _load_config()
    allow = cfg.get("ALLOW_FROM", [])

    if args.startswith("lista") or args == "":
        if not allow:
            await ctx.reply("📋 Lista vazia.")
            return
        lines = "\n".join(f"  • `{x}`" for x in allow)
        await ctx.reply(f"📋 *Com acesso:*\n{lines}")
        return

    m = re.match(r"(add|del)\s+(\S+)", args)
    if not m:
        await ctx.reply(
            "Uso:\n"
            "`!acesso add [número/ID]`\n"
            "`!acesso del [número/ID]`\n"
            "`!acesso lista`"
        )
        return

    action, target = m.group(1), m.group(2)
    target_norm = "".join(c for c in target if c.isdigit()) or target

    if action == "add":
        if target_norm not in allow:
            allow.append(target_norm)
            cfg["ALLOW_FROM"] = allow
            _save_config(cfg)
            await ctx.reply(f"✅ `{target_norm}` adicionado.")
        else:
            await ctx.reply(f"Já tá na lista: `{target_norm}`")

    elif action == "del":
        if target_norm in allow:
            allow.remove(target_norm)
            cfg["ALLOW_FROM"] = allow
            _save_config(cfg)
            await ctx.reply(f"🗑️ `{target_norm}` removido.")
        else:
            await ctx.reply(f"Não achei `{target_norm}` na lista.")


# ── !dono ─────────────────────────────────────────────────────────────────────

async def handle_dono(ctx: MessageContext):
    if _is_owner(ctx):
        await ctx.reply("🔱 Você é o dono desse sistema, parceiro.")
    else:
        await ctx.reply("🔒 Você não é o dono.")


SKILL = [
    Skill(
        name="admin_acesso",
        description="`!acesso` — gerenciar acesso (só dono)",
        triggers=["!acesso"],
        handler=handle_acesso,
        category="admin",
        priority=20,
    ),
    Skill(
        name="admin_dono",
        description="`!dono` — confirmar se você é o dono",
        triggers=["!dono"],
        handler=handle_dono,
        category="admin",
        priority=20,
    ),
]
