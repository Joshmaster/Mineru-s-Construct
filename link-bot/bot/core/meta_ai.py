"""
Proxy para Meta AI no WhatsApp.

Envia prompt para o chat do Meta AI via bridge Baileys e aguarda a imagem de
resposta de forma assíncrona. Zero token de API — usa o próprio WhatsApp.

Configuração obrigatória no config.json:
    "META_AI_JID": "número@s.whatsapp.net"

Uso nos módulos:
    # main.py — inicializar e interceptar respostas:
    from bot.core import meta_ai
    meta_ai.proxy.setup(client, config.get("META_AI_JID", ""))

    # Em _on_message, antes do allow list:
    if meta_ai.proxy.intercept(msg, download_fn):
        return

    # Skills e reminder_art:
    path = await meta_ai.proxy.ask_image(prompt, timeout=90)
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Callable, Awaitable, TYPE_CHECKING

if TYPE_CHECKING:
    from bot.core.whatsapp_client import WhatsAppClient, _Jid

log = logging.getLogger("meta_ai")

_meta_digits: set[str] = set()


@dataclass
class _Request:
    event: asyncio.Event = field(default_factory=asyncio.Event)
    image_path: str | None = None
    text: str = ""
    want_image: bool = True


class MetaAIProxy:
    def __init__(self):
        self._client: "WhatsAppClient | None" = None
        self._meta_jid: "_Jid | None" = None
        self._queue: list[_Request] = []

    def setup(self, client: "WhatsAppClient", jid_str: str):
        if not jid_str:
            return
        from bot.core.whatsapp_client import build_jid
        from bot.core import access as ac
        self._client = client
        self._meta_jid = build_jid(jid_str)
        digits = ac.digits(jid_str)
        if digits:
            _meta_digits.add(digits)
        log.info(f"Meta AI proxy configurado: {jid_str}")

    @property
    def configured(self) -> bool:
        return bool(self._client and self._meta_jid and _meta_digits)

    def is_from_meta_ai(self, msg: dict) -> bool:
        if not _meta_digits:
            return False
        from bot.core import access as ac
        for field_ in ("sender", "chat"):
            d = ac.digits(msg.get(field_, ""))
            if d and d in _meta_digits:
                return True
        return False

    async def intercept(
        self,
        msg: dict,
        download_fn: Callable[[], Awaitable[tuple[str | None, str | None]]],
    ) -> bool:
        """
        Chamado em _on_message para cada mensagem.
        Se for do Meta AI: baixa mídia se houver, resolve o pedido pendente,
        e retorna True (sinal para o main.py não processar como mensagem normal).
        """
        if not self.is_from_meta_ai(msg):
            return False

        text = msg.get("text", "")
        media_path = None
        if msg.get("media"):
            media_path, _ = await download_fn()

        log.info(f"Meta AI respondeu — imagem={bool(media_path)} texto={text[:60]!r}")

        for req in self._queue:
            if req.event.is_set():
                continue
            # ask_image espera imagem; ask_text aceita qualquer coisa
            if req.want_image and not media_path:
                continue
            req.image_path = media_path
            req.text = text
            req.event.set()
            break

        return True

    async def ask_image(self, prompt: str, timeout: int = 90) -> str | None:
        """Envia prompt ao Meta AI e aguarda uma imagem de resposta."""
        if not self.configured:
            return None

        req = _Request(want_image=True)
        self._queue.append(req)
        try:
            await self._client.send_message(self._meta_jid, prompt)
            await asyncio.wait_for(req.event.wait(), timeout=timeout)
            return req.image_path
        except asyncio.TimeoutError:
            log.warning(f"Meta AI timeout ({timeout}s): {prompt[:60]!r}")
            return None
        except Exception as e:
            log.error(f"Meta AI erro: {e}")
            return None
        finally:
            try:
                self._queue.remove(req)
            except ValueError:
                pass

    async def ask_text(self, prompt: str, timeout: int = 60) -> str | None:
        """Envia prompt ao Meta AI e aguarda uma resposta de texto."""
        if not self.configured:
            return None

        req = _Request(want_image=False)
        self._queue.append(req)
        try:
            await self._client.send_message(self._meta_jid, prompt)
            await asyncio.wait_for(req.event.wait(), timeout=timeout)
            return req.text or None
        except asyncio.TimeoutError:
            log.warning(f"Meta AI text timeout ({timeout}s)")
            return None
        except Exception as e:
            log.error(f"Meta AI erro: {e}")
            return None
        finally:
            try:
                self._queue.remove(req)
            except ValueError:
                pass


proxy = MetaAIProxy()
