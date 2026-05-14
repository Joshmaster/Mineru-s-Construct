"""
Contexto da mensagem - passado pra cada skill como argumento.

Encapsula:
- info da mensagem (autor, texto, mídia anexa)
- referência ao WhatsAppClient (pra responder)
- storage compartilhado (TODOs, notas, lembretes)
- config global
"""

from dataclasses import dataclass, field
from typing import Optional, Any
import asyncio


@dataclass
class MessageContext:
    """Tudo que a skill precisa pra processar uma mensagem."""

    # Texto puro recebido
    raw_text: str
    # Texto após router remover trigger/vocativo
    args_text: str

    # Identificação
    sender_jid: Any         # JID do remetente
    chat_jid: Any           # JID do chat (DM ou grupo)
    is_group: bool = False

    # Identidade
    message_id: str = ""    # ID da mensagem (pra reagir)
    my_jid: Any = None      # JID do próprio bot
    pushname: str = ""      # Nome de exibição do remetente

    # Mídia anexa (se houver)
    has_media: bool = False
    media_type: Optional[str] = None      # 'image', 'video', 'audio', 'document'
    media_path: Optional[str] = None      # caminho local após download

    # Referências do bot
    client: Any = None              # WhatsAppClient (bridge Baileys)
    storage: Any = None             # instância de Storage
    config: Any = None              # dict de config
    router: Any = None              # pra skill /ajuda listar comandos

    def _sender_str(self) -> str:
        jid = self.sender_jid
        if jid is None:
            return ""
        return str(jid) if not hasattr(jid, "User") else f"{jid.User}@{getattr(jid, 'Server', 's.whatsapp.net')}"

    async def reply(self, text: str):
        """Envia resposta de texto pro chat, citando a mensagem original."""
        if self.client is None:
            print(f"[reply mock] {text}")
            return
        try:
            await self.client.send_message(
                self.chat_jid, text,
                quoted_id=self.message_id or "",
                quoted_sender=self._sender_str() if self.is_group else "",
            )
        except Exception as e:
            print(f"[reply err] {e}")

    async def react(self, emoji: str):
        """Reage à mensagem com emoji."""
        if self.client is None or not self.message_id or not emoji:
            return
        try:
            result = await self.client.build_reaction(
                self.chat_jid, self.my_jid, self.message_id, emoji
            )
            # Bridge envia reação direto e retorna None; Neonize retornava proto
            if result is not None:
                await self.client.send_message(self.chat_jid, result)
        except Exception:
            pass

    async def typing(self):
        """Mostra 'digitando...' no chat."""
        if self.client is None:
            return
        try:
            await self.client.send_chat_presence(self.chat_jid, "COMPOSING")
        except Exception:
            pass

    async def stop_typing(self):
        """Para o indicador de digitação."""
        if self.client is None:
            return
        try:
            await self.client.send_chat_presence(self.chat_jid, "PAUSED")
        except Exception:
            pass

    async def send_image(self, file_path: str, caption: str = ""):
        """Envia imagem com legenda opcional, citando a mensagem original."""
        if self.client is None:
            print(f"[send_image mock] {file_path}")
            return
        try:
            await asyncio.wait_for(
                self.client.send_image(
                    self.chat_jid, file_path,
                    caption=caption or None,
                    quoted_id=self.message_id or "",
                    quoted_sender=self._sender_str() if self.is_group else "",
                ),
                timeout=12,
            )
        except asyncio.TimeoutError:
            print(f"[send_image timeout] {file_path}")
            if caption:
                await self.reply(caption)
        except Exception as e:
            print(f"[send_image err] {e}")
            if caption:
                await self.reply(caption)

    async def send_buttons(self, text: str, buttons: list[tuple[str, str]], footer: str = "") -> bool:
        return False

    async def send_list(self, title: str, description: str, rows: list[tuple[str, str, str]], button_text: str = "Abrir", footer: str = "") -> bool:
        return False

    async def send_audio_ptt(self, file_path: str):
        """Envia áudio como nota de voz (PTT), citando a mensagem original."""
        if self.client is None:
            return
        try:
            await self.client.send_audio(
                self.chat_jid, file_path, ptt=True,
                quoted_id=self.message_id or "",
                quoted_sender=self._sender_str() if self.is_group else "",
            )
        except Exception as e:
            print(f"[send_audio_ptt err] {e}")

    async def reply_media(self, file_path: str, caption: str = "",
                           as_sticker: bool = False):
        """Envia mídia detectando o tipo, citando a mensagem original."""
        if self.client is None:
            print(f"[reply_media mock] {file_path} (sticker={as_sticker})")
            return
        qid = self.message_id or ""
        qsender = self._sender_str() if self.is_group else ""
        try:
            ext = file_path.rsplit(".", 1)[-1].lower() if "." in file_path else ""
            if as_sticker:
                if hasattr(self.client, "send_sticker"):
                    await self.client.send_sticker(self.chat_jid, file_path, quoted_id=qid, quoted_sender=qsender)
                else:
                    await self.client.send_message(self.chat_jid, file_path, quoted_id=qid, quoted_sender=qsender)
                if caption:
                    await self.client.send_message(self.chat_jid, caption)
            elif ext in ("mp3", "ogg", "m4a", "wav", "aac", "opus"):
                await self.client.send_audio(self.chat_jid, file_path, ptt=False, quoted_id=qid, quoted_sender=qsender)
                if caption:
                    await self.client.send_message(self.chat_jid, caption)
            else:
                await self.send_image(file_path, caption)
        except Exception as e:
            print(f"[reply_media err] {e}")
