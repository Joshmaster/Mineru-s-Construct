#!/usr/bin/env python3
"""
Link Bot - Launcher Principal
==============================
Conecta no WhatsApp via bridge Baileys, carrega todas as skills,
roteia mensagens, dispara lembretes em background.

Uso:
    python -m bot.main           # roda normal
    python -m bot.main --reset   # apaga sessão Baileys e re-pareia

Config: ler config/config.json (criado pelo personalizar.sh/.bat).
"""

import asyncio
import importlib
import json
import logging
import os
import re
import shutil
import sys
import tempfile
import threading
import time
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import List
from zoneinfo import ZoneInfo
import unicodedata

# Garante que pasta raiz tá no path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

try:
    from aiohttp import web as aiohttp_web
except ImportError:
    print("❌ Falta aiohttp. Instala com:  pip install aiohttp")
    sys.exit(1)

from bot.core.whatsapp_client import WhatsAppClient, build_jid, _Jid
from bot.core.router import Router, Skill
from bot.core.context import MessageContext
from bot.core.storage import Storage
from bot.core.scheduler import ReminderScheduler
from bot.core import llm as _llm
from bot.core import access as access_ctl
from bot.core import meta_ai as _meta_ai


# ===================== CONFIG / LOG =====================

class BrazilFormatter(logging.Formatter):
    def formatTime(self, record, datefmt=None):
        dt = datetime.fromtimestamp(record.created, ZoneInfo("America/Sao_Paulo"))
        return dt.strftime(datefmt or "%d/%m/%Y %H:%M:%S")


_handler = logging.StreamHandler()
_handler.setFormatter(BrazilFormatter(
    "%(asctime)s [%(name)s] %(message)s",
    datefmt="%d/%m/%Y %H:%M:%S",
))
logging.basicConfig(level=logging.INFO, handlers=[_handler], force=True)
for noisy in ("aiohttp", "aiohttp.access"):
    logging.getLogger(noisy).setLevel(logging.WARNING)

log = logging.getLogger("link-bot")

MEDIA_RETENTION_SECONDS = 24 * 60 * 60
INBOX_DIR = Path.home() / ".linkbot" / "inbox"
GENERATED_MEDIA_DIRS = [
    ROOT / ".linkbot" / "reminder_cards",
]
SENT_MESSAGES_FILE = ROOT / ".linkbot" / "sent_messages.json"


def _norm_text(text: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFD", (text or "").lower())
        if unicodedata.category(c) != "Mn"
    )


def _fallback_reaction(category: str = "") -> str:
    return ""


def _clean_natural_args(text: str, words: tuple[str, ...]) -> str:
    """Remove palavras de ativação comuns, preservando o pedido útil."""
    import re
    cleaned = re.sub(r"^\s*(?:link|ei\s+link|ô\s+link|o\s+link)[,:\s-]*", "", text or "", flags=re.IGNORECASE)
    cleaned = re.sub(r"!\w+", " ", cleaned)
    for word in words:
        cleaned = re.sub(rf"\b{re.escape(word)}\b", " ", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" :,-")
    return cleaned or (text or "").strip()


def _looks_like_media_request(text: str) -> bool:
    norm = _norm_text(text)
    action = any(w in norm for w in (
        "toca", "tocar", "coloca", "baixa", "baixar", "manda", "enviar",
        "procura", "busca", "buscar", "pega", "download",
    ))
    media = any(w in norm for w in (
        "musica", "audio", "mp3", "video", "mp4", "youtube", "yutube",
        "youtu", "!yt", " yt ", "spotify", "insta", "instagram", "reel", "twitter", "x.com",
    ))
    return action and media


def _looks_like_contextual_music_request(text: str) -> bool:
    norm = _norm_text(text)
    return bool(norm) and any(x in norm for x in (
        "outra famosa", "outro famoso", "mais famosa", "mais famoso",
        "outra musica", "outra musica", "mais uma", "da mesma banda",
        "desse artista", "dessa banda", "parecida com essa", "nesse estilo",
        "mais outra", "outra dela", "outra dele", "outra deles",
        "do mesmo artista", "do mesmo estilo", "mesmo genero", "mesmo genero",
        # frases casuais curtas
        "outra ai", "outro ai", "baixa outra", "manda outra",
        "manda mais uma", "mais uma ai", "mais um ai", "outra igual",
        "uma parecida", "outra do mesmo", "do mesmo", "da mesma",
        "manda mais", "coloca outra", "bota outra",
    ))


def _looks_like_delete_bot_messages(text: str) -> bool:
    norm = _norm_text(text)
    if not any(w in norm for w in ("apag", "delet", "exclu", "limpa", "limpar", "remove", "remov")):
        return False
    if any(w in norm for w in ("lembrete", "tarefa", "missao", "nota", "anotacao", "anotacoes")):
        return False
    return any(w in norm for w in (
        "mensag", "msg", "msgs", "chat", "conversa", "historico",
        "audio", "audios", "midia", "midias", "arquivo", "arquivos",
        "suas", "seus", "voce mandou", "tu mandou", "do bot", "tudo",
        "hoje",
    ))


def _delete_count_from_text(text: str) -> int:
    norm = _norm_text(text)
    m = re.search(r"\b(\d{1,3})\b", norm)
    if m:
        return max(1, min(int(m.group(1)), 50))
    if any(w in norm for w in ("ultima", "ultimo", "essa", "esta", "isso")):
        return 1
    if any(w in norm for w in ("tudo", "todas", "todos", "historico", "chat", "conversa", "hoje")):
        return 50
    return 20


def _load_sent_messages() -> dict[str, list[dict]]:
    try:
        if SENT_MESSAGES_FILE.exists():
            data = json.loads(SENT_MESSAGES_FILE.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return {
                    str(chat): [item for item in items if isinstance(item, dict)]
                    for chat, items in data.items()
                    if isinstance(items, list)
                }
    except Exception:
        pass
    return {}


def _save_sent_messages(data: dict[str, list[dict]]):
    try:
        SENT_MESSAGES_FILE.parent.mkdir(parents=True, exist_ok=True)
        SENT_MESSAGES_FILE.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    except Exception as e:
        log.debug(f"não consegui salvar sent_messages: {e}")


def _cleanup_old_media() -> int:
    cutoff = time.time() - MEDIA_RETENTION_SECONDS
    removed = 0
    for folder in [INBOX_DIR, *GENERATED_MEDIA_DIRS]:
        if not folder.exists():
            continue
        for path in folder.iterdir():
            if not path.is_file():
                continue
            try:
                if path.stat().st_mtime < cutoff:
                    path.unlink()
                    removed += 1
            except Exception as e:
                log.warning(f"Não consegui limpar mídia expirada {path}: {e}")
    return removed


def load_config() -> dict:
    """Carrega config/config.json e expande env vars ${VAR}."""
    path = ROOT / "config" / "config.json"
    if not path.exists():
        log.error(f"Config não encontrado: {path}")
        log.error("Roda o script personalizar primeiro.")
        sys.exit(1)

    with open(path, encoding="utf-8") as f:
        raw = f.read()

    import re
    def replace(m):
        var = m.group(1)
        return os.environ.get(var, "")
    raw = re.sub(r"\$\{(\w+)\}", replace, raw)

    return json.loads(raw)


# ===================== SKILL LOADER =====================

def load_all_skills(router: Router):
    """Importa cada skill em bot/skills/ e registra no router."""
    skills_dir = ROOT / "bot" / "skills"
    loaded = 0
    failed = []

    for f in sorted(skills_dir.glob("*.py")):
        if f.name.startswith("_"):
            continue
        mod_name = f"bot.skills.{f.stem}"
        try:
            mod = importlib.import_module(mod_name)
            skill_obj = getattr(mod, "SKILL", None)
            if skill_obj is None:
                continue
            if isinstance(skill_obj, list):
                for s in skill_obj:
                    router.register(s)
                    loaded += 1
            else:
                router.register(skill_obj)
                loaded += 1
        except Exception as e:
            failed.append((f.name, str(e)))

    log.info(f"📜 Skills carregadas: {loaded}")
    if failed:
        for name, err in failed:
            log.warning(f"  ⚠️ {name}: {err}")

    # Monta catálogo de skills e injeta no LLM para que saiba responder sobre comandos
    try:
        linhas = []
        for skill in router.list_enabled():
            # Usa apenas a primeira linha da description para manter o catálogo compacto
            desc_curta = (skill.description or "").split("\n")[0].strip()
            # Remove markdown bold (*texto*) para ficar limpo no system prompt
            desc_curta = desc_curta.replace("*", "")
            triggers_str = ", ".join(skill.triggers[:3]) if skill.triggers else ""
            linhas.append(f"- {triggers_str}: {desc_curta}")
        _llm.set_skill_catalog("\n".join(linhas))
    except Exception as e:
        log.warning(f"Não foi possível montar catálogo de skills para o LLM: {e}")

    return loaded


# ===================== BOT =====================

class LinkBot:
    def __init__(self, config: dict):
        self.config = config

        # Storage
        store_path = config.get("STORAGE_PATH",
                                str(Path.home() / ".linkbot" / "data.db"))
        self.storage = Storage(store_path)
        access_ctl.migrate_config_contacts(config)

        # Router
        self.router = Router()
        load_all_skills(self.router)

        # JIDs reais por número (populado quando mensagem chega)
        self.user_jids: dict = {}
        self.last_media: dict = {}
        self.sent_music_context: dict[str, dict] = {}
        self.last_music_by_chat: dict[str, dict] = {}  # chat_jid_str → {context, ts}
        self.sent_messages_by_chat: dict[str, list[dict]] = _load_sent_messages()  # chat_jid_str → [{id, ts}]

        # Bot identity
        self.my_jid = None
        self.my_lid = ""  # LID usado em menções de grupo (@lid)

        # Lembretes aguardando confirmação de reação:
        # {stanza_id: {text, target_jid_str, next_retry, retry_count}}
        self._pending_reminder_ack: dict[str, dict] = {}
        self._retry_task = None
        self._media_cleanup_task = None

        # Clarificação de skill pendente: sender_number → (skill_name, msg_original, ts, retries)
        self._pending_clarification: dict[str, tuple[str, str, float, int]] = {}

        # Allow/admin list
        self.allow_list = list(access_ctl.allow_keys(config))
        self.admin_list = list(access_ctl.admin_keys(config))

        # Bridge URL (configurável)
        bridge_url = config.get("BRIDGE_URL", "http://localhost:7334")
        self.client = WhatsAppClient(bridge_url)

        # Meta AI proxy (sem token — usa chat do WhatsApp)
        _meta_ai.proxy.setup(self.client, config.get("META_AI_JID", ""))

        # Scheduler
        self.scheduler = ReminderScheduler(
            self.storage, self._send_reminder
        )

    # ── Startup ──────────────────────────────────────────────────────────────

    async def _on_connected(self):
        log.info("🟢 Conectado ao WhatsApp (bridge Baileys).")
        try:
            me = await self.client.get_me()
            self.my_jid = me.JID
            self.my_lid = getattr(me, "LID", "")
        except Exception:
            pass
        await self.scheduler.start()
        if self._retry_task is None or self._retry_task.done():
            self._retry_task = asyncio.create_task(self._reminder_retry_loop())
        removed = _cleanup_old_media()
        if removed:
            log.info(f"🧹 Mídias temporárias expiradas removidas: {removed}")
        if self._media_cleanup_task is None or self._media_cleanup_task.done():
            self._media_cleanup_task = asyncio.create_task(self._media_cleanup_loop())

    async def _media_cleanup_loop(self):
        while True:
            await asyncio.sleep(60 * 60)
            removed = _cleanup_old_media()
            if removed:
                log.info(f"🧹 Mídias temporárias expiradas removidas: {removed}")

    # ── Lembretes ─────────────────────────────────────────────────────────────

    def _reminder_jid_candidates(self, user_jid_str: str):
        cfg = load_config()
        keys = access_ctl.identity_keys(user_jid_str)
        record = access_ctl.contact_record(*keys)
        if record:
            keys.extend(record.get("aliases") or [])

        if set(keys) & set(self.admin_list):
            keys.extend(cfg.get("OWNER_IDS", []) or [])
            owner = cfg.get("OWNER")
            if owner:
                keys.append(owner)

        seen = set()
        for key in access_ctl.identity_keys(*keys):
            dig = access_ctl.digits(key)
            if not dig:
                continue
            jid = build_jid(dig)
            marker = str(jid)
            if marker and marker not in seen:
                seen.add(marker)
                yield jid

    async def _send_reminder(self, user_jid_str: str, text: str,
                             image_path: str | None = None, *, send_to: str = ""):
        resp = None

        if not send_to:
            send_to = str(self.config.get("REMINDERS_GROUP_JID", "") or "").strip()

        if send_to and "@g.us" in send_to:
            try:
                jid = build_jid(send_to.split("@")[0], "g.us")
                if image_path:
                    resp = await asyncio.wait_for(
                        self.client.send_image(jid, image_path, caption=text or None),
                        timeout=25,
                    )
                else:
                    resp = await asyncio.wait_for(self.client.send_message(jid, text), timeout=25)
                log.info(f"Reminder entregue no grupo {send_to}")
                self._register_reminder_ack(resp, text, send_to)
                return
            except Exception as e:
                log.warning(f"Falha enviando reminder no grupo {send_to}: {e}")

        last_error = None
        for jid in self._reminder_jid_candidates(user_jid_str):
            marker = str(jid)
            try:
                if image_path:
                    resp = await asyncio.wait_for(
                        self.client.send_image(jid, image_path, caption=text or None),
                        timeout=25,
                    )
                else:
                    resp = await asyncio.wait_for(self.client.send_message(jid, text), timeout=25)
                log.info(f"Reminder entregue via {marker}")
                self._register_reminder_ack(resp, text, marker)
                return
            except Exception as e:
                last_error = e
                log.warning(f"Falha enviando reminder via {marker}: {e}")

        try:
            jid = build_jid(user_jid_str)
            if image_path:
                resp = await asyncio.wait_for(
                    self.client.send_image(jid, image_path, caption=text or None),
                    timeout=25,
                )
            else:
                resp = await asyncio.wait_for(self.client.send_message(jid, text), timeout=25)
            log.info(f"Reminder entregue via fallback {user_jid_str}")
            self._register_reminder_ack(resp, text, user_jid_str)
        except Exception as e:
            log.error(f"Falha enviando reminder: {e or last_error}")
            raise

    def _register_reminder_ack(self, resp, text: str, target: str):
        msg_id = str(getattr(resp, 'ID', '') or getattr(resp, 'ServerID', '') or '')
        if not msg_id:
            return
        self._pending_reminder_ack[msg_id] = {
            'text': text,
            'target': target,
            'next_retry': int(time.time()) + 15 * 60,
            'retry_count': 0,
        }
        log.info(f"Reminder pendente de confirmação: {msg_id}")

    async def _reminder_retry_loop(self):
        RETRY_INTERVAL = 15 * 60
        while True:
            await asyncio.sleep(60)
            now = int(time.time())
            to_retry = [
                (sid, info) for sid, info in list(self._pending_reminder_ack.items())
                if info.get('next_retry', 0) <= now
            ]
            for sid, info in to_retry:
                self._pending_reminder_ack.pop(sid, None)
                target = info.get('target', '')
                retry_text = f"⏰ (sem confirmação — tentativa {info['retry_count'] + 1})\n{info['text']}"
                try:
                    if '@g.us' in target:
                        jid = build_jid(target.split('@')[0], 'g.us')
                    else:
                        jid = build_jid(target.split('@')[0]) if '@' in target else build_jid(target)
                    resp = await asyncio.wait_for(
                        self.client.send_message(jid, retry_text), timeout=25
                    )
                    new_id = str(getattr(resp, 'ID', '') or '')
                    if new_id:
                        self._pending_reminder_ack[new_id] = {
                            **info,
                            'next_retry': now + RETRY_INTERVAL,
                            'retry_count': info['retry_count'] + 1,
                        }
                    log.info(f"Reminder retry #{info['retry_count'] + 1} enviado para {target}")
                except Exception as e:
                    log.error(f"Falha no retry de reminder para {target}: {e}")

    # ── Allow / Admin ─────────────────────────────────────────────────────────

    def _reload_allow_list(self):
        try:
            cfg = load_config()
            self.allow_list = list(access_ctl.allow_keys(cfg))
            self.admin_list = list(access_ctl.admin_keys(cfg))
        except Exception:
            pass

    def _is_allowed(self, *ids) -> bool:
        self._reload_allow_list()
        if not self.allow_list:
            return False
        return bool(set(access_ctl.identity_keys(*ids)) & set(self.allow_list))

    def _is_admin(self, *ids) -> bool:
        self._reload_allow_list()
        return bool(set(access_ctl.identity_keys(*ids)) & set(self.admin_list))

    # ── AI match ─────────────────────────────────────────────────────────────

    def _ai_match_skill(self, text: str):
        skill_items = [
            {"name": s.name, "description": f"{s.description}\nAliases: {', '.join(s.triggers[:8])}"}
            for s in self.router.list_enabled()
            if s.enabled
        ]
        intent = _llm.classify_skill_intent(text, skill_items)
        if intent is None:
            return None
        if not intent.get("skill"):
            return False
        skill_name = str(intent["skill"]).strip()
        args = str(intent.get("args", text) or "").strip()
        skill = self.router.get_by_name(skill_name)
        if skill is None and skill_name.startswith(("!", "[")):
            command_match = self.router.match(f"{skill_name} {args}".strip())
            if command_match:
                return command_match
        if skill is None and args.startswith(("!", "[")):
            command_match = self.router.match(args)
            if command_match:
                return command_match
        if skill is None:
            return False
        return skill, args

    def _natural_match_skill(self, text: str):
        """Atalhos determinísticos para pedidos naturais que não devem depender do LLM."""
        norm = _norm_text(text)

        if _looks_like_media_request(text):
            skill = self.router.get_by_name("delirius_dl")
            if skill:
                args = _clean_natural_args(text, (
                    "link", "toca", "tocar", "coloca", "baixa", "baixar", "manda",
                    "enviar", "procura", "busca", "buscar", "pega", "download",
                    "uma", "um", "a", "o", "pra", "para", "por favor",
                ))
                return skill, args

        if any(w in norm for w in ("gera imagem", "gerar imagem", "cria imagem", "criar imagem", "desenha", "ilustra")):
            skill = self.router.get_by_name("img_gerar")
            if skill:
                return skill, _clean_natural_args(text, ("gera", "gerar", "cria", "criar", "imagem", "desenha", "ilustra"))

        if "gif" in norm:
            skill = self.router.get_by_name("delirius_gif")
            if skill:
                return skill, _clean_natural_args(text, ("manda", "me manda", "busca", "procura", "gif", "de", "um", "uma"))

        if any(w in norm for w in ("fala em voz", "le em voz", "lê em voz", "narra", "tts", "audio falando")):
            skill = self.router.get_by_name("delirius_fala")
            if skill:
                return skill, _clean_natural_args(text, ("fala em voz alta", "fala", "ler", "le", "lê", "em voz alta", "narra", "tts"))

        return None

    def _safe_direct_match(self, match):
        """Evita que conversa comum vire comando por trigger ampla demais."""
        if not match:
            return None
        skill, rest = match
        if skill.name in {"status", "identidade", "ping", "info"} and not (rest or "").strip():
            return None
        return match

    def _remember_sent_music(self, message_id: str, context: str, chat_jid_str: str = ""):
        context = (context or "").strip()
        if not message_id or not context:
            return
        entry = {"context": context[:500], "ts": time.time()}
        self.sent_music_context[str(message_id)] = entry
        if chat_jid_str:
            self.last_music_by_chat[str(chat_jid_str)] = entry
        # Limpeza simples para não acumular IDs antigos.
        cutoff = time.time() - 6 * 60 * 60
        for mid, item in list(self.sent_music_context.items()):
            if float(item.get("ts") or 0) < cutoff:
                self.sent_music_context.pop(mid, None)

    def _remember_sent_message(self, chat_jid_str: str, message_id: str):
        message_id = str(message_id or "").strip()
        chat_jid_str = str(chat_jid_str or "").strip()
        if not message_id or not chat_jid_str:
            return
        items = self.sent_messages_by_chat.setdefault(chat_jid_str, [])
        if any(item.get("id") == message_id for item in items):
            return
        items.append({"id": message_id, "ts": time.time()})
        cutoff = time.time() - 24 * 60 * 60
        self.sent_messages_by_chat[chat_jid_str] = [
            item for item in items[-120:]
            if float(item.get("ts") or 0) >= cutoff
        ]
        _save_sent_messages(self.sent_messages_by_chat)

    async def _handle_delete_bot_messages(self, chat_jid, chat_jid_str: str, text: str, quoted_id: str = "") -> bool:
        count = _delete_count_from_text(text)
        targets: list[str] = []
        norm = _norm_text(text)
        silent_cleanup = any(w in norm for w in (
            "tudo", "todas", "todos", "historico", "chat", "conversa",
            "hoje", "limpa", "limpar",
        ))
        if quoted_id and any(w in norm for w in ("essa", "esta", "isso", "mensagem marcada", "marcada", "respondida")):
            targets.append(str(quoted_id))
        items = self.sent_messages_by_chat.get(str(chat_jid_str), [])
        for item in reversed(items):
            mid = str(item.get("id") or "")
            if mid and mid not in targets:
                targets.append(mid)
            if len(targets) >= count:
                break

        if not targets:
            if silent_cleanup:
                return True
            resp = await self.client.send_message(chat_jid, "não tenho mensagem recente minha pra apagar aqui")
            self._remember_sent_message(chat_jid_str, getattr(resp, "ID", "") or getattr(resp, "ServerID", ""))
            return True

        deleted = 0
        for mid in targets:
            if await self.client.delete_message(chat_jid, mid):
                deleted += 1
        if deleted:
            known = self.sent_messages_by_chat.get(str(chat_jid_str), [])
            removed = set(targets)
            self.sent_messages_by_chat[str(chat_jid_str)] = [
                item for item in known if item.get("id") not in removed
            ]
            _save_sent_messages(self.sent_messages_by_chat)
        if silent_cleanup:
            return True
        msg = f"apaguei {deleted} mensagem(ns) minha(s)" if deleted else "não consegui apagar minhas mensagens agora"
        resp = await self.client.send_message(chat_jid, msg)
        self._remember_sent_message(chat_jid_str, getattr(resp, "ID", "") or getattr(resp, "ServerID", ""))
        return True

    def _quoted_music_context(self, quoted_id: str, quoted_text: str = "", chat_jid_str: str = "") -> str:
        if quoted_id:
            item = self.sent_music_context.get(str(quoted_id)) or {}
            if item.get("context"):
                return str(item["context"])
        text = (quoted_text or "").strip()
        if text:
            norm = _norm_text(text)
            if "spotify:" in norm or "youtube:" in norm or "audio do youtube" in norm or text.startswith("🎵"):
                return text[:500]
        # Fallback: última música enviada neste chat (sem precisar de reply)
        if chat_jid_str:
            item = self.last_music_by_chat.get(str(chat_jid_str)) or {}
            if item.get("context") and time.time() - float(item.get("ts") or 0) < 6 * 3600:
                return str(item["context"])
        return ""

    # ── JID candidates ────────────────────────────────────────────────────────

    def _jid_candidates_for_target(self, target: str):
        keys = access_ctl.identity_keys(target)
        record = access_ctl.contact_record(*keys)
        if record:
            keys.extend(record.get("aliases") or [])

        seen = set()
        candidates = []
        for key in access_ctl.identity_keys(*keys):
            cached = self.user_jids.get(key) or self.user_jids.get(access_ctl.digits(key))
            if cached is not None:
                marker = str(cached)
                if marker not in seen:
                    seen.add(marker)
                    candidates.append(cached)

        for key in access_ctl.identity_keys(*keys):
            dig = access_ctl.digits(key)
            if not dig:
                continue
            server = "g.us" if dig.endswith("@g.us") else "s.whatsapp.net"
            jid = build_jid(dig, server)
            marker = str(jid)
            if marker in seen:
                continue
            seen.add(marker)
            candidates.append(jid)
        return candidates

    async def _send_to_known_or_built_jid(self, target: str, msg: str):
        last_error = None
        for jid in self._jid_candidates_for_target(target):
            try:
                resp = await self.client.send_message(jid, msg)
                log.info(f"📤 Admin notify enviado para {target} via {jid}")
                return resp
            except Exception as e:
                last_error = e
                log.warning(f"Falha enviando para {target} via {jid}: {e}")
        if last_error:
            raise last_error
        raise ValueError(f"sem JID candidato para {target}")

    # ── Access request flow ───────────────────────────────────────────────────

    async def _notify_admins_access_request(self, item: dict, approved: bool = False):
        cfg = load_config()
        admins = cfg.get("OWNER_IDS") or [cfg.get("OWNER", "")]
        if approved:
            text = (
                "🔓 Acesso liberado no WhatsApp\n"
                f"Nome: {item.get('name') or '?'}\n"
                f"Número físico/chat: {item.get('phone') or '?'}\n"
                f"ID recebido: {item.get('sender_id') or '?'}"
            )
        else:
            text = (
                "🔐 Pedido de acesso no WhatsApp\n"
                f"Nome: {item.get('name') or '(sem nome)'}\n"
                f"Número físico/chat: {item.get('phone') or '?'}\n"
                f"ID recebido: {item.get('sender_id') or '?'}\n"
                f"Pushname: {item.get('pushname') or '?'}\n\n"
                "Qual código devo exigir dessa pessoa?\n"
                "Responda marcando esta mensagem com o código escolhido."
            )
        prompt_ids = []
        sent_admin_uids = set()
        for admin in admins:
            admin = str(admin or "").strip()
            if not admin:
                continue
            rec = access_ctl.contact_record(admin)
            admin_uid = (rec or {}).get("contact_uid") or admin
            if admin_uid in sent_admin_uids:
                continue
            sent_admin_uids.add(admin_uid)
            try:
                resp = await self._send_to_known_or_built_jid(admin, text)
                resp_id = getattr(resp, "ID", "") or getattr(resp, "ServerID", "")
                if resp_id:
                    prompt_ids.append(str(resp_id))
            except Exception as e:
                log.warning(f"Falha avisando admin {admin}: {e}")
        if prompt_ids and not approved and item.get("step") == "admin_code":
            key, pending = access_ctl.find_pending_by_code_or_id(item.get("sender_id") or item.get("phone") or "")
            if pending:
                access_ctl.upsert_pending(key, admin_prompt_ids=prompt_ids)

    async def _handle_blocked_dm(self, chat_jid, sender_jid, sender_number: str, chat_number: str, text: str, pushname: str):
        key = access_ctl.pending_key(sender_number, chat_number, sender_jid, chat_jid)
        item = access_ctl.load_pending().get(key)

        if item and item.get("step") in {"user_code", "code"}:
            if access_ctl.code_matches(text, item.get("code")):
                added = access_ctl.add_allowed(
                    item.get("sender_id"), item.get("phone"), item.get("chat_id"), sender_number, chat_number
                )
                access_ctl.pop_pending(key)
                self._reload_allow_list()
                await self.client.send_message(chat_jid, "acesso liberado. pode falar comigo agora")
                await self._notify_admins_access_request(item, approved=True)
                log.info(f"🔓 Acesso liberado para {sender_number}/{chat_number}: {added}")
            else:
                await self.client.send_message(chat_jid, "código errado. confere com o dono e manda de novo")
            return

        if item and item.get("step") == "admin_code":
            await self.client.send_message(chat_jid, "ainda tô esperando o dono definir o código. segura aí")
            return

        if not item:
            access_ctl.upsert_pending(
                key,
                sender_id=sender_number,
                phone=chat_number,
                chat_id=access_ctl.digits(chat_jid),
                sender_jid=str(sender_jid),
                chat_jid=str(chat_jid),
                pushname=pushname,
                step="name",
            )
            await self.client.send_message(chat_jid, "fala teu nome pra eu pedir liberação pro dono")
            log.warning(f"🔒 Pedido de acesso iniciado: sender_id={sender_number} phone/chat={chat_number}")
            return

        if item.get("step") == "name":
            name = text.strip()[:80]
            access_ctl.set_contact_name(name, sender_number, chat_number, sender_jid, chat_jid)
            item = access_ctl.upsert_pending(
                key,
                name=name,
                code="",
                step="admin_code",
                sender_id=sender_number,
                phone=chat_number,
                chat_id=access_ctl.digits(chat_jid),
                sender_jid=str(sender_jid),
                chat_jid=str(chat_jid),
                pushname=pushname,
            )
            await self._notify_admins_access_request(item)
            await self.client.send_message(chat_jid, "pedi pro dono liberar. se ele passar um código, manda aqui")
            log.warning(f"🔐 Pedido enviado ao dono para definir código de {name}: sender_id={sender_number} phone/chat={chat_number}")
            return

        await self.client.send_message(chat_jid, "aguardando o código do dono")

    async def _handle_admin_code_reply(self, chat_jid, text: str, quoted_id: str = "") -> bool:
        waiting_all = access_ctl.pending_waiting_admin_code()
        if not quoted_id:
            if waiting_all and access_ctl.extract_admin_code(text):
                await self.client.send_message(chat_jid, "marca a mensagem do pedido e responde com o código. sem marcar eu não gravo")
                return True
            return False

        waiting = []
        for key, item in waiting_all:
            prompt_ids = [str(x) for x in (item.get("admin_prompt_ids") or [])]
            if quoted_id in prompt_ids:
                waiting.append((key, item))
        if not waiting:
            return False

        code = access_ctl.extract_admin_code(text)
        if not code:
            await self.client.send_message(chat_jid, "não usei isso como código. responde ao pedido marcado só com o código escolhido")
            return True

        if len(waiting) > 1:
            await self.client.send_message(
                chat_jid,
                "tem mais de um pedido aguardando código. usa `!acesso pendentes` e depois `!acesso codigo [ID] [codigo]`"
            )
            return True

        key, item = waiting[0]
        item = access_ctl.upsert_pending(key, code=code, step="user_code")
        await self.client.send_message(
            chat_jid,
            f"código salvo para {item.get('name') or key}. agora espero a pessoa repetir esse código"
        )

        try:
            await self._send_to_known_or_built_jid(item.get("sender_id") or item.get("phone") or key, "o dono definiu o código. se ele te passar, manda aqui")
        except Exception as e:
            log.warning(f"Não consegui avisar solicitante que o código foi definido: {e}")
        return True

    # ── Media ─────────────────────────────────────────────────────────────────

    async def _download_media(self, msg: dict) -> tuple:
        """Baixa mídia via bridge. Retorna (path, kind) ou (None, None)."""
        media_info = msg.get("media")
        if not media_info:
            return None, None

        media_kind = media_info.get("type")
        raw_key = msg.get("rawKey")
        raw_message = msg.get("rawMessage")
        if not raw_key or not raw_message:
            return None, media_kind

        ext_map = {
            "image": ".jpg", "video": ".mp4", "audio": ".ogg",
            "document": ".bin", "sticker": ".webp",
        }
        ext = ext_map.get(media_kind, ".bin")
        ts = int(time.time())
        out_path = str(Path(tempfile.gettempdir()) / f"link_in_{ts}{ext}")

        data = await self.client.download_media(raw_key, raw_message)
        if data:
            with open(out_path, "wb") as f:
                f.write(data)
            return out_path, media_kind

        return None, media_kind

    def _remember_media(self, sender_key: str, media_path: str, media_kind: str | None) -> str:
        src = Path(media_path)
        inbox = Path.home() / ".linkbot" / "inbox"
        inbox.mkdir(parents=True, exist_ok=True)
        ext = src.suffix or ".bin"
        dest = inbox / f"{int(time.time())}_{sender_key}_{media_kind or 'media'}{ext}"
        shutil.copy2(src, dest)
        self.last_media[sender_key] = {
            "path": str(dest),
            "kind": media_kind,
            "ts": time.time(),
        }
        return str(dest)

    def _recent_media(self, sender_key: str) -> tuple[str | None, str | None]:
        item = self.last_media.get(sender_key) or {}
        path = item.get("path")
        if not path or not os.path.exists(path):
            return None, None
        if time.time() - float(item.get("ts") or 0) > 15 * 60:
            return None, None
        return path, item.get("kind")

    # ── LLM reaction emoji ────────────────────────────────────────────────────

    async def _llm_reaction(
        self,
        text: str,
        *,
        skill: Skill | None = None,
        has_media: bool = False,
        media_type: str | None = "",
        is_admin: bool = False,
        usuario: str = "",
    ) -> str:
        loop = asyncio.get_event_loop()
        def _choose():
            return _llm.choose_reaction_emoji(
                text,
                usuario=usuario,
                skill_name=getattr(skill, "name", "") if skill else "",
                skill_category=getattr(skill, "category", "") if skill else "",
                has_media=has_media,
                media_type=media_type or "",
                is_admin=is_admin,
            )
        category = getattr(skill, "category", "") if skill else ""
        try:
            emoji = await asyncio.wait_for(loop.run_in_executor(None, _choose), timeout=8)
            return emoji or _fallback_reaction(category)
        except Exception as e:
            log.debug(f"reacao via LLM fallback falhou: {e}")
            return _fallback_reaction(category)

    # ── Reminder reaction ack ─────────────────────────────────────────────────

    def _check_reminder_reaction(self, msg: dict) -> bool:
        """Retorna True se é reação a um lembrete pendente (cancela retry)."""
        if msg.get("messageType") != "reactionMessage":
            return False
        raw = msg.get("rawMessage") or {}
        rxn = raw.get("reactionMessage") or {}
        target_id = (rxn.get("key") or {}).get("id", "")
        if target_id and target_id in self._pending_reminder_ack:
            info = self._pending_reminder_ack.pop(target_id)
            log.info(f"✅ Reminder confirmado por reação (após {info['retry_count']} retentativas)")
        return True

    # ── Group mention ─────────────────────────────────────────────────────────

    def _is_bot_mentioned(self, msg: dict) -> bool:
        my_user = getattr(self.my_jid, "User", "") if self.my_jid else ""
        if not my_user or my_user == "unknown":
            return False
        text = msg.get("text", "") or ""

        # checa @numero no texto (com e sem código de país)
        short = my_user.lstrip("0")[-10:]  # últimos 10 dígitos
        for part in (my_user, short):
            if f"@{part}" in text:
                return True

        # checa mentionedJid no rawMessage (inclui LID @lid)
        my_lid = self.my_lid or ""
        raw = msg.get("rawMessage") or {}
        for field in ("extendedTextMessage", "imageMessage", "videoMessage", "audioMessage"):
            obj = raw.get(field) or {}
            ctx = obj.get("contextInfo") or {}
            mentioned = ctx.get("mentionedJid") or []
            log.info(f"[grupo] mentionedJid={mentioned} my_user={my_user} my_lid={my_lid}")
            for jid in mentioned:
                jid_str = str(jid)
                if my_user in jid_str or short in jid_str:
                    return True
                # LID: "26565077414035@lid"
                if my_lid and my_lid in jid_str:
                    return True
        return False

    # ── Message handler ───────────────────────────────────────────────────────

    async def _on_message(self, msg: dict):
        """Processa mensagem recebida via webhook do bridge."""
        chat_jid_str = msg.get("chat", "")
        sender_jid_str = msg.get("sender", "")
        is_group = bool(msg.get("isGroup"))
        text = msg.get("text", "")
        quoted_id = msg.get("quotedMsgId", "")
        quoted_text = msg.get("quotedText", "")
        pushname = msg.get("pushName", "")
        message_id = msg.get("msgId", "")

        # Cria JIDs compatíveis com código existente
        chat_jid = build_jid(chat_jid_str)
        sender_jid = build_jid(sender_jid_str)
        sender_number = access_ctl.jid_user(sender_jid)
        chat_number = access_ctl.jid_user(chat_jid)

        # Reação a lembrete pendente
        if self._check_reminder_reaction(msg):
            return

        # Meta AI: intercepta antes do allow list (não está na lista de permitidos)
        if _meta_ai.proxy.is_from_meta_ai(msg):
            async def _dl():
                return await self._download_media(msg)
            await _meta_ai.proxy.intercept(msg, _dl)
            return

        # Registra JIDs conhecidos
        for key in access_ctl.identity_keys(sender_number, chat_number, sender_jid_str, chat_jid_str):
            self.user_jids[key] = chat_jid

        # Grupo: só responde a !comando ou @menção explícita
        if is_group:
            # refresh lazy do JID/LID se ainda desconhecido
            if not self.my_jid or getattr(self.my_jid, "User", "unknown") == "unknown":
                try:
                    me = await self.client.get_me()
                    self.my_jid = me.JID
                    self.my_lid = getattr(me, "LID", "")
                except Exception:
                    pass
            mentioned = self._is_bot_mentioned(msg)
            my_user = getattr(self.my_jid, "User", "") if self.my_jid else ""
            quoted_music_context = self._quoted_music_context(quoted_id, quoted_text, chat_jid_str)
            owner_natural = (
                self._is_admin(sender_number, chat_number, sender_jid_str, chat_jid_str)
                and (
                    self._natural_match_skill(text or "") is not None
                    or (quoted_music_context and _looks_like_contextual_music_request(text or ""))
                )
            )
            log.info(f"[grupo] text={repr((text or '')[:60])} mentioned={mentioned} owner_natural={owner_natural} my_user={my_user}")
            if not (text or "").strip().startswith("!") and not mentioned and not owner_natural:
                return

        # Allow list (só DM)
        if not is_group:
            if not self._is_allowed(sender_number, chat_number, sender_jid_str, chat_jid_str):
                log.warning(
                    f"Mensagem BLOQUEADA: sender_id={sender_number} phone/chat={chat_number} "
                    f"jid={sender_jid_str}"
                )
                try:
                    await self._handle_blocked_dm(chat_jid, sender_jid, sender_number, chat_number, text, pushname)
                except Exception:
                    log.error("Falha no fluxo de liberação", exc_info=True)
                return

        sender_key = access_ctl.pending_key(sender_number, chat_number, sender_jid_str, chat_jid_str)
        incoming_media_path = None
        incoming_media_kind = None
        has_media_flag = bool(msg.get("media"))
        if has_media_flag:
            incoming_media_path, incoming_media_kind = await self._download_media(msg)
            if incoming_media_path:
                incoming_media_path = self._remember_media(sender_key, incoming_media_path, incoming_media_kind)

        if not text or not text.strip():
            if incoming_media_path:
                await self.client.send_message(
                    chat_jid,
                    "recebi o arquivo. manda `salva` ou reenvia com legenda do que quer fazer"
                )
                log.info(
                    f"📥 [id={sender_number} phone/chat={chat_number}] "
                    f"midia sem texto salva em {incoming_media_path}"
                )
            return
        log.info(f"📩 [id={sender_number} phone/chat={chat_number}] {text[:80]}")
        access_ctl.merge_contact_ids(sender_number, chat_number, sender_jid_str, chat_jid_str)

        if self._is_admin(sender_number, chat_number, sender_jid_str, chat_jid_str):
            if await self._handle_admin_code_reply(chat_jid, text, quoted_id):
                log.info(f"🔑 Código definido pelo dono para pedido pendente")
                return

        if not self._is_admin(sender_number, chat_number, sender_jid_str, chat_jid_str):
            key = f"known_name:{access_ctl.pending_key(sender_number, chat_number, sender_jid_str, chat_jid_str)}"
            pending = access_ctl.load_pending().get(key)
            if pending and pending.get("step") == "known_name":
                name = text.strip()[:80]
                access_ctl.set_contact_name(name, sender_number, chat_number, sender_jid, chat_jid)
                access_ctl.pop_pending(key)
                await self.client.send_message(chat_jid, f"beleza, {name}. salvei teu contato")
                log.info(f"👤 Nome salvo para {sender_number}/{chat_number}: {name}")
                return

            if not access_ctl.has_contact_name(sender_number, chat_number, sender_jid_str, chat_jid_str):
                fallback_name = (pushname or "").strip()
                if fallback_name and fallback_name.lower() not in {"whatsapp", "unknown", "desconhecido"}:
                    access_ctl.set_contact_name(fallback_name, sender_number, chat_number, sender_jid, chat_jid)
                elif is_group:
                    access_ctl.set_contact_name(
                        sender_number, sender_number, chat_number, sender_jid, chat_jid
                    )
                else:
                    access_ctl.upsert_pending(
                        key,
                        sender_id=sender_number,
                        phone=chat_number,
                        chat_id=access_ctl.digits(chat_jid_str),
                        sender_jid=sender_jid_str,
                        chat_jid=chat_jid_str,
                        step="known_name",
                    )
                    await self.client.send_message(chat_jid, "não sei teu nome ainda. como posso te chamar?")
                    return

        text_norm = _norm_text(text)
        if any(x in text_norm for x in ["quem sou eu", "quem e eu", "qual meu nome", "sabe quem sou", "lembra de mim"]):
            nome = access_ctl.display_name(sender_number, chat_number, sender_jid_str, chat_jid_str, pushname=pushname)
            papel = "meu parceiro e dono desse sistema" if self._is_admin(sender_number, chat_number, sender_jid_str, chat_jid_str) else "usuário autorizado"
            reply = f"você é {nome}, {papel}"
            resp = await self.client.send_message(chat_jid, reply)
            self._remember_sent_message(chat_jid_str, getattr(resp, "ID", "") or getattr(resp, "ServerID", ""))
            log.info(f"📤 [id={sender_number} phone/chat={chat_number}] {reply}")
            return

        if _looks_like_delete_bot_messages(text):
            await self._handle_delete_bot_messages(chat_jid, chat_jid_str, text, quoted_id)
            return

        # quoted_music_context: já calculado no bloco de grupo acima; recalcula aqui apenas em DM
        if not is_group:
            quoted_music_context = self._quoted_music_context(quoted_id, quoted_text, chat_jid_str)

        # ── Clarificação pendente ────────────────────────────────────────────────
        _now_ts = time.time()
        for _k in [k for k, v in self._pending_clarification.items() if _now_ts - v[2] > 600]:
            del self._pending_clarification[_k]

        if sender_number in self._pending_clarification:
            _sk, _orig, _, _retries = self._pending_clarification.pop(sender_number)
            if _retries < 2:
                _action, _args_pend = await asyncio.get_event_loop().run_in_executor(
                    None, _llm.resolver_pendente, _sk, text
                )
                if _action == "choose":
                    _args_pend = await asyncio.get_event_loop().run_in_executor(
                        None, _llm.ia_escolher_args, _sk
                    )
                    _action = "use"
                if _action == "cannot_choose":
                    _resp = await asyncio.get_event_loop().run_in_executor(
                        None, _llm.gerar_pergunta_skill, _sk, _orig, ""
                    )
                    if _resp:
                        resp = await self.client.send_message(chat_jid, _resp)
                        self._remember_sent_message(chat_jid_str, getattr(resp, "ID", "") or getattr(resp, "ServerID", ""))
                    self._pending_clarification[sender_number] = (_sk, _orig, time.time(), _retries + 1)
                    return
                if _action == "use" and _args_pend:
                    skill_obj = self.router.get_by_name(_sk)
                    if skill_obj:
                        match = (skill_obj, _args_pend)
                        skill, rest = match
                        log.info(f"  → skill (clarificado): {skill.name} args={_args_pend!r}")
                        # pula para execução da skill abaixo
                        # (match não é None, o fluxo normal continua)

        # URL auto-detect → delirius_dl (YouTube, Spotify, Instagram, Twitter/X)
        if not locals().get('match'):
            match = None
        if match is None and quoted_music_context and _looks_like_contextual_music_request(text):
            _dl_skill = self.router.get_by_name("delirius_dl")
            if _dl_skill:
                match = (_dl_skill, f"{text}\nContexto musical anterior: {quoted_music_context}")
        try:
            if match is None:
                from bot.skills.delirius_dl import detect_url as _detect_dl_url
                _auto_url, _ = _detect_dl_url(text)
                if _auto_url:
                    _dl_skill = self.router.get_by_name("delirius_dl")
                    if _dl_skill:
                        match = (_dl_skill, text)
        except Exception:
            pass

        # Match skills (se URL auto-detect não achou nada)
        stripped = text.strip()
        if match is None:
            natural_match = self._natural_match_skill(text)
            direct_router = self.router.match(text)
            if natural_match:
                match = natural_match
            elif stripped.startswith(("!", "[")) or (direct_router and direct_router[0].name in {"ajuda"}):
                match = direct_router
            else:
                # !comando no meio da frase (ex: "chama a skill !spot zelda")
                import re as _re
                _inline = _re.search(r'!\w+', stripped)
                if _inline:
                    _from_cmd = stripped[_inline.start():]
                    _inline_match = self.router.match(_from_cmd)
                    if _inline_match:
                        match = _inline_match
            if match is None:
                ai_match = await asyncio.get_event_loop().run_in_executor(None, self._ai_match_skill, text)
                if ai_match is False:
                    match = self._safe_direct_match(direct_router)
                elif ai_match is None:
                    match = self._safe_direct_match(direct_router)
                elif ai_match and not (ai_match[1] or "").strip():
                    # skill detectada mas args vazio → pede clarificação
                    _sk_name = ai_match[0].name
                    _pergunta = await asyncio.get_event_loop().run_in_executor(
                        None, _llm.gerar_pergunta_skill, _sk_name, text, ""
                    )
                    if _pergunta:
                        resp = await self.client.send_message(chat_jid, _pergunta)
                        self._remember_sent_message(chat_jid_str, getattr(resp, "ID", "") or getattr(resp, "ServerID", ""))
                        self._pending_clarification[sender_number] = (_sk_name, text, time.time(), 0)
                        return
                    match = ai_match  # pergunta falhou → executa com o que tem
                else:
                    match = ai_match

        if match is None:
            try:
                _ctx_llm = MessageContext(
                    raw_text=text, args_text=text,
                    sender_jid=sender_jid, chat_jid=chat_jid,
                    is_group=is_group, message_id=message_id,
                    quoted_msg_id=quoted_id, quoted_text=quoted_text,
                    my_jid=self.my_jid, pushname=pushname,
                    client=self.client,
                )
                nome_usuario = access_ctl.display_name(sender_number, chat_number, sender_jid_str, chat_jid_str, pushname=pushname)
                await _ctx_llm.typing()
                await _ctx_llm.react(await self._llm_reaction(
                    text,
                    has_media=bool(incoming_media_path),
                    media_type=incoming_media_kind,
                    is_admin=self._is_admin(sender_number, chat_number, sender_jid_str, chat_jid_str),
                    usuario=nome_usuario,
                ))
                reply = await asyncio.get_event_loop().run_in_executor(
                    None, _llm.chat, sender_number, text, nome_usuario
                )
                resp = await self.client.send_message(chat_jid, reply, quoted_id=message_id, quoted_sender=sender_jid_str if is_group else "")
                self._remember_sent_message(chat_jid_str, getattr(resp, "ID", "") or getattr(resp, "ServerID", ""))
                log.info(f"📤 [id={sender_number} phone/chat={chat_number}] {reply[:120]}")
            except Exception as e:
                log.error(f"LLM fallback falhou: {e}")
                resp = await self.client.send_message(chat_jid, "🌀")
                self._remember_sent_message(chat_jid_str, getattr(resp, "ID", "") or getattr(resp, "ServerID", ""))
            return

        skill, rest = match
        log.info(f"  → skill: {skill.name}")

        media_path = None
        media_kind = None
        has_media = False

        if incoming_media_path:
            media_path, media_kind = incoming_media_path, incoming_media_kind
        elif skill.requires_media:
            media_path, media_kind = self._recent_media(sender_key)
        elif has_media_flag:
            media_path, media_kind = await self._download_media(msg)
            if media_path:
                media_path = self._remember_media(sender_key, media_path, media_kind)
        has_media = media_path is not None

        ctx = MessageContext(
            raw_text=text,
            args_text=rest,
            sender_jid=sender_jid,
            chat_jid=chat_jid,
            is_group=is_group,
            message_id=message_id,
            quoted_msg_id=quoted_id,
            quoted_text=quoted_text,
            my_jid=self.my_jid,
            pushname=pushname,
            has_media=has_media,
            media_type=media_kind,
            media_path=media_path,
            client=self.client,
            storage=self.storage,
            config=self.config,
            router=self.router,
            sent_music_callback=lambda mid, ctx, _cj=chat_jid_str: self._remember_sent_music(mid, ctx, _cj),
            sent_message_callback=lambda mid, _cj=chat_jid_str: self._remember_sent_message(_cj, mid),
        )

        nome_usuario = access_ctl.display_name(sender_number, chat_number, sender_jid_str, chat_jid_str, pushname=pushname)
        await ctx.typing()
        if skill.name == "ajuda":
            await ctx.react("📜")
        else:
            await ctx.react(await self._llm_reaction(
                text,
                skill=skill,
                has_media=has_media,
                media_type=media_kind,
                is_admin=self._is_admin(sender_number, chat_number, sender_jid_str, chat_jid_str),
                usuario=nome_usuario,
            ))

        try:
            await skill.handler(ctx)
            log.info(f"✅ skill concluida: {skill.name}")
        except Exception as e:
            log.error(f"Erro na skill {skill.name}: {e}", exc_info=True)
            try:
                resp = await self.client.send_message(
                    chat_jid,
                    f"⚡ Esse construct quebrou, parceiro: {e}"
                )
                self._remember_sent_message(chat_jid_str, getattr(resp, "ID", "") or getattr(resp, "ServerID", ""))
            except Exception:
                pass

    # ── Webhook server (recebe do bridge) ─────────────────────────────────────

    async def _webhook_handler(self, request: aiohttp_web.Request) -> aiohttp_web.Response:
        try:
            payload = await request.json()
            event = payload.get("event", "")
            if event == "message":
                asyncio.create_task(self._on_message(payload))
        except Exception as e:
            log.error(f"Webhook erro: {e}")
        return aiohttp_web.Response(status=200, text="ok")

    async def _start_webhook_server(self) -> aiohttp_web.AppRunner:
        app = aiohttp_web.Application()
        app.router.add_post("/webhook", self._webhook_handler)
        runner = aiohttp_web.AppRunner(app)
        await runner.setup()
        webhook_port = self.config.get("WEBHOOK_PORT", 7333)
        site = aiohttp_web.TCPSite(runner, "127.0.0.1", webhook_port)
        await site.start()
        log.info(f"📡 Webhook Python em http://localhost:{webhook_port}/webhook")
        return runner

    # ── HTTP API (porta 7332 — envio externo via Python) ──────────────────────

    def _start_http_api(self, loop: asyncio.AbstractEventLoop):
        """Sobe HTTP API na porta 7332 para envio externo de mensagens WhatsApp."""
        bot_ref = self

        class _Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                if self.path not in ("/send", "/triforce"):
                    self.send_response(404)
                    self.end_headers()
                    return
                try:
                    length = int(self.headers.get("Content-Length", 0))
                    body = json.loads(self.rfile.read(length))
                    to_num = str(body.get("to", "")).strip()
                    msg    = str(body.get("msg", "")).strip()
                    if not to_num or not msg:
                        raise ValueError("campos 'to' e 'msg' obrigatorios")
                    if self.path == "/triforce":
                        if not msg.startswith("✨"):
                            msg = f"✨ {msg}"
                    else:
                        while msg.startswith("✨"):
                            msg = msg.lstrip("✨").strip()
                    if not msg:
                        raise ValueError("mensagem vazia apos strip")

                    log.info(f"📤 [{to_num}] {msg[:60]}")
                    last_error = None
                    sent = False
                    response_id = ""
                    for jid in bot_ref._jid_candidates_for_target(to_num):
                        try:
                            fut = asyncio.run_coroutine_threadsafe(
                                bot_ref.client.send_message(jid, msg), loop
                            )
                            resp = fut.result(timeout=15)
                            response_id = str(getattr(resp, "ID", "") or getattr(resp, "ServerID", ""))
                            log.info(f"📤 HTTP /send entregue para {to_num} via {jid}")
                            sent = True
                            break
                        except Exception as e:
                            last_error = e
                            log.warning(f"HTTP /send falhou para {to_num} via {jid}: {e}")
                    if not sent:
                        raise ValueError(f"JID desconhecido/inalcançável para {to_num}: {last_error}")
                    self.send_response(200)
                    self.end_headers()
                    self.wfile.write(json.dumps({"ok": True, "id": response_id}).encode())
                except Exception as e:
                    log.error(f"HTTP /send erro: {e}")
                    self.send_response(500)
                    self.end_headers()
                    self.wfile.write(
                        json.dumps({"ok": False, "error": str(e)}).encode()
                    )

            def log_message(self, *args):
                pass

        server = ThreadingHTTPServer(("127.0.0.1", 7332), _Handler)
        log.info("📡 WhatsApp HTTP API em http://localhost:7332")
        server.serve_forever()

    # ── Run ───────────────────────────────────────────────────────────────────

    async def run(self):
        log.info("=" * 50)
        log.info("🗡️  LINK BOT — Hyrule Edition (Baileys Bridge)")
        log.info("=" * 50)

        if not self.allow_list:
            log.warning("⚠️ ALLOW_FROM vazio! Ninguém poderá falar com o bot.")
            log.warning("   Edita config/config.json e bota seu número.")

        # Aguarda bridge estar online
        bridge_url = self.config.get("BRIDGE_URL", "http://localhost:7334")
        log.info(f"⏳ Aguardando bridge em {bridge_url} ...")
        for attempt in range(30):
            if await self.client.is_connected():
                break
            # Bridge pode estar subindo mas não conectado ainda — tenta status
            try:
                import httpx as _hx
                async with _hx.AsyncClient() as hc:
                    r = await hc.get(f"{bridge_url}/status", timeout=2)
                    if r.status_code == 200:
                        data = r.json()
                        if data.get("hasQr"):
                            log.info(f"📱 Escaneie o QR em: {bridge_url}/qr")
                        break
            except Exception:
                pass
            await asyncio.sleep(2)
        else:
            log.warning("⚠️ Bridge não respondeu. Verifique se 'node whatsapp-bridge/index.js' está rodando.")

        loop = asyncio.get_event_loop()

        # HTTP API thread (porta 7332)
        t = threading.Thread(target=self._start_http_api, args=(loop,), daemon=True)
        t.start()

        # Webhook server (porta 7333)
        runner = await self._start_webhook_server()

        # Conectado
        await self._on_connected()

        log.info("✅ Bot pronto. Aguardando mensagens via bridge...")

        try:
            while True:
                await asyncio.sleep(60)
                if not await self.client.is_connected():
                    log.warning("⚠️ Bridge desconectado do WhatsApp. Aguardando reconexão...")
        except asyncio.CancelledError:
            pass
        finally:
            await runner.cleanup()
            await self.scheduler.stop()
            if self._retry_task and not self._retry_task.done():
                self._retry_task.cancel()
            if self._media_cleanup_task and not self._media_cleanup_task.done():
                self._media_cleanup_task.cancel()
            self.storage.close()
            await self.client.close()


# ===================== MAIN =====================

async def main():
    if "--reset" in sys.argv:
        auth_dir = Path(__file__).resolve().parents[2] / "whatsapp-bridge" / "auth"
        if auth_dir.exists():
            shutil.rmtree(auth_dir)
            print(f"🔥 Sessão Baileys apagada: {auth_dir}")
            print("Próxima execução do bridge vai pedir QR de novo.")
        else:
            print(f"Sessão não encontrada em {auth_dir}")
        return

    config = load_config()
    bot = LinkBot(config)
    await bot.run()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n👋 Bot encerrado pelo usuário.")
