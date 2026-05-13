---
name: Handoff de sessao
description: Estado da última sessão - lido ao iniciar para retomar sem perder contexto
type: project
---

## Feito nesta sessao

### TTS !fala — edge-tts com voz Brian (Microsoft Neural)
- Substituiu Delirius API/gtts (CDN bloqueado) por `edge-tts` local
- Pipeline: edge-tts → MP3 → ffmpeg → OGG/Opus → send ptt=true
- Voz padrão: `en-US-BrianMultilingualNeural` (escolhida pelo josh entre 8 vozes masculinas)
- Seleção de idioma: `!fala en: hello` / `!fala es: hola`
- Seleção de voz: `!fala voz AntonioNeural: texto`
- LLM melhora o texto antes de gerar o áudio (`rewrite_for_tts` em `llm.py`)
- `context.py reply_media` detecta extensão para rotear audio vs imagem
- `whatsapp_client.py send_audio` resolve MIME pelo ext do arquivo

### WhatsApp Bridge — melhorias
- Bridge escuta em `0.0.0.0` (acessível via Tailscale `100.121.86.1:7334`)
- Endpoint `/qr.png` adicionado (PNG bruto para abrir no browser)
- Endpoint `/qr/text` retorna string do QR em JSON
- `send/audio` aceita `mimetype` no body (não hardcoded)
- Logs de debug: `messages.upsert` (fromMe, jid, hasMsg) e `send/audio` (jid, ptt, mime, size, id)
- Sessão estava corrompida (device `:3` conflitando com `:4`) — limpo e refeito QR

### Meta AI Proxy — `bot/core/meta_ai.py`
- Proxy singleton sem token: envia prompt pro chat do Meta AI no WhatsApp, aguarda imagem
- `proxy.setup(client, jid)` — inicializa com META_AI_JID do config
- `proxy.ask_image(prompt, timeout=90)` — envia e aguarda imagem
- `proxy.intercept(msg, download_fn)` — chamado em `_on_message` antes do allow list
- `main.py` hookado: intercept antes do allow list, media baixada e entregue ao proxy
- **META_AI_JID ainda não configurado** — pendente o número do Meta AI no config.json

### !img — Meta AI como backend primário
- `img_gerar.py` tenta Meta AI primeiro, fallback OpenRouter
- Suporte a overlay de texto PIL: `!img prompt :: texto sobre a imagem`
- Uma skill só (`!img`) — sem `!imagine` separado

### Cards de lembrete — Star Wars
- `render_starwars_card(reminder)` em `reminder_art.py` — async, Pollinations Flux background + PIL overlay
- Layout 3 zonas: header escuro (título), imagem visível (horário com stroke 10px), painel sólido (remédios)
- Prompts PT-BR para Meta AI + prompts EN para Pollinations (fallback)
- **Atualmente usando `render_reminder_card` (card original PIL)** — aguarda META_AI_JID para ativar Star Wars
- Lógica de pré-geração (T-5min) implementada mas desativada — reativar quando Meta AI configurado

### Segurança
- `whatsapp-bridge/auth_backup*/` adicionado ao `.gitignore` (continha creds.json e pre-keys reais)
- Números de telefone reais presentes nos sender-key files do backup — nunca foram commitados

## Estado final dos serviços
- Hyrule Proxy: rodando
- Discord bot: online
- Supervisor: rodando
- WA Bridge (Baileys): rodando (porta 7334, conectado, sessão nova)
- WhatsApp bot: rodando (código atualizado com rewrite_for_tts e meta_ai)
- TRIFORCE / MAJORA / MASTERSWORD: rodando

## Pendente
- Configurar `META_AI_JID` no `link-bot/config/config.json` com número do Meta AI no WhatsApp
- Após configurar META_AI_JID: ativar `render_starwars_card` no scheduler (substituir `render_reminder_card`)
- Testar `!img` com Meta AI gerado (requer META_AI_JID)

## Cuidados com dados sensíveis
- Não commitar: `link-bot/config/config.json`, `link-bot/.linkbot/`, `whatsapp-bridge/auth/`, `whatsapp-bridge/auth_backup*/`
- `hyrule_env.py` tem token Discord, chaves OpenRouter/Groq — nunca vai pro git
- Números reais de WhatsApp só no config local

---
Atualizado ao encerrar cada sessao. Nao acumula - sobrescreve.
