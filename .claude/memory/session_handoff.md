---
name: Handoff interagentes Hyrule
description: Ponte entre TRIFORCE/Claude, MAJORA/Codex e MASTERSWORD/OpenCode; quem sai escreve para quem entrar continuar
type: project
---

## Recado para a proxima camada/agente

Este arquivo e o canal de handoff entre TRIFORCE/Claude, MAJORA/Codex e MASTERSWORD/OpenCode. Leia primeiro ao retomar contexto; sobrescreva ao encerrar ou transferir trabalho para outra camada.

## Sessao encerrada em 2026-05-15

### Feito
- Migração de mídia/música:
  - `link-bot/bot/skills/delirius_dl.py` passou a usar `yt-dlp` local para YouTube MP3/MP4.
  - Spotify agora resolve localmente por busca no YouTube/YouTube Music; Delirius removido do fluxo de música.
  - Instagram e Twitter/X tentam local primeiro e mantêm Delirius só como fallback para casos bloqueados.
  - `DISCORD/link_discord.py` também usa helpers locais para `spot`/`yt`.
  - `requirements.txt` inclui `yt-dlp`.
- Fallback LLM:
  - Groq removido do repo/configs rastreadas e do OpenCode local.
  - Hierarquia atual validada: Cerebras -> Mistral -> OpenRouter -> Ollama.
  - `check_llms.py` atualizado e validado sem expor chaves.
- WhatsApp apagar mensagens:
  - Bot agora registra IDs de mensagens, áudios, imagens, stickers e legendas enviadas por chat em `.linkbot/sent_messages.json`.
  - Comandos como `apaga suas mensagens`, `limpa o chat`, `apaga tudo`, `apaga as últimas 5 mensagens`, `apaga essa mensagem` funcionam para mensagens futuras registradas.
  - Limpeza de conversa fica silenciosa para não sujar o chat com confirmação nova.
  - Mensagens antigas anteriores ao registro não puderam ser apagadas por falta de IDs.
- Remoções de funções:
  - Removido print de URL/site: `delirius_print`, `!print`, `!screenshot`, `!screen`.
  - Removidas skills de PC do WhatsApp: `pc_abrir`, `pc_status`, `pc_volume`, `pc_screenshot`.
  - Removidas skills TOTK utilitárias: `korok_achei`, `korok_quantos`, `citacao`.
  - Menus, README e menu do Discord limpos das referências removidas.
  - Bot WhatsApp passou a carregar 51 skills.
- Persona Link:
  - `OPENCODE/roaming/LINK_PERSONA.md` ajustada para Link mais canônico: poucas palavras, presença calma, coragem e cuidado por ação.
  - Adicionada seção `Modo de ação — proatividade`: agir/delegar quando a intenção estiver clara, perguntar só dado essencial, tentar alternativa razoável em falhas.
- OWNER validado:
  - Discord: resposta `Confirmado link` recebida de `josh_barbosa`; salvo em `.task_memory/owner_discord_identity_confirmed.json`.
  - WhatsApp: resposta `Sou eu link` recebida do ID `75771930505309`; salvo em `.task_memory/owner_whatsapp_identity_confirmed.json`.
  - Primeiro envio WhatsApp para `@s.whatsapp.net` deu OK mas não chegou; reenviado via `75771930505309@lid`, que é o JID real recente.

### Commits subidos
- `f312bcf` Use local media downloads and update LLM fallbacks
- `51861c2` Track WhatsApp bot messages for deletion
- `175595c` Make WhatsApp cleanup commands silent
- `3453ae1` Remove URL screenshot skill
- `65e722c` Remove PC and TOTK utility skills
- `79d3d3b` Remove stale Discord Hyrule menu entries
- `0588226` Make Link persona warmer in short replies
- `3eb9e38` Tune Link persona toward canon restraint
- `5ef2cda` Add proactive action mode to Link persona

### Estado dos serviços ao encerrar
- Hyrule Proxy: rodando
- Discord bot: online
- Supervisor: rodando
- WA Bridge: rodando na porta 7334
- WhatsApp bot: rodando
- FFmpeg: instalado
- TRIFORCE: rodando
- MAJORA: rodando
- MASTERSWORD: rodando
- itch-monitor: rodando
- WhatsApp conectado (`hasQr=false`)

### Estado Git
- `git status --short` mostrou somente `.task_memory/` untracked.
- `.task_memory/` contém confirmação local de identidade OWNER via Discord e WhatsApp; não foi commitado.

### Pendências / atenção
- Se OWNER quiser, decidir se `.task_memory/` deve entrar no `.gitignore` ou virar memória oficial em `.claude/memory/`.
- O log do Discord mostrou uma resposta ruim do LLM: `opatá`. OWNER achou engraçado; não foi corrigido. Se repetir, filtrar/normalizar respostas inventadas curtas.
- Ainda existe branding `TOTK` em alguns scripts/README/logs. Não é função removida; só limpar se OWNER pedir trocar branding.
- No WhatsApp, envio direto para OWNER deve preferir JID `@lid` conhecido quando o bridge receber o contato assim.
