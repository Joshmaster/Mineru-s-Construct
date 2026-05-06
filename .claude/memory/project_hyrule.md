---
name: Projeto Hyrule
description: Contexto completo do ecossistema de agentes — bot Discord Link, supervisor, watcher, proxy e integração com Claude Code
type: project
originSessionId: ac218d08-6f60-4d2f-b426-1188d53f3b27
---
## Arquitetura geral

Todos os agentes ficam em `C:/Users/OWNER/Agents/`.

### Bot Discord — Link (`DISCORD/link_discord.py`)
- Responde OWNER (`DISCORD_OWNER_USERNAME`) e USER2 (`DISCORD_USER2_USERNAME`) via DM no Discord
- Usa LLMs free tier (OpenRouter + Groq) com fallback entre modelos
- Persona carregada de `OPENCODE/roaming/LINK_PERSONA.md`
- Quando OWNER pede algo do PC, gera tag `[SHEIKAH_SLATE: descrição]`
- `sanitizar()` centralizado remove a tag antes de enviar ao usuário
- Comando especial `!Link acorde` → limpa tudo e reinicia (sem precisar da TRIFORCE)
- Parâmetros API: `temperature=0.85`, `frequency_penalty=0.7`, `presence_penalty=0.4`
- Histórico: últimas 10 trocas (20 entradas) por usuário
- **Groq requer headers especiais** — sem eles retorna 403/1010 Cloudflare

### Supervisor (`bot_supervisor.py`)
- Daemon permanente que monitora `DISCORD/discord.log` em tempo real
- **Watchdog embutido**: verifica o bot a cada 30s e reinicia automaticamente se cair
- **Fluxo de resolução (ordem de prioridade):**
  1. `executar_pedido()` — Python puro, zero tokens (padrões hardcoded + navegação de pastas)
  2. `executar_qwen_react()` — qwen2.5:7b ReAct loop (até 5 rodadas, tools filtradas)
  3. `chamar_agente_tools()` — OpenRouter (gpt-oss-20b → gpt-oss-120b → nemotron → trinity → llama → gemma)
  4. `chamar_groq_tools()` — Groq 0.3s
  5. `enfileirar_para_claude()` — TRIFORCE como último recurso
- **Tool filtering:** `_selecionar_tools()` filtra por intent (8 categorias), max 3 tools para o qwen
- **Deduplicação:** `pedidos_vistos` dict com chave `timestamp|pedido`, TTL 10 min — evita reprocessar mesmo evento, permite retry após TTL
- **TRIFORCE-PEDIDO:** também tem dedup por timestamp

### Navegação de pastas (embutida no `executar_pedido`)
- Estado `_pasta_atual: dict[str, Path]` por usuário (reseta no restart para Desktop)
- Detecta nomes reais de pastas/arquivos no texto (não depende de conjugação verbal)
- Atalhos: Desktop (OneDrive primeiro, depois local), Downloads, Documentos, Imagens, OneDrive
- Bloqueado: Windows, System32, SysWOW64 — resto liberado (inclusive Program Files)
- "me manda X" sem caminho absoluto → busca na pasta atual
- Listagem: top 30 por nome, emojis por tipo de arquivo

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
- Lê `~/.claude/.credentials.json` e alerta OWNER quando o token OAuth resta menos de 120 min

### MAJORA watcher (`watch_codex_queue.py`)
- Polling a cada 2s em `codex_queue.json`
- Usa `codex exec` para pedidos MAJORA
- Responde no canal do item: Discord (`localhost:7331`) ou WhatsApp (`localhost:7332`)
- Usa `.majora_processing.lock` para evitar processamento paralelo/recursivo
- Lock é considerado stale após 15 min ou se o PID morreu

### MASTERSWORD watcher (`watch_mastersword_queue.py`)
- Polling a cada 2s em `mastersword_queue.json`
- Usa `opencode run` para pedidos MASTERSWORD
- Instalação: `npm i -g opencode-ai` (binário `opencode`, versão validada 1.14.39)
- Config Linux ativa: `~/.config/opencode/opencode.json`
- Config versionada: `OPENCODE/mastersword.opencode.json`
- Modelos padrão: OpenRouter free → Groq free → Ollama local (`qwen2.5:7b`)
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

### OpenRouter (ordem no supervisor)
1. `openai/gpt-oss-20b:free`
2. `openai/gpt-oss-120b:free`
3. `nvidia/nemotron-3-super-120b-a12b:free`
4. `arcee-ai/trinity-large-preview:free`
5. `meta-llama/llama-3.3-70b-instruct:free`
6. `google/gemma-4-31b-it:free`

### Groq (fallback, 0.3s)
1. `llama-3.3-70b-versatile`
2. `moonshotai/kimi-k2-instruct`
3. `openai/gpt-oss-20b`
4. `llama-3.1-8b-instant`
- Headers obrigatórios para não ser bloqueado pelo Cloudflare

### Ollama local
- `qwen2.5:7b` — executor principal de tools no supervisor
- Tool filtering: max 3 tools por pedido (`_selecionar_tools()`)

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

## Navegação de pastas — arquitetura (2026-04-16)
- `_salvar_nav_state(usuario, pasta)` salva `{"pasta": str, "itens": [nomes reais]}` em `nav_state.json`
- `_carregar_nav_state(autor)` em link_discord.py injeta pasta + itens no prompt do LLM
- Regra injetada: "use o nome EXATAMENTE como listado, sem traduzir ou corrigir ortografia"
- Fuzzy match (difflib ratio ≥ 0.8) permanece como rede de segurança no supervisor
