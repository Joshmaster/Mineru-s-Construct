---
name: feedback-contact-names
description: Nomes de contato Discord e WhatsApp — usar apelidos reais, nunca OWNER/USER2
metadata:
  type: feedback
---

Usar sempre nomes/apelidos reais ao referenciar contatos em DMs ou chats, nunca placeholders internos.

**Por que:** "OWNER" e "USER2" são aliases internos de sistema, não nomes reais. Aparecer em mensagens ou logs causa confusão.

**Como aplicar:**
- Discord DM targets (API `/delete`, `/send`, etc.): `"josh"` e `"manu"` — nunca `"OWNER"` ou `"USER2"`
- `startup_services.py` usa `["josh", "manu"]` para apagar mensagens
- `discord_forward.py` encaminha para `"josh"` ou `"manu"`
- `usuarios_extra.json` não tem mais as chaves `"owner"` / `"user2"`
- Em skills WA (ex: `korok.py`): usar `"parceiro"` em vez de literal `OWNER`
- Mapeamento atual: Josh = `257334783930007552`, Manu = `512825467397603328`
