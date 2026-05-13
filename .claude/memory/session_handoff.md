---
name: Handoff de sessao
description: Estado da última sessão - lido ao iniciar para retomar sem perder contexto
type: project
---

## Feito nesta sessao

### Meta AI proxy — investigação e descarte
- Implementamos `bot/core/meta_ai.py` (proxy singleton via Baileys)
- Investigação completa: Baileys retorna 200 OK mas mensagem não chega ao Meta AI
- Meta AI é endpoint especial da Meta, não contato WhatsApp normal — só funciona via app oficial
- Meta baniu chatbots gerais no WhatsApp (out/2025) e bloqueia acesso por APIs não-oficiais
- **Proxy removido de `img_gerar.py` e `reminder_art.py`** — o arquivo `meta_ai.py` ainda existe mas não é usado

### !img — OpenRouter direto
- Removida tentativa Meta AI (que adicionava 90s de delay)
- `!img` vai direto pro OpenRouter agora
- Suporte a overlay de texto: `!img prompt :: texto sobre a imagem`
- Modelos: Gemini 2.5 Flash Image (padrão) e OpenAI GPT-5 Image

### Cards de lembrete — Star Wars via Pollinations
- `render_starwars_card(reminder)` em `reminder_art.py` — async, Pollinations Flux + PIL overlay
- Layout 3 zonas: header escuro (título), imagem visível (horário com stroke 10px), painel sólido (remédios)
- Scheduler com pré-render T-5min via `asyncio.create_task` + cache `_card_cache`
- Fallback: card PIL original se Pollinations falhar
- **Ativo e funcionando** — testado, card gerado e enviado pro PV

### Bridge Baileys — melhorias de debug
- `type=append` para Meta AI JID agora detectado (foi necessário para o debug)
- Chat store via `chats.upsert`/`chats.update` events
- Log de `msgType` (tipo interno da mensagem) adicionado para debug
- Endpoint `/chats` adicionado

### TTS !fala — mantido do handoff anterior
- edge-tts → MP3 → ffmpeg OGG/Opus → send PTT
- Voz padrão: `en-US-BrianMultilingualNeural`
- LLM melhora texto antes de gerar áudio (`rewrite_for_tts`)

## Estado atual dos serviços
- Bridge Baileys: rodando (porta 7334, sessão ativa)
- WhatsApp bot: rodando (`/tmp/wapp_bot.log`)
- Supervisor: rodando
- Discord bot: rodando

### !figurinha animada — 60fps
- `bot/core/sticker.py`: attempts list começa em 60fps agora
- Degrada automaticamente (60→30→15→8fps) se arquivo ultrapassar 500KB
- Commit: `893fc62`

## Pendente / próximas ideias
- `!img` funciona mas depende das chaves OpenRouter (verificar se estão válidas em `hyrule_env.py`)
- Geração de imagem: pensar em alternativa ao Meta AI (Pollinations já funciona pra cards, pode ser opção pro !img também)
- TRIFORCE / MAJORA / MASTERSWORD: rodam mas não foram tocados nesta sessão

## Cuidados com dados sensíveis
- Não commitar: `link-bot/config/config.json`, `link-bot/.linkbot/`, `whatsapp-bridge/auth/`, `whatsapp-bridge/auth_backup*/`
- `hyrule_env.py` tem token Discord, chaves OpenRouter/Groq — nunca vai pro git
- `META_AI_JID` está no config.json local (não commitado)

---
Atualizado ao encerrar cada sessao. Nao acumula - sobrescreve.
