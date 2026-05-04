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
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import List

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


# ===================== CONFIG / LOG =====================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(message)s",
    datefmt="%H:%M:%S",
)
for noisy in ("whatsmeow", "whatsmeow.Client",
              "whatsmeow.Client.Socket", "neonize"):
    logging.getLogger(noisy).setLevel(logging.WARNING)

log = logging.getLogger("link-bot")


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

        # Router
        self.router = Router()
        load_all_skills(self.router)

        # JIDs reais por número (populado quando mensagem chega)
        self.user_jids: dict = {}

        # Bot identity (preenchido no on_connected)
        self.my_jid = None

        # Allow list: quem pode falar com o bot
        self.allow_list = config.get("ALLOW_FROM", [])
        # Normaliza pra só dígitos
        self.allow_list = [
            "".join(c for c in n if c.isdigit())
            for n in self.allow_list
        ]
        self.allow_list = [n for n in self.allow_list if n]

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
            raw = cfg.get("ALLOW_FROM", [])
            self.allow_list = [
                "".join(c for c in n if c.isdigit()) or n
                for n in raw
            ]
            self.allow_list = [n for n in self.allow_list if n]
        except Exception:
            pass

    def _is_allowed(self, sender_number: str) -> bool:
        """Verifica se o remetente tá na allow_list (relê config a cada check)."""
        self._reload_allow_list()
        if not self.allow_list:
            return False  # default deny
        return sender_number in self.allow_list

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
            sender_number = getattr(sender, "User", "")
            is_group = ev.Info.MessageSource.IsGroup
        except Exception as e:
            log.debug(f"falha ao extrair source: {e}")
            return

        # Allow list (só DM)
        if not is_group:
            if not self._is_allowed(sender_number):
                log.warning(f"Mensagem de {sender_number} BLOQUEADA (não está na allow_list).")
                # Avisa o remetente que pode se registrar com !eu
                try:
                    await self.client.send_message(
                        chat_jid,
                        "🔒 Acesso negado. Se você é o dono, manda `!eu` pra se registrar."
                    )
                except Exception:
                    pass
                return

        # Texto
        text = self._extract_text(ev.Message)
        if not text or not text.strip():
            return

        log.info(f"📩 [{sender_number}] {text[:80]}")

        # Armazena JID real para uso no HTTP API
        self.user_jids[sender_number] = chat_jid

        # Match no router
        match = self.router.match(text)
        if match is None:
            # Fallback LLM com persona Link (OpenRouter → Groq)
            try:
                reply = await asyncio.get_event_loop().run_in_executor(
                    None, _llm.chat, sender_number, text
                )
                await self.client.send_message(chat_jid, reply)
            except Exception as e:
                log.error(f"LLM fallback falhou: {e}")
                await self.client.send_message(chat_jid, "🌀")
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
            has_media=has_media,
            media_type=media_kind,
            media_path=media_path,
            client=self.client,
            storage=self.storage,
            config=self.config,
            router=self.router,
        )

        # Dispara
        try:
            await skill.handler(ctx)
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
                if self.path != "/send":
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

                    # Usa JID real capturado quando usuário enviou mensagem
                    jid = bot_ref.user_jids.get(to_num)
                    if jid is None:
                        raise ValueError(f"JID desconhecido para {to_num} — usuario precisa ter mandado mensagem antes")

                    log.info(f"📤 [{to_num}] {msg[:60]}")
                    fut = asyncio.run_coroutine_threadsafe(
                        bot_ref.client.send_message(jid, msg), loop
                    )
                    fut.result(timeout=15)
                    self.send_response(200)
                    self.end_headers()
                    self.wfile.write(b'{"ok":true}')
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
