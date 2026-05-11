"""
Cliente HTTP para o WhatsApp Bridge (Baileys).
Substitui o NewAClient do neonize com a mesma interface pública.
"""

import asyncio
import base64
import logging
from pathlib import Path

import httpx

log = logging.getLogger("wa-client")


class _Jid:
    """JID compatível com código que lê .User e .Server."""

    __slots__ = ("User", "Server")

    def __init__(self, user: str, server: str = "s.whatsapp.net"):
        self.User = str(user or "").split("@")[0]
        self.Server = server

    def __str__(self) -> str:
        return f"{self.User}@{self.Server}"

    def __repr__(self) -> str:
        return f"<Jid {self}>"


def build_jid(number: str, server: str = "s.whatsapp.net") -> _Jid:
    """Constrói um _Jid a partir de número e servidor (compatível com neonize.utils.build_jid)."""
    number = str(number or "")
    if "@" in number:
        parts = number.split("@", 1)
        return _Jid(parts[0], parts[1] if len(parts) > 1 else server)
    return _Jid(number, server)


class _MsgResp:
    """Resposta de envio com ID da mensagem."""
    __slots__ = ("ID", "ServerID")

    def __init__(self, msg_id: str = ""):
        self.ID = msg_id
        self.ServerID = msg_id


class WhatsAppClient:
    """Wrapper HTTP sobre o bridge Baileys. Interface compatível com neonize."""

    def __init__(self, bridge_url: str = "http://localhost:7334"):
        self._url = bridge_url.rstrip("/")
        self._http: httpx.AsyncClient | None = None

    def _client(self) -> httpx.AsyncClient:
        if self._http is None or self._http.is_closed:
            self._http = httpx.AsyncClient(base_url=self._url, timeout=30)
        return self._http

    @staticmethod
    def _jid_str(jid) -> str:
        if isinstance(jid, str):
            return jid
        if isinstance(jid, _Jid):
            return str(jid)
        user = getattr(jid, "User", "") or ""
        server = getattr(jid, "Server", "s.whatsapp.net") or "s.whatsapp.net"
        return f"{user}@{server}"

    @staticmethod
    def _b64(path: str) -> str:
        return base64.b64encode(Path(path).read_bytes()).decode()

    async def send_message(self, jid, text) -> _MsgResp:
        if text is None:
            return _MsgResp()
        http = self._client()
        resp = await http.post("/send/text", json={"jid": self._jid_str(jid), "text": str(text)})
        resp.raise_for_status()
        data = resp.json()
        return _MsgResp(data.get("id", ""))

    async def send_image(self, jid, path: str, caption: str = "") -> _MsgResp:
        ext = Path(path).suffix.lower().lstrip(".")
        mime = {"jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png",
                "gif": "image/gif", "webp": "image/webp"}.get(ext, "image/jpeg")
        http = self._client()
        resp = await http.post("/send/image", json={
            "jid": self._jid_str(jid),
            "base64": self._b64(path),
            "caption": caption or "",
            "mimeType": mime,
        })
        resp.raise_for_status()
        return _MsgResp(resp.json().get("id", ""))

    async def send_audio(self, jid, path: str, ptt: bool = False):
        http = self._client()
        resp = await http.post("/send/audio", json={
            "jid": self._jid_str(jid),
            "base64": self._b64(path),
            "ptt": ptt,
        })
        resp.raise_for_status()

    async def send_sticker(self, jid, path: str):
        http = self._client()
        resp = await http.post("/send/sticker", json={
            "jid": self._jid_str(jid),
            "base64": self._b64(path),
        })
        resp.raise_for_status()

    async def send_reaction(self, jid, msg_id: str, emoji: str, from_me: bool = False):
        http = self._client()
        try:
            resp = await http.post("/send/reaction", json={
                "jid": self._jid_str(jid),
                "msgId": msg_id,
                "emoji": emoji,
                "fromMe": from_me,
            })
            resp.raise_for_status()
        except Exception as e:
            log.debug(f"reaction falhou (não-crítico): {e}")

    async def build_reaction(self, jid, my_jid, message_id: str, emoji: str):
        """Envia reação diretamente; retorna None para send_message ignorar."""
        await self.send_reaction(jid, message_id, emoji)
        return None

    async def send_chat_presence(self, jid, presence, media=None):
        presence_str = "composing" if "COMPOSING" in str(presence).upper() else "paused"
        http = self._client()
        try:
            await http.post("/send/presence", json={
                "jid": self._jid_str(jid),
                "presence": presence_str,
            })
        except Exception as e:
            log.debug(f"presence falhou: {e}")

    async def download_media(self, raw_key: dict, raw_message: dict) -> bytes | None:
        """Baixa mídia via bridge e retorna bytes, ou None se falhar."""
        http = self._client()
        try:
            resp = await http.post("/download/media", json={
                "rawKey": raw_key,
                "rawMessage": raw_message,
            }, timeout=60)
            resp.raise_for_status()
            b64 = resp.json().get("base64", "")
            return base64.b64decode(b64) if b64 else None
        except Exception as e:
            log.debug(f"download media falhou: {e}")
            return None

    async def get_me(self):
        """Retorna objeto com JID do bot (número conectado)."""
        http = self._client()
        try:
            resp = await http.get("/status")
            resp.raise_for_status()
            data = resp.json()
            number = data.get("number", "") or data.get("jid", "")
            if number:
                return type("Me", (), {"JID": build_jid(number)})()
        except Exception:
            pass
        return type("Me", (), {"JID": build_jid("unknown")})()

    async def is_connected(self) -> bool:
        try:
            resp = await self._client().get("/status", timeout=3)
            return resp.json().get("connected", False)
        except Exception:
            return False

    async def close(self):
        if self._http and not self._http.is_closed:
            await self._http.aclose()
