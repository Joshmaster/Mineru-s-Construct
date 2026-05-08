"""Skill: comandos de admin — só OWNER/OWNER_IDS podem usar."""

import json
import re
from pathlib import Path
from bot.core.router import Skill
from bot.core.context import MessageContext
from bot.core import access as access_ctl

CONFIG_PATH = Path(__file__).resolve().parents[2] / "config" / "config.json"


def _load_config() -> dict:
    return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))


def _save_config(cfg: dict):
    CONFIG_PATH.write_text(
        json.dumps(cfg, indent=2, ensure_ascii=False), encoding="utf-8"
    )


def _sender_id(ctx: MessageContext) -> str:
    return access_ctl.jid_user(ctx.sender_jid)


def _is_owner(ctx: MessageContext) -> bool:
    try:
        cfg = _load_config()
        return access_ctl.is_admin(ctx.sender_jid, ctx.chat_jid, _sender_id(ctx), cfg=cfg)
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

    if args.startswith("pend"):
        pend = access_ctl.load_pending()
        if not pend:
            await ctx.reply("sem pedido pendente")
            return
        lines = []
        for key, item in pend.items():
            status = "aguardando código do dono" if item.get("step") == "admin_code" else (
                "aguardando usuário repetir código" if item.get("code") else "sem código"
            )
            lines.append(
                f"• {status} - {item.get('name') or '(sem nome)'}\n"
                f"  físico/chat: `{item.get('phone') or '?'}`\n"
                f"  id recebido: `{item.get('sender_id') or key}`"
            )
        await ctx.reply("🔐 *Pendentes:*\n" + "\n".join(lines))
        return

    m_code = re.match(r"c[oó]digo\s+(\S+)\s+(\S+)", args)
    if m_code:
        key, item = access_ctl.find_pending_by_code_or_id(m_code.group(1))
        if not item:
            await ctx.reply("não achei esse pedido pendente")
            return
        access_ctl.upsert_pending(key, code=m_code.group(2), step="user_code")
        await ctx.reply(f"código salvo para {item.get('name') or key}")
        return

    m_ap = re.match(r"(aprova|aprovar|libera|liberar)\s+(\S+)", args)
    if m_ap:
        key, item = access_ctl.find_pending_by_code_or_id(m_ap.group(2))
        if not item:
            await ctx.reply("não achei esse pedido pendente")
            return
        added = access_ctl.add_allowed(item.get("sender_id"), item.get("phone"), item.get("chat_id"))
        access_ctl.pop_pending(key)
        await ctx.reply(f"liberado: {item.get('name') or key}\nadd: {', '.join(added) or 'já estava'}")
        return

    m_rec = re.match(r"(recusa|recusar|nega|negar)\s+(\S+)", args)
    if m_rec:
        key, item = access_ctl.find_pending_by_code_or_id(m_rec.group(2))
        if not item:
            await ctx.reply("não achei esse pedido pendente")
            return
        access_ctl.pop_pending(key)
        await ctx.reply(f"recusado: {item.get('name') or key}")
        return

    m = re.match(r"(add|del)\s+(\S+)", args)
    if not m:
        await ctx.reply(
            "Uso:\n"
            "`!acesso add [número/ID]`\n"
            "`!acesso del [número/ID]`\n"
            "`!acesso lista`\n"
            "`!acesso pendentes`\n"
            "`!acesso codigo [ID] [codigo]`\n"
            "`!acesso aprovar [código/ID]`"
        )
        return

    action, target = m.group(1), m.group(2)
    target_norm = "".join(c for c in target if c.isdigit()) or target

    if action == "add":
        added = access_ctl.add_allowed(target_norm)
        await ctx.reply(f"✅ `{target_norm}` adicionado." if added else f"Já tá na lista: `{target_norm}`")

    elif action == "del":
        if access_ctl.remove_allowed(target_norm):
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
