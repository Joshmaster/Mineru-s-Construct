"""
Contexto da mensagem - passado pra cada skill como argumento.

Encapsula:
- info da mensagem (autor, texto, mídia anexa)
- referência ao client neonize (pra responder)
- storage compartilhado (TODOs, notas, lembretes)
- config global
"""

from dataclasses import dataclass, field
from typing import Optional, Any


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
    client: Any = None              # NewAClient do neonize
    storage: Any = None             # instância de Storage
    config: Any = None              # dict de config
    router: Any = None              # pra skill /ajuda listar comandos

    async def reply(self, text: str):
        """Envia resposta de texto pro chat."""
        if self.client is None:
            print(f"[reply mock] {text}")
            return
        try:
            await self.client.send_message(self.chat_jid, text)
        except Exception as e:
            print(f"[reply err] {e}")

    async def react(self, emoji: str):
        """Reage à mensagem com emoji."""
        if self.client is None or not self.message_id or self.my_jid is None:
            return
        try:
            reaction = await self.client.build_reaction(
                self.chat_jid, self.my_jid, self.message_id, emoji
            )
            await self.client.send_message(self.chat_jid, reaction)
        except Exception:
            pass

    async def typing(self):
        """Mostra 'digitando...' no chat."""
        if self.client is None:
            return
        try:
            from neonize.utils.enum import ChatPresence, ChatPresenceMedia
            await self.client.send_chat_presence(
                self.chat_jid,
                ChatPresence.CHAT_PRESENCE_COMPOSING,
                ChatPresenceMedia.CHAT_PRESENCE_MEDIA_TEXT,
            )
        except Exception:
            pass

    async def stop_typing(self):
        """Para o indicador de digitação."""
        if self.client is None:
            return
        try:
            from neonize.utils.enum import ChatPresence, ChatPresenceMedia
            await self.client.send_chat_presence(
                self.chat_jid,
                ChatPresence.CHAT_PRESENCE_PAUSED,
                ChatPresenceMedia.CHAT_PRESENCE_MEDIA_TEXT,
            )
        except Exception:
            pass

    async def send_image(self, file_path: str, caption: str = ""):
        """Envia imagem com legenda opcional."""
        if self.client is None:
            print(f"[send_image mock] {file_path}")
            return
        try:
            await self.client.send_image(self.chat_jid, file_path, caption=caption or None)
        except Exception as e:
            print(f"[send_image err] {e}")
            if caption:
                await self.reply(caption)

    async def send_audio_ptt(self, file_path: str):
        """Envia áudio como nota de voz (PTT)."""
        if self.client is None:
            return
        try:
            await self.client.send_audio(self.chat_jid, file_path, ptt=True)
        except Exception as e:
            print(f"[send_audio_ptt err] {e}")

    async def reply_media(self, file_path: str, caption: str = "",
                           as_sticker: bool = False):
        """Envia mídia (imagem/vídeo/sticker) pro chat."""
        if self.client is None:
            print(f"[reply_media mock] {file_path} (sticker={as_sticker})")
            return
        try:
            if as_sticker:
                if hasattr(self.client, "send_sticker"):
                    await self.client.send_sticker(self.chat_jid, file_path)
                else:
                    await self.client.send_message(self.chat_jid, file_path)
            else:
                await self.send_image(file_path, caption)
                return
            if caption:
                await self.client.send_message(self.chat_jid, caption)
        except Exception as e:
            print(f"[reply_media err] {e}")
