#!/usr/bin/env python3
"""
Link Bot - Launcher Principal
==============================
Conecta no WhatsApp via neonize, carrega todas as skills,
roteia mensagens, dispara lembretes em background.

Uso:
    python -m bot.main           # roda normal
    python -m bot.main --reset   # apaga sessão e re-pareia

Config: ler config/config.json (criado pelo personalizar.sh/.bat).
"""

import asyncio
import importlib
import json
import logging
import os
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
    from neonize.aioze.client import NewAClient
    from neonize.aioze.events import (
        ConnectedEv, MessageEv, PairStatusEv,
    )
    from neonize.utils import build_jid
except ImportError:
    print("❌ Falta neonize. Instala com:  pip install neonize qrcode httpx")
    sys.exit(1)

from bot.core.router import Router, Skill
from bot.core.context import MessageContext
from bot.core.storage import Storage
from bot.core.scheduler import ReminderScheduler
from bot.core import llm as _llm
from bot.core import access as access_ctl


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
for noisy in ("whatsmeow", "whatsmeow.Client",
              "whatsmeow.Client.Socket", "neonize"):
    logging.getLogger(noisy).setLevel(logging.WARNING)

log = logging.getLogger("link-bot")


def _norm_text(text: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFD", (text or "").lower())
        if unicodedata.category(c) != "Mn"
    )


def load_config() -> dict:
    """Carrega config/config.json e expande env vars ${VAR}."""
    path = ROOT / "config" / "config.json"
    if not path.exists():
        log.error(f"Config não encontrado: {path}")
        log.error("Roda o script personalizar primeiro.")
        sys.exit(1)

    with open(path, encoding="utf-8") as f:
        raw = f.read()

    # Expande ${ENV_VAR}
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
            # Pode ser uma skill ou lista
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
    return loaded


# ===================== HANDLERS =====================

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

        # Bot identity (preenchido no on_connected)
        self.my_jid = None

        # Allow/admin list: aceita número físico e ID/JID recebido do WhatsApp.
        self.allow_list = list(access_ctl.allow_keys(config))
        self.admin_list = list(access_ctl.admin_keys(config))

        # Cliente neonize
        session_path = config.get("SESSION_PATH",
                                   str(Path.home() / ".linkbot" / "session.sqlite"))
        Path(session_path).parent.mkdir(parents=True, exist_ok=True)
        self.client = NewAClient(session_path)

        # Scheduler
        self.scheduler = ReminderScheduler(
            self.storage, self._send_reminder
        )

        # Registra eventos
        self.client.event(ConnectedEv)(self._on_connected)
        self.client.event(PairStatusEv)(self._on_pair)
        self.client.event(MessageEv)(self._on_message)

        # QR: salva PNG + mostra no terminal
        @self.client.event.qr
        async def _on_qr(_client, qr_bytes: bytes):
            import qrcode as _qrcode
            qr_path = str(Path(session_path).parent / "qr.png")
            img = _qrcode.make(qr_bytes)
            img.save(qr_path)
            log.info("=" * 50)
            log.info("📱 ESCANEIE O QR ABAIXO OU ABRA O ARQUIVO:")
            log.info(f"   {qr_path}")
            log.info("=" * 50)
            try:
                import segno as _segno
                _segno.make_qr(qr_bytes).terminal(compact=True)
            except Exception:
                pass
            # Abre a imagem automaticamente
            try:
                if sys.platform == "win32":
                    os.startfile(qr_path)
                else:
                    import subprocess as _sp
                    _sp.Popen(["xdg-open", qr_path],
                              stdout=_sp.DEVNULL, stderr=_sp.DEVNULL)
            except Exception:
                pass

    async def _on_connected(self, _client, _ev):
        log.info("🟢 Conectado ao WhatsApp.")
        try:
            me = await self.client.get_me()
            self.my_jid = me.JID
        except Exception:
            pass
        await self.scheduler.start()

    async def _on_pair(self, _client, ev):
        try:
            log.info(f"✅ Pareado: +{ev.ID.User}")
            self.my_jid = ev.ID
        except Exception:
            log.info("✅ Pareamento concluído.")

    async def _send_reminder(self, user_jid_str: str, text: str):
        """Callback do scheduler — manda mensagem pro user."""
        try:
            jid = build_jid(user_jid_str)
            await self.client.send_message(jid, text)
        except Exception as e:
            log.error(f"Falha enviando reminder: {e}")

    def _reload_allow_list(self):
        """Relê config.json do disco (permite hot-reload após !eu / !acesso)."""
        try:
            cfg = load_config()
            self.allow_list = list(access_ctl.allow_keys(cfg))
            self.admin_list = list(access_ctl.admin_keys(cfg))
        except Exception:
            pass

    def _is_allowed(self, *ids) -> bool:
        """Verifica se o remetente tá na allow_list (relê config a cada check)."""
        self._reload_allow_list()
        if not self.allow_list:
            return False  # default deny
        return bool(set(access_ctl.identity_keys(*ids)) & set(self.allow_list))

    def _is_admin(self, *ids) -> bool:
        self._reload_allow_list()
        return bool(set(access_ctl.identity_keys(*ids)) & set(self.admin_list))

    def _ai_match_skill(self, text: str):
        skill_items = [
            {"name": s.name, "description": s.description}
            for s in self.router.list_enabled()
            if s.enabled
        ]
        intent = _llm.classify_skill_intent(text, skill_items)
        if intent is None:
            return None
        if not intent.get("skill"):
            return False
        skill = self.router.get_by_name(intent["skill"])
        if skill is None:
            return False
        return skill, intent.get("args", text)

    def _jid_candidates_for_target(self, target: str):
        """Retorna JIDs prováveis para número físico, LID interno e aliases do contato."""
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
            servers = []
            if dig.startswith("55") and len(dig) in (12, 13):
                servers.append("s.whatsapp.net")
            else:
                servers.append("lid")
            servers.append("s.whatsapp.net")
            for server in servers:
                marker = f"{dig}@{server}"
                if marker in seen:
                    continue
                seen.add(marker)
                candidates.append(build_jid(dig, server))
        return candidates

    async def _send_to_known_or_built_jid(self, target: str, msg: str):
        last_error = None
        for jid in self._jid_candidates_for_target(target):
            try:
                resp = await self.client.send_message(jid, msg)
                log.info(
                    f"📤 Admin notify enviado para {target} via "
                    f"{getattr(jid, 'User', '?')}@{getattr(jid, 'Server', '?')}"
                )
                return resp
            except Exception as e:
                last_error = e
                log.warning(
                    f"Falha enviando para {target} via "
                    f"{getattr(jid, 'User', '?')}@{getattr(jid, 'Server', '?')}: {e}"
                )
        if last_error:
            raise last_error
        raise ValueError(f"sem JID candidato para {target}")

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
        """Fluxo de solicitação: pede nome, admin define código, usuário repete código."""
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

        target_jid = item.get("chat_jid") or item.get("sender_jid")
        try:
            await self._send_to_known_or_built_jid(item.get("sender_id") or item.get("phone") or key, "o dono definiu o código. se ele te passar, manda aqui")
        except Exception as e:
            log.warning(f"Não consegui avisar solicitante que o código foi definido: {e}")
        return True

    async def _download_media(self, ev) -> tuple:
        """Tenta baixar mídia anexa. Retorna (path, kind) ou (None, None)."""
        msg = ev.Message
        media_kind = None
        download_method = None

        if msg.imageMessage and msg.imageMessage.URL:
            media_kind = "image"
            download_method = "imageMessage"
        elif msg.videoMessage and msg.videoMessage.URL:
            media_kind = "video"
            download_method = "videoMessage"
        elif msg.audioMessage and msg.audioMessage.URL:
            media_kind = "audio"
            download_method = "audioMessage"
        elif msg.documentMessage and msg.documentMessage.URL:
            media_kind = "document"
            download_method = "documentMessage"
        elif msg.stickerMessage and msg.stickerMessage.URL:
            media_kind = "sticker"
            download_method = "stickerMessage"

        if media_kind is None:
            return None, None

        # Tenta o método mais comum: client.download_any(message)
        try:
            ext_map = {
                "image": ".jpg", "video": ".mp4", "audio": ".ogg",
                "document": ".bin", "sticker": ".webp",
            }
            ext = ext_map.get(media_kind, ".bin")
            ts = int(time.time())
            out_path = str(Path(tempfile.gettempdir()) /
                          f"link_in_{ts}{ext}")

            # Várias APIs possíveis no neonize
            for method in ("download_any", "download", "download_media"):
                fn = getattr(self.client, method, None)
                if fn is None:
                    continue
                try:
                    data = await fn(msg)
                    if isinstance(data, bytes):
                        with open(out_path, "wb") as f:
                            f.write(data)
                        return out_path, media_kind
                    elif isinstance(data, str) and os.path.exists(data):
                        return data, media_kind
                except Exception:
                    continue
            return None, media_kind
        except Exception as e:
            log.debug(f"download falhou: {e}")
            return None, media_kind

    def _extract_text(self, msg) -> str:
        """Extrai texto de qualquer tipo de mensagem."""
        # Texto puro
        if hasattr(msg, "conversation") and msg.conversation:
            return msg.conversation
        # Texto com formatação
        if hasattr(msg, "extendedTextMessage") and msg.extendedTextMessage:
            text = getattr(msg.extendedTextMessage, "text", "")
            if text:
                return text
        # Caption de imagem/vídeo
        if hasattr(msg, "imageMessage") and msg.imageMessage:
            cap = getattr(msg.imageMessage, "caption", "")
            if cap:
                return cap
        if hasattr(msg, "videoMessage") and msg.videoMessage:
            cap = getattr(msg.videoMessage, "caption", "")
            if cap:
                return cap
        return ""

    def _quoted_stanza_id(self, msg) -> str:
        """ID da mensagem marcada/respondida no WhatsApp, quando existir."""
        candidates = []
        if hasattr(msg, "extendedTextMessage") and msg.extendedTextMessage:
            candidates.append(getattr(msg.extendedTextMessage, "contextInfo", None))
        if hasattr(msg, "imageMessage") and msg.imageMessage:
            candidates.append(getattr(msg.imageMessage, "contextInfo", None))
        if hasattr(msg, "videoMessage") and msg.videoMessage:
            candidates.append(getattr(msg.videoMessage, "contextInfo", None))
        for ctx in candidates:
            if not ctx:
                continue
            for attr in ("stanzaID", "stanzaId", "stanza_id"):
                val = getattr(ctx, attr, "")
                if val:
                    return str(val)
        return ""

    async def _on_message(self, _client, ev):
        # Ignora mensagens que VOCÊ enviou
        try:
            if ev.Info.MessageSource.IsFromMe:
                return
        except Exception:
            pass

        # Identidade do remetente
        try:
            chat = ev.Info.MessageSource.Chat
            sender = ev.Info.MessageSource.Sender
            chat_jid = chat
            sender_jid = sender
            sender_number = access_ctl.jid_user(sender)
            chat_number = access_ctl.jid_user(chat)
            is_group = ev.Info.MessageSource.IsGroup
        except Exception as e:
            log.debug(f"falha ao extrair source: {e}")
            return

        # Texto e metadados básicos vêm antes do gate de acesso para o fluxo de liberação.
        text = self._extract_text(ev.Message)
        quoted_id = self._quoted_stanza_id(ev.Message)
        pushname = getattr(ev.Info, "Pushname", "") or ""
        message_id = getattr(ev.Info, "ID", "") or ""

        # Armazena JIDs reais para envio posterior via HTTP/API/admin.
        for key in access_ctl.identity_keys(sender_number, chat_number, sender_jid, chat_jid):
            self.user_jids[key] = chat_jid

        # Allow list (só DM)
        if not is_group:
            if not self._is_allowed(sender_number, chat_number, sender_jid, chat_jid):
                log.warning(
                    f"Mensagem BLOQUEADA: sender_id={sender_number} phone/chat={chat_number} "
                    f"jid={sender_jid}"
                )
                try:
                    await self._handle_blocked_dm(chat_jid, sender_jid, sender_number, chat_number, text, pushname)
                except Exception:
                    log.error("Falha no fluxo de liberação", exc_info=True)
                return

        if not text or not text.strip():
            return
        log.info(f"📩 [id={sender_number} phone/chat={chat_number}] {text[:80]}")
        access_ctl.merge_contact_ids(sender_number, chat_number, sender_jid, chat_jid)

        if self._is_admin(sender_number, chat_number, sender_jid, chat_jid):
            if await self._handle_admin_code_reply(chat_jid, text, quoted_id):
                log.info(f"🔑 Código definido pelo dono para pedido pendente")
                return

        if not self._is_admin(sender_number, chat_number, sender_jid, chat_jid):
            key = f"known_name:{access_ctl.pending_key(sender_number, chat_number, sender_jid, chat_jid)}"
            pending = access_ctl.load_pending().get(key)
            if pending and pending.get("step") == "known_name":
                name = text.strip()[:80]
                access_ctl.set_contact_name(name, sender_number, chat_number, sender_jid, chat_jid)
                access_ctl.pop_pending(key)
                await self.client.send_message(chat_jid, f"beleza, {name}. salvei teu contato")
                log.info(f"👤 Nome salvo para {sender_number}/{chat_number}: {name}")
                return

            if not access_ctl.has_contact_name(sender_number, chat_number, sender_jid, chat_jid):
                fallback_name = (pushname or "").strip()
                if fallback_name and fallback_name.lower() not in {"whatsapp", "unknown", "desconhecido"}:
                    access_ctl.set_contact_name(fallback_name, sender_number, chat_number, sender_jid, chat_jid)
                else:
                    access_ctl.upsert_pending(
                        key,
                        sender_id=sender_number,
                        phone=chat_number,
                        chat_id=access_ctl.digits(chat_jid),
                        sender_jid=str(sender_jid),
                        chat_jid=str(chat_jid),
                        step="known_name",
                    )
                    await self.client.send_message(chat_jid, "não sei teu nome ainda. como posso te chamar?")
                    return

        text_norm = _norm_text(text)
        if any(x in text_norm for x in ["quem sou eu", "quem e eu", "qual meu nome", "sabe quem sou", "lembra de mim"]):
            nome = access_ctl.display_name(sender_number, chat_number, sender_jid, chat_jid, pushname=pushname)
            papel = "meu parceiro e dono desse sistema" if self._is_admin(sender_number, chat_number, sender_jid, chat_jid) else "usuário autorizado"
            reply = f"você é {nome}, {papel}"
            await self.client.send_message(chat_jid, reply)
            log.info(f"📤 [id={sender_number} phone/chat={chat_number}] {reply}")
            return

        # Match: comandos explícitos usam router direto; linguagem natural passa pela IA.
        stripped = text.strip()
        if stripped.startswith(("!", "[")):
            match = self.router.match(text)
        else:
            ai_match = await asyncio.get_event_loop().run_in_executor(None, self._ai_match_skill, text)
            if ai_match is False:
                match = None
            elif ai_match is None:
                match = self.router.match(text)
            else:
                match = ai_match
        if match is None:
            # Fallback LLM com persona Link (OpenRouter → Groq)
            try:
                _ctx_llm = MessageContext(
                    raw_text=text, args_text=text,
                    sender_jid=sender_jid, chat_jid=chat_jid,
                    is_group=is_group, message_id=message_id,
                    my_jid=self.my_jid, pushname=pushname,
                    client=self.client,
                )
                await _ctx_llm.typing()
                nome_usuario = access_ctl.display_name(sender_number, chat_number, sender_jid, chat_jid, pushname=pushname)
                reply = await asyncio.get_event_loop().run_in_executor(
                    None, _llm.chat, sender_number, text, nome_usuario
                )
                await self.client.send_message(chat_jid, reply)
                log.info(f"📤 [id={sender_number} phone/chat={chat_number}] {reply[:120]}")
            except Exception as e:
                log.error(f"LLM fallback falhou: {e}")
                await self.client.send_message(chat_jid, "🌀")
                log.info(f"📤 [id={sender_number} phone/chat={chat_number}] 🌀")
            return

        skill, rest = match
        log.info(f"  → skill: {skill.name}")

        # Mídia (se necessária)
        media_path = None
        media_kind = None
        has_media = False

        if skill.requires_media or self._has_media(ev.Message):
            media_path, media_kind = await self._download_media(ev)
            has_media = media_path is not None

        # Monta contexto
        ctx = MessageContext(
            raw_text=text,
            args_text=rest,
            sender_jid=sender_jid,
            chat_jid=chat_jid,
            is_group=is_group,
            message_id=message_id,
            my_jid=self.my_jid,
            pushname=pushname,
            has_media=has_media,
            media_type=media_kind,
            media_path=media_path,
            client=self.client,
            storage=self.storage,
            config=self.config,
            router=self.router,
        )

        # Reage com espada + mostra digitando
        await ctx.react("⚔️")
        await ctx.typing()

        # Dispara
        try:
            await skill.handler(ctx)
            log.info(f"✅ skill concluida: {skill.name}")
        except Exception as e:
            log.error(f"Erro na skill {skill.name}: {e}", exc_info=True)
            try:
                await self.client.send_message(
                    chat_jid,
                    f"⚡ Esse construct quebrou, parceiro: {e}"
                )
            except Exception:
                pass

    def _has_media(self, msg) -> bool:
        return any([
            getattr(msg, "imageMessage", None),
            getattr(msg, "videoMessage", None),
            getattr(msg, "audioMessage", None),
            getattr(msg, "documentMessage", None),
            getattr(msg, "stickerMessage", None),
        ])

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
                        # ✨ é exclusivo do /triforce — LLM não pode usar como prefixo
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
                            log.info(
                                f"📤 HTTP /send entregue para {to_num} via "
                                f"{getattr(jid, 'User', '?')}@{getattr(jid, 'Server', '?')}"
                            )
                            sent = True
                            break
                        except Exception as e:
                            last_error = e
                            log.warning(
                                f"HTTP /send falhou para {to_num} via "
                                f"{getattr(jid, 'User', '?')}@{getattr(jid, 'Server', '?')}: {e}"
                            )
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
                pass  # silencioso

        server = ThreadingHTTPServer(("127.0.0.1", 7332), _Handler)
        log.info("📡 WhatsApp HTTP API em http://localhost:7332")
        server.serve_forever()

    async def run(self):
        log.info("=" * 50)
        log.info("🗡️  LINK BOT — TOTK Edition")
        log.info("=" * 50)

        if not self.allow_list:
            log.warning("⚠️ ALLOW_FROM vazio! Ninguém poderá falar com o bot.")
            log.warning("   Edita config/config.json e bota seu número.")

        try:
            loop = asyncio.get_event_loop()
            t = threading.Thread(
                target=self._start_http_api, args=(loop,), daemon=True
            )
            t.start()

            task = await self.client.connect()
            await task  # mantém ativo até desconectar
        except Exception as e:
            log.error(f"Falha ao conectar: {e}")
            return
        finally:
            await self.scheduler.stop()
            self.storage.close()


# ===================== MAIN =====================

async def main():
    if "--reset" in sys.argv:
        config = load_config()
        session = Path(config.get("SESSION_PATH",
                                   str(Path.home() / ".linkbot" / "session.sqlite")))
        if session.exists():
            session.unlink()
            print(f"🔥 Sessão apagada: {session}")
            print("Próxima execução vai pedir QR de novo.")
        return

    config = load_config()
    bot = LinkBot(config)
    await bot.run()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n👋 Bot encerrado pelo usuário.")
