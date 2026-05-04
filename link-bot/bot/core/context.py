"""
Contexto da mensagem - passado pra cada skill como argumento.

Encapsula:
- info da mensagem (autor, texto, mídia anexa)
- referência ao client neonize (pra responder)
- storage compartilhado (TODOs, notas, lembretes)
- config global
"""

from dataclasses import dataclass
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

    async def reply_media(self, file_path: str, caption: str = "",
                           as_sticker: bool = False):
        """Envia mídia (imagem/vídeo/sticker) pro chat."""
        if self.client is None:
            print(f"[reply_media mock] {file_path} (sticker={as_sticker})")
            return
        try:
            if as_sticker:
                # neonize: send_sticker(jid, path)
                if hasattr(self.client, "send_sticker"):
                    await self.client.send_sticker(self.chat_jid, file_path)
                else:
                    # fallback: envia como arquivo
                    await self.client.send_message(
                        self.chat_jid, file_path
                    )
            else:
                await self.client.send_message(
                    self.chat_jid, file_path
                )
            if caption:
                await self.client.send_message(self.chat_jid, caption)
        except Exception as e:
            print(f"[reply_media err] {e}")
