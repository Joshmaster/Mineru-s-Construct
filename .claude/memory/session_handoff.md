---
name: Handoff de sessao
description: Estado da ultima sessao - lido ao iniciar para retomar sem perder contexto
type: project
---

## Feito nesta sessao

### Migração WhatsApp: Neonize → Baileys (concluída)
- Neonize removido do pip e requirements.txt
- Bridge Node.js em `whatsapp-bridge/index.js` (porta 7334, REST)
- Bot Python recebe webhook na porta 7333, envia via bridge
- `WhatsAppClient` em `link-bot/bot/core/whatsapp_client.py` adapta a interface
- `startup_services.py` sobe bridge antes do bot WA
- QR disponível em `http://localhost:7334/qr` — já conectado, sessão salva em `whatsapp-bridge/auth/`
- Commited: "Migrate WhatsApp from Neonize to Baileys bridge"

### LLM — performance e circuit breaker
- `think=False` em Ollama (Discord + WhatsApp) — era `True`, causava 90s+ de delay
- Persona compacta para Ollama fallback (2 linhas, não o LINK_PERSONA.md completo)
- Histórico limitado a 4 msgs para Ollama (não 20)
- Circuit breaker: 3 falhas → bloqueia cloud provider por 180s
- Sentinel `_AUTH_ERROR` em `_post()`: 401 quebra loop de modelos imediatamente
- `classify_skill_intent`: catálogo só com nomes para Ollama + timeout 25s
- Resultado: Discord ~4s/msg, WhatsApp ~28s/msg (Ollama CPU)
- OpenRouter e Groq com chaves inválidas (401) — precisam de novas chaves

### Fix Discord bot token
- `DISCORD_REMINDER_CHANNEL_ID` não existia em `hyrule_env.py` → `ImportError` matava o `TOKEN` inteiro
- Corrigido: imports separados (TOKEN num `try`, `_REMINDER_CH_ID` em outro)
- Novo token salvo: `MTQ2NTcxODQwMjgzNTU1MDM5Mg.G5CFwL.*` (não registrar completo)

### Nomes de contato — sem OWNER/USER2
- `discord_forward.py`: usa `"josh"` / `"manu"` (não `"OWNER"` / `"USER2"`)
- `startup_services.py`: usa `["josh", "manu"]`
- `usuarios_extra.json`: removidas as chaves `"owner"` e `"user2"`
- `korok.py`: `"parceiro"` em vez de `"OWNER"` literal
- Ver [[feedback-contact-names]]

## Estado final dos serviços
- Hyrule Proxy: rodando
- Discord bot: online (token novo)
- Supervisor: rodando
- WA Bridge (Baileys): rodando (porta 7334, conectado)
- WhatsApp bot: rodando
- TRIFORCE / MAJORA / MASTERSWORD: rodando

## Cuidados com dados sensíveis
- Não commitar: `link-bot/config/config.json`, `link-bot/.linkbot/`, `whatsapp-bridge/auth/`, `DISCORD/files/qr_*.png`
- `hyrule_env.py` tem token Discord, chaves OpenRouter/Groq — nunca vai pro git
- Números reais de WhatsApp só no config local

## Pendente
- Novas chaves OpenRouter e Groq (atuais retornam 401)
- Quando cloud voltar: Discord ~1s, WhatsApp ~5s
- Testar fluxo real de WhatsApp com usuário mandando mensagem de verdade

---
Atualizado ao encerrar cada sessao. Nao acumula - sobrescreve.
