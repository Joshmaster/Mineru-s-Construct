---
name: Handoff de sessao
description: Estado da última sessão - lido ao iniciar para retomar sem perder contexto
type: project
---

## Feito nesta sessao

### Codex / MAJORA — atualização 2026-05-13
- GitHub latest (`https://github.com/openai/codex/releases/latest`) confirmado como `0.130.0`
- `npm install -g @openai/codex@latest` executado
- Versão validada: `codex-cli 0.130.0`
- Pacote global validado: `@openai/codex@0.130.0`
- Binário ativo: `/home/joshlink/.nvm/versions/node/v22.22.2/bin/codex`
- `project_hyrule.md` atualizado com a versão da MAJORA/Codex
- MAJORA watcher reiniciado após update; PID atual `159011`

### WhatsApp Bridge — correção 2026-05-13
- Investigado alerta de bridge parada após update do Codex
- Causa: bridge funcional em `7334`, mas rodada manualmente como `node index.js` com log em `/tmp/bridge.log`; `.bridge_pid` estava stale apontando para PID morto `157900`
- Isso fazia `startup_services.py status` mostrar parado e novas tentativas falharem com `EADDRINUSE`
- Processo solto `150121` e tails antigos de `/tmp/bridge.log` foram encerrados
- Bridge reiniciada pelo `startup_services` com PID correto `159181`
- Validação: `GET http://localhost:7334/status` retornou `{"ok":true,"connected":true,"hasQr":false}`

### Limpeza de baú/inbox/mídias geradas — 2026-05-13
- OWNER pediu limpar o baú e apagar mídias atuais do inbox/cards gerados
- Apagados arquivos de `~/.linkbot/bau`, `~/.linkbot/inbox` e `~/Agents/.linkbot/reminder_cards`
- `link-bot/bot/main.py` agora mantém `~/.linkbot/inbox` e `~/Agents/.linkbot/reminder_cards` por até 24h
- Limpeza automática roda ao conectar e depois a cada 1h
- WhatsApp bot reiniciado para carregar a regra; PID atual `159848`

### Delirius Spotify — ajuste 2026-05-13
- `!spot`/`!spotify` agora aceita busca por texto além de link (`!spot zelda lost woods`)
- Busca usa `/search/spotify` e pega o primeiro resultado antes de chamar `/download/spotifydl`
- Corrigidos headers da Delirius para evitar 403 por anti-bot simples
- `/download/spotifydl` agora usa timeout 90s e 2 tentativas para reduzir falso "API fora agora"
- Áudio baixado (MP3 com capa embutida) agora é convertido com ffmpeg para OGG/Opus estéreo 48k sem metadata antes de enviar no WhatsApp, para evitar arquivo recebido mas não reproduzível
- Legenda do envio Spotify agora pareia o áudio com título/artista e link oficial (`Spotify: https://open.spotify.com/track/...`)
- Alias `!spoty` aceito; busca normaliza `mr.bluesky`, `bluesky`, `eletric`, `lith` para reduzir erro de digitação comum
- Testado: `zelda lost woods` retorna `Lost Woods - 3000m` e URL de mídia no JSON
- WhatsApp bot reiniciado para carregar a regra; PID atual `162353`
- Atualização posterior: busca textual do `!spot` passa pelo LLM antes da Delirius para corrigir digitação, entender intenção e priorizar música original/oficial quando o usuário pedir
- `!spot` agora gera até 4 consultas candidatas via LLM, cai no texto original se o LLM falhar, busca até 6 resultados por consulta e evita cover/remix/karaoke/live quando o pedido indica original
- Testado: `mr.bluesky original` virou consultas como `mr blue sky original` e retornou `Mr. Blue Sky — Electric Light Orchestra`
- WhatsApp bot reiniciado após essa atualização; PID atual `166549`
- Ajuste final pedido pelo OWNER: original/oficial virou padrão do `!spot`; o usuário não precisa escrever "original"
- Cover/remix/karaoke/live/instrumental/sped up/slowed/etc. só são aceitos quando o usuário pedir explicitamente esse tipo de versão
- Testado: `mr.bluesky` retorna `Mr. Blue Sky — Electric Light Orchestra`; `Aragorn's Coronationg Song-clamavi` corrige digitação e retorna `Aragorn's Coronation Song — Clamavi De Profundis`
- WhatsApp bot reiniciado após esse ajuste; PID atual `167289`
- Correção após erro da Manu: quando `/download/spotifydl` retorna falha mesmo após a busca achar a faixa, `!spot` agora tenta fallback automático no YouTube, baixa o MP3 por `/download/ytmp3` e envia o arquivo
- Fallback de YouTube inclui `YouTube: <url>` na legenda do áudio, para mandar arquivo + link
- Caso observado: `!spot nemo nightwish` achou `Nemo — Nightwish`, mas Spotify download retornou `Download failed.`; fallback YouTube encontra `Nightwish - Nemo [OFFICIAL VIDEO]`
- WhatsApp bot reiniciado após esse ajuste; PID atual `167948`

### Relógio / timezone — correção 2026-05-13
- Sistema estava em `Etc/UTC`, fazendo `date` e alguns timestamps locais aparecerem 3h à frente
- Corrigido com `sudo timedatectl set-timezone America/Sao_Paulo`
- `/etc/localtime` agora aponta para `America/Sao_Paulo`
- `/etc/timezone` criado/atualizado com `America/Sao_Paulo`
- Validação: `date` mostra horário local `-03`; Python `datetime.now()` bate com `ZoneInfo("America/Sao_Paulo")`

### Discord bot — restart 2026-05-13
- Discord bot reiniciado para carregar estado atual do projeto; PID atual `168455`
- Validação: `startup_services.py status` mostra Discord online

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
- Bridge Baileys: rodando (porta 7334, PID `159181`, conectado)
- WhatsApp bot: rodando (PID `167948`, logs em `link-bot/.linkbot/whatsapp_err.log`)
- Supervisor: rodando (PID `157898`)
- Discord bot: rodando (PID `168455`)
- TRIFORCE daemon: rodando (PID `157912`)
- MAJORA watcher/Codex: rodando com `codex-cli 0.130.0`
- MASTERSWORD watcher: rodando (PID `157914`)
- Hyrule Proxy: rodando (PID `157895`)

### !figurinha animada — 60fps
- `bot/core/sticker.py`: attempts list começa em 60fps agora
- Degrada automaticamente (60→30→15→8fps) se arquivo ultrapassar 500KB
- Commit: `893fc62`

## Pendente / próximas ideias
- `!img` funciona mas depende das chaves OpenRouter (verificar se estão válidas em `hyrule_env.py`)
- Geração de imagem: pensar em alternativa ao Meta AI (Pollinations já funciona pra cards, pode ser opção pro !img também)
- TRIFORCE / MASTERSWORD: rodam mas não foram tocados nesta sessão

## Cuidados com dados sensíveis
- Não commitar: `link-bot/config/config.json`, `link-bot/.linkbot/`, `whatsapp-bridge/auth/`, `whatsapp-bridge/auth_backup*/`
- `hyrule_env.py` tem token Discord, chaves OpenRouter/Groq — nunca vai pro git
- `META_AI_JID` está no config.json local (não commitado)

---
Atualizado ao encerrar cada sessao. Nao acumula - sobrescreve.
