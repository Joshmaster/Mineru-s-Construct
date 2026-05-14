---
name: Handoff de sessao
description: Estado da última sessão - lido ao iniciar para retomar sem perda de contexto
type: project
---

## Feito nesta sessao

### Discord token — atualizado 2026-05-13/14
- Token anterior estava sendo recusado com `401 Unauthorized`
- OWNER enviou novo token via catbox; salvo em `hyrule_env.py` e `local_secrets/tokens.md`
- Arquivo temporário apagado após leitura
- Discord bot reiniciado; voltou online como `LINK e Adventure kit ⚔ 📢🔊#6867`
- **Não mexer nesse token a menos que OWNER peça**
- **Nunca commitar `hyrule_env.py` nem `local_secrets/`**

### !img — Pollinations como padrão (2026-05-14)
- `link-bot/bot/skills/img_gerar.py` reescrito
- Padrão agora: Pollinations Flux (grátis, sem chave)
- Fallback automático: OpenRouter (Gemini por padrão) se Pollinations falhar
- `--gemini` ou `--openai` forçam OpenRouter diretamente
- Aspect ratio e overlay (`::`) continuam funcionando
- Commit: `e1c3e37` — push em `origin/master`
- WA bot reiniciado após mudança; PID `187641`

## Feito em sessoes anteriores (resumo)

- Codex/MAJORA: versão `0.130.0`
- WA Bridge: rodando porta `7334`, conectado
- `!spot`: busca inteligente via LLM + Spotify + fallback YouTube; envia MP3 direto
- `!figurinha`: começa em 60fps, degrada automaticamente
- Cards de lembrete: Star Wars via Pollinations Flux + PIL overlay
- `!fala`: edge-tts → MP3 → OGG/Opus PTT
- Timezone: `America/Sao_Paulo`
- Limpeza automática de inbox/baú/cards a cada 1h
- `!img` com overlay: `!img prompt :: texto sobre a imagem`

## Estado atual dos serviços
- Hyrule Proxy: rodando
- Discord bot: online (`LINK e Adventure kit ⚔ 📢🔊#6867`)
- Supervisor: rodando
- WA Bridge: rodando (porta `7334`, conectado)
- WhatsApp bot: rodando (PID `187641`)
- TRIFORCE daemon: rodando
- MAJORA watcher/Codex: rodando (`codex-cli 0.130.0`)
- MASTERSWORD watcher: rodando

## Pendente / próximas ideias
- `!img` com Pollinations: não testado ao vivo ainda — primeiro pedido real vai confirmar
- Nada crítico pendente

## Cuidados com dados sensíveis
- Não commitar: `link-bot/config/config.json`, `link-bot/.linkbot/`, `whatsapp-bridge/auth/`, `whatsapp-bridge/auth_backup*/`
- `hyrule_env.py` tem token Discord, chaves OpenRouter/Groq — nunca vai pro git
- `local_secrets/` — nunca vai pro git

---
Atualizado ao encerrar cada sessao. Nao acumula - sobrescreve.
