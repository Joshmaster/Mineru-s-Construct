---
name: Projeto Hyrule
description: Contexto completo do ecossistema de agentes — bot Discord Link, supervisor, watcher, proxy e integração com Claude Code
type: project
originSessionId: ac218d08-6f60-4d2f-b426-1188d53f3b27
---
## Arquitetura geral

Todos os agentes ficam em `~/Agents/`.

### Bot Discord — Link (`DISCORD/link_discord.py`)
- Responde OWNER (`DISCORD_OWNER_USERNAME`) e USER2 (`DISCORD_USER_2`) via DM no Discord
- Usa a cadeia atual de LLMs do Hyrule: Cerebras/Mistral/OpenRouter/Ollama, sem Groq
- Persona carregada de `OPENCODE/roaming/LINK_PERSONA.md`
- Quando OWNER pede algo do PC, gera tag `[SHEIKAH_SLATE: descrição]`
- `sanitizar()` centralizado remove a tag antes de enviar ao usuário
- Comando especial `!Link acorde` → limpa tudo e reinicia (sem precisar da TRIFORCE)
- Parâmetros API: `temperature=0.85`, `frequency_penalty=0.7`, `presence_penalty=0.4`
- Histórico: últimas 10 trocas (20 entradas) por usuário

### Supervisor (`bot_supervisor.py`)
- Daemon permanente que monitora `DISCORD/discord.log` em tempo real
- **Watchdog embutido**: verifica o bot a cada 30s e reinicia automaticamente se cair
- **Fluxo de resolução (ordem de prioridade):**
  1. `executar_pedido()` — Python puro, zero tokens (padrões hardcoded + navegação de pastas)
  2. `executar_qwen_react()` — qwen3:8b ReAct loop (até 5 rodadas, todas as tools)
  3. Cloud configurado (Cerebras/Mistral/OpenRouter no link-bot; OpenRouter legacy no supervisor quando necessário)
  4. `enfileirar_para_claude()` — TRIFORCE como último recurso
- **Qwen tools:** `_selecionar_tools()` retorna todas as tools quando `OLLAMA_ALL_TOOLS=True` (qwen3:8b)
- **`!zpensa` com tools:** Discord usa `responder_com_ia_local_tools()`; WhatsApp usa `chat_local_tools()` e atalho proprio para imagem. Busca web simples chama `buscar_internet()` direto; imagens/URLs de arquivo no Discord sempre passam por `/download` + `/send-file`, nao por link; ReAct de `!zpensa` usa tools filtradas por intent (`usar_todas_tools=False`, max 3 rodadas) para reduzir latencia.
- **Deduplicação:** `pedidos_vistos` dict com chave `timestamp|pedido`, TTL 10 min — evita reprocessar mesmo evento, permite retry após TTL
- **TRIFORCE-PEDIDO:** também tem dedup por timestamp

### Navegação de pastas (embutida no `executar_pedido`)
- Estado `_pasta_atual: dict[str, Path]` por usuário (reseta no restart para Desktop)
- Detecta nomes reais de pastas/arquivos no texto (não depende de conjugação verbal)
- Atalhos: Desktop (OneDrive primeiro, depois local), Downloads, Documentos, Imagens, OneDrive
- Bloqueado: Windows, System32, SysWOW64 — resto liberado (inclusive Program Files)
- "me manda X" sem caminho absoluto → busca na pasta atual
- Listagem: top 30 por nome, emojis por tipo de arquivo

### Retenção de mídias temporárias
- WhatsApp inbox (`~/.linkbot/inbox`) e mídias geradas pelo sistema (`~/Agents/.linkbot/reminder_cards`) ficam disponíveis por até 24h
- `link-bot/bot/main.py` limpa arquivos expirados ao conectar e depois a cada 1h
- Baú (`~/.linkbot/bau`) é armazenamento manual; só limpa quando OWNER pedir

### Roteamento natural de skills
- Regra permanente: conversa natural tem prioridade sobre `!comando`.
- `!comando` permanece como fallback e alias interno para LLMs; o usuário não deve precisar digitar `!` quando a intenção está clara.
- Ordem esperada: frase natural clara → detecção determinística local → classificador LLM → `!comando` fallback → chat normal.
- No grupo WhatsApp, OWNER pode acionar funções por frase natural sem `!`; outros usuários continuam precisando mencionar o bot ou usar comando para evitar ruído.
- Música/mídia: YouTube e Spotify aceitam busca por texto; link é opcional quando a skill consegue resolver por busca.

### Mídia local via yt-dlp
- `link-bot/bot/skills/delirius_dl.py` usa `yt-dlp` local como caminho primário para YouTube MP3/MP4.
- Busca de música/Spotify por texto usa busca local do YouTube via `yt-dlp`; Delirius não é fallback de música.
- Link Spotify resolve título por `open.spotify.com/oembed` e baixa a faixa equivalente pelo YouTube local.
- Discord (`DISCORD/link_discord.py`) também usa os helpers locais para `!spot`/`!yt`, sem chamar `spotifydl`/`ytmp3`.
- Instagram e Twitter/X tentam `yt-dlp` local primeiro; Delirius fica como fallback real para casos de login/bloqueio local.

### Comando `!Link acorde`
- Detectado diretamente em `link_discord.py` (sem passar pelo LLM)
- Supervisor executa: clear-history + delete msgs (OWNER + USER2) + reinicia bot
- Bot responde "acordando tudo... um segundo" imediatamente

### Hierarquia de uso
- **Link** — conversa e pedidos simples do PC
- **Supervisor + qwen** — execução de tools
- **`!Link acorde`** — reset geral sem depender de ninguém
- **TRIFORCE** — só para coisas complexas (debug, edição de código, análise)

### TRIFORCE daemon (`triforce_daemon.py`)
- Polling a cada 2s em `claude_queue.json`
- Usa `claude --print --continue --dangerously-skip-permissions --no-session-persistence --output-format json`
- Responde no canal do item: Discord (`localhost:7331`) ou WhatsApp (`localhost:7332`)
- Não usa fallback LLM para mascarar erro do Claude; falha aparece explicitamente
- Nao envia mais alerta preventivo de token/OAuth do Claude; falhas da TRIFORCE aparecem quando a fila tenta executar.

### MAJORA watcher (`watch_codex_queue.py`)
- Polling a cada 2s em `codex_queue.json`
- Usa `codex exec` para pedidos MAJORA
- Codex CLI instalado via npm global: `@openai/codex` / `codex-cli 0.130.0` (validado em 2026-05-13)
- Responde no canal do item: Discord (`localhost:7331`) ou WhatsApp (`localhost:7332`)
- Usa `.majora_processing.lock` para evitar processamento paralelo/recursivo
- Lock é considerado stale após 15 min ou se o PID morreu

### MASTERSWORD watcher (`watch_mastersword_queue.py`)
- Polling a cada 2s em `mastersword_queue.json`
- Usa `opencode run` para pedidos MASTERSWORD
- Instalação: `npm i -g opencode-ai` (binário `opencode`, versão validada 1.14.39)
- Config Linux ativa: `~/.config/opencode/opencode.json`
- Config versionada: `OPENCODE/mastersword.opencode.json`
- Persona/config: `OPENCODE/roaming/MASTERSWORD_INSTRUCTIONS.md` + `OPENCODE/roaming/LINK_PERSONA.md`
- Retomada: `opencode link` e `mastersword link` seguem a mesma rotina de `link link`/`codex link`
- Modelos padrão: OpenRouter free → Ollama local (`qwen3:8b`); Groq não faz parte da cadeia atual
- Responde no canal do item: Discord (`localhost:7331`) ou WhatsApp (`localhost:7332`)
- Usa `.mastersword_processing.lock`; stale após 15 min ou se o PID morreu

### Watcher interativo (`watch_discord_queue.py`)
- Polling a cada 1s em `claude_queue.json`
- exit code 2 → acorda Claude Code (TRIFORCE)
- 5 slots paralelos via asyncRewake nos hooks do Claude Code
- Respeita `canal`; WhatsApp responde via `localhost:7332`

### Proxy Hyrule (`CLAUDE CODE/proxy.py`) — porta 8765

### Claude Code CLI
- Instalado via npm global no nvm, sem `sudo npm -g`
- Binário atual: `~/.nvm/versions/node/v22.22.2/bin/claude`
- Auto-update validado em 2026-05-06: enabled, permissões OK, canal latest

## Modelos LLMs

### Cadeia atual do link-bot
- `_call_fast`: Cerebras `llama3.1-8b` → OpenRouter `openai/gpt-oss-20b:free` → Ollama `qwen3:8b`
- `_call_quality`: Mistral `mistral-small-latest` → OpenRouter `openai/gpt-oss-20b:free` → Ollama `qwen3:8b`
- `chat()`: Cerebras `llama3.1-8b` → Mistral `mistral-small-latest` → OpenRouter `openai/gpt-oss-20b:free` → Ollama compact
- `choose_reaction_emoji`: Ollama only
- `check_llms.py` valida Cerebras, Mistral, OpenRouter e Ollama. Groq não é checado.

### Ollama local
- `qwen3:8b` — executor principal de tools no supervisor
- `qwen2.5:7b` removido
- `OLLAMA_ALL_TOOLS=True`: qwen recebe o conjunto completo de 17 tools
- Swap local ampliado para `/swap.img` 10G para dar margem ao modelo

## HTTP API do bot (porta 7331)
- `POST /send` — envia mensagem
- `POST /send-file` — envia arquivo (campo: `file`, não `path`)
- `POST /download` — baixa arquivo de URL
- `POST /delete` — apaga mensagens (`{to, count}`)
- `POST /edit` — edita mensagem própria do bot
- `POST /react` — adiciona reação emoji
- `POST /pin` — fixa mensagem
- `POST /clear-history` — limpa histórico em memória e disco
- `GET /history` — histórico de mensagens
- `GET /status` — status do bot

## Scripts de checagem
- `startup_services.py restart` — para tudo, limpa memória, apaga msgs Discord, reinicia
- `startup_services.py start` — inicia só o que estiver parado
- `check_llms.py` — valida daemons e lê chaves de `hyrule_env.py`
- `check_discord_logs.py` — lê conversas recentes
- `check_claude_queue.py` — lê e limpa fila

## Serviços gerenciados por `startup_services.py`
- Hyrule Proxy (`CLAUDE CODE/proxy.py --serve`) — porta 8765
- Discord bot (`DISCORD/link_discord.py`) — porta 7331
- Supervisor (`bot_supervisor.py`)
- WhatsApp bot (`python3 -m bot.main`) — porta 7332
- TRIFORCE daemon (`triforce_daemon.py`)
- MAJORA watcher (`watch_codex_queue.py`)
- MASTERSWORD watcher (`watch_mastersword_queue.py`)

## Arquivos de segurança
- `hyrule_env.py` fica fora do git
- `.claude/.credentials.json` fica fora do git
- `CLAUDE CODE/HYRULE.md` e `CLAUDE CODE/global/HYRULE.md` usam placeholders `${OPENROUTER_KEY}` / `${GROQ_KEY}` na versão versionada

## Hooks (Claude Code settings.json)
```
SessionStart: startup_services.py → check_llms.py → check_discord_logs.py → watch_discord_queue.py (slots 0-4, asyncRewake)
UserPromptSubmit: check_claude_queue.py
PermissionRequest: allow all
```

## Mudanças sessão 2026-04-17 — busca de imagens

### Nova tool `buscar_imagem(termo, wiki='zelda')` em `bot_supervisor.py`
Fluxo de 3 níveis testado e validado:
1. **Hyrule Compendium** `botw-compendium.herokuapp.com/api/v3/compendium/entry/{slug}` → `data.image` → funciona para itens BOTW/TOTK (master_sword, hylian_shield)
2. **Fandom pageimages** `zelda.fandom.com/api.php?...&prop=pageimages&piprop=original` → `original.source` → imagem principal full-size da página (ganondorf, etc.)
3. **Fandom allimages** prefix fallback → filtra icon/sprite/map
4. **Wikimedia Commons** `generator=search&gsrsearch={termo}&gsrnamespace=6` → último recurso genérico

### `executar_pedido` — correções
- Removido `"buscar"` do bloco "ler arquivo" (causava "Arquivo não encontrado" para "buscar na web X")
- Adicionado bloco de busca de imagem direto (sem LLM): detecta `(busca+web) AND (imagem+foto+png)` → chama `buscar_imagem` → `/download` → `/send-file`

### `_selecionar_tools` — atualização
- Novo intent `_busca_img`: se pedido tem (busca/web) AND (imagem/foto/png) → tools = `{buscar_imagem, baixar_e_enviar}` (dentro do limite de 3 do qwen)

### Bugs de encoding corrigidos (sessão de hoje)
- `—` (travessão) quebra encoding no `/send` → usar `-` normal
- `/send-file` usa JSON `{"file": "C:/path/..."}` com `/` (não `\`)

## Bugs corrigidos nesta sessão (2026-04-16)
- `executar_pedido` estava retornando None (desativado) — reativado com `usuario` como parâmetro
- `/send-file` usava campo `path` em vez de `file` — corrigido em 3 lugares
- `_selecionar_tools` retornava todas as 16 tools — agora filtra por intent (max 3)
- `pedidos_vistos` era set de texto puro — virou dict com timestamp+TTL, chave `ts|pedido`
- `startup_services restart` apagava msgs antes do bot subir — deleção movida para depois do bot online
- Mensagem do bot dizia "chamando o Claude" — corrigido para "chamando a triforce"
- `BASE_DIR` é string em link_discord.py — _NAV_STATE_FILE agora usa `Path(BASE_DIR) / ...`
- LLM gerava drive letter errado (A:\, D:\ em vez de C:\) — _tentar_caminho() corrige automaticamente
- LLM "traduzia" nomes de pastas (pyton → Python) — solução global: nav_state salva conteúdo real da pasta, bot injeta no prompt com regra CRITICA de usar nomes exatos

## Mudanças sessão 2026-05-17 — card de rotina de remédios

- `link-bot/bot/core/reminder_art.py` agora tem `render_medication_schedule_card(reminders)`, um card PNG estilo Star Wars/Hora do Remédio para listar a rotina completa do dia.
- O card usa lembretes recorrentes ativos do SQLite, ordena por horário (`recurrence daily HH:MM` ou `trigger_at`) e renderiza remédios/doses por bloco.
- `link-bot/bot/skills/lembrete.py` tem a skill `remedios_card`.
- Gatilhos aceitos: `!remedios`, `card dos remedios`, `horarios dos remedios`, `horarios do remedio`, `rotina de remedios`, `todos os remedios`.
- A skill envia imagem com legenda curta `Rotina de remedios`; OWNER pediu card/imagem sem textão.
- `zelda_milkshake_reminder.py` removido: era one-shot de 17/05/2026 14:00, ja disparado e desativado.
- Watchers MAJORA/MASTERSWORD agora preservam item de fila quando lock esta ativo, evitando perda de pedido em corrida.

## Mudanças sessão 2026-05-17 — roteamento natural enxuto

- `link-bot/bot/main.py` tem `DISABLED_SKILL_MODULES` para nao carregar skills nunca usadas:
  - `aleatorio`, `calc`, `cep`, `clima`, `conversao`, `cotacao`, `encurtar`, `hora`, `noticias`, `qr`.
  - Isso remove dado/moeda/sorteio/senha, calculo, CEP, clima, conversao, cotacao, URL curta, hora, noticias e QR como skills.
  - Perguntas desses temas caem no chat normal/LLM.
- Roteamento natural prioriza:
  - imagem/foto -> `imagem_buscar`
  - criar/desenhar imagem -> `img_gerar`
  - tocar/baixar musica/video -> `delirius_dl`
  - GIF -> `delirius_gif`
  - voz/TTS -> `delirius_fala`
  - figurinha com texto -> `delirius_tt`
  - melhorar/upscale imagem -> `delirius_melhora`
  - mandar midia para Discord -> `discord_forward`
  - agents naturais -> `triforce_cmd`, `majora_cmd`, `mastersword_cmd`
- Classificador LLM (`link-bot/bot/core/llm.py`) ganhou regras e exemplos para evitar confundir imagem com musica/download.
- Busca de imagem (`bot_supervisor.py`) ganhou fallback `zeldawiki.wiki` para artes oficiais, especialmente `Link Master Sword`.

## Navegação de pastas — arquitetura (2026-04-16)
- `_salvar_nav_state(usuario, pasta)` salva `{"pasta": str, "itens": [nomes reais]}` em `nav_state.json`
- `_carregar_nav_state(autor)` em link_discord.py injeta pasta + itens no prompt do LLM
- Regra injetada: "use o nome EXATAMENTE como listado, sem traduzir ou corrigir ortografia"
- Fuzzy match (difflib ratio ≥ 0.8) permanece como rede de segurança no supervisor
