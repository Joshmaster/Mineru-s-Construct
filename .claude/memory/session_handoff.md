---
name: Handoff de sessao
description: Estado da ultima sessao - lido ao iniciar para retomar sem perda de contexto
type: project
---

## Feito nesta sessao (2026-05-15) — latência e bridge

### Fix de latência (llm.py)
- **Hard timeout via thread**: `_post()` agora usa `threading.Thread` + `t.join(timeout)` — urllib não enforçava timeout total em respostas lentas (OpenRouter chegou a 91s com `timeout=10` configurado).
- **`chat()` reordenado**: antes OpenRouter primeiro (30-91s). Agora: Cerebras 8b (~0.5s) → Mistral (~0.6s) → OpenRouter → Ollama.
- **`_call_quality` reordenado**: Mistral (~0.7s) → OpenRouter → Ollama.
- Tempos medidos: fast=0.3s, quality=0.7s, chat=0.5s no caso típico.

### Fix bridge — mensagens perdidas no restart (index.js)
- Raiz: mensagens enviadas durante restart chegam como `type="append"` (backfill Baileys) e o bridge ignorava.
- Fix: `type="append"` com `messageTimestamp` < 3min E reconexão < 30s são entregues ao webhook.
- `connectedAt` registra timestamp de cada `connection=open` para controlar a janela.

## Feito nesta sessao (2026-05-15) — refactor llm.py

### Refatoração completa de `link-bot/bot/core/llm.py`

**Dead code removido:**
- `_call_groq`, `GROQ_KEYS`, `GROQ_MODELS`, `GROQ_HEADERS` — nunca usados no fallback chain
- `_CLAUDE_Q` — variável declarada mas nunca usada

**Arquitetura DRY — `_call_openai_compat`:**
- Extraída função genérica que centraliza: circuit breaker, rotação de chaves, 2-pass (disponíveis → cooldown)
- `_call_openrouter`, `_call_cerebras`, `_call_mistral` agora são wrappers de 6 linhas
- Cerebras e Mistral ganharam 2-pass que antes só OpenRouter tinha

**`classify_skill_intent` atualizado:**
- Antes: `_call_openrouter` + `_call_ollama` diretamente
- Agora: Cerebras → OpenRouter → Ollama (beneficia do provider mais rápido)

**`_processar_tags` simplificado:**
- Loop sobre dict `{TAG: tipo}` elimina 4 blocos idênticos

**`_system_owner_block` extraído:**
- Bloco owner/user repetido em `chat()` e `chat_local()` virou função

**`choose_reaction_emoji`:**
- `_BLOCKED_REACTIONS` agora usa emojis literais (antes: unicode escapado como `🚫`)
- Comentário com unicode escapado corrigido

**Outras limpezas:**
- `import sys as _sys` movido para topo com outros imports
- Docstring do módulo atualizada com hierarquia atual
- Bloco de comentário de tiers atualizado (removia menção a Delirius)
- `chat_local` docstring corrigida ("sem OpenRouter/Groq" → "sem providers cloud")
- Dupla linha em branco antes de `_json_from_text` removida

**Latências confirmadas pós-refactor:**
- Cerebras llama3.1-8b: ~0.3-0.5s
- Mistral small: ~0.4s
- OpenRouter gpt-oss-20b: 5-11s (variável)

## Feito nesta sessao (2026-05-15) — continuação

### Roteamento natural de funcoes no WhatsApp
- `link-bot/bot/main.py`
  - Adicionado `_natural_match_skill()` para intents naturais deterministicas antes do classificador LLM.
  - Conversa natural agora tem prioridade sobre `!comando`.
  - `!comando` fica como fallback.
  - No grupo WhatsApp, OWNER pode acionar funcoes por frase natural sem `!`; outros usuarios ainda precisam mencionar o bot ou usar comando para evitar ruido.
  - `_ai_match_skill()` agora passa aliases/triggers das skills para o LLM e aceita retorno interno com `!comando` (ex: `!yt`, `!img`) como alias para resolver a skill.

### Musica/midia sem link obrigatorio
- `link-bot/bot/skills/delirius_dl.py`
  - YouTube agora aceita busca por texto, alem de link.
  - Pedidos como "toca lost woods via yutube" e "toca zelda lost woods no youtube" buscam no YouTube e baixam o audio.
  - `!yt` continua funcionando como fallback.
  - Limpeza de query remove aliases como `!yt`, `youtube`, `yutube`, `via youtube`.

### Musica contextual por reply
- `whatsapp-bridge/index.js`
  - Payload do webhook agora inclui `quotedText` e `quotedParticipant` quando a mensagem e resposta/citacao.
- `link-bot/bot/core/whatsapp_client.py`
  - `send_audio()` agora retorna ID da mensagem enviada.
- `link-bot/bot/core/context.py`
  - `MessageContext` carrega `quoted_msg_id`, `quoted_text` e callback para registrar contexto musical enviado.
- `link-bot/bot/main.py`
  - Guarda contexto de musicas enviadas pelo bot por ID de mensagem por ate 6h.
  - Se OWNER responde uma musica com "outra famosa", "mais uma", "da mesma banda", etc., o bot injeta `Contexto musical anterior:` no pedido.
  - No grupo, reply contextual de musica do OWNER tambem passa sem exigir `!`/mencao.
- `link-bot/bot/skills/delirius_dl.py` e `link-bot/bot/core/llm.py`
  - Busca Spotify usa o contexto anterior para escolher outra musica famosa da mesma banda/artista.
  - Se o LLM falhar, fallback usa artista do contexto (`Artist popular songs`, `Artist greatest hits`) em vez de buscar "outra famosa" aleatorio.

### Memoria persistente
- Criado `.claude/memory/feedback_natural_skill_routing.md`.
- Atualizados `.claude/memory/MEMORY.md` e `.claude/memory/project_hyrule.md`.
- Atualizados `AGENTS.md` e `CLAUDE.md` com a regra:
  - conversa natural tem prioridade;
  - `!comando` e fallback;
  - LLMs podem usar `!` internamente como alias.

## Estado atual dos servicos
- Hyrule Proxy: rodando
- Discord bot: online
- Supervisor: rodando
- WA Bridge: rodando na porta 7334
- WhatsApp bot: rodando (PID 232284)
- TRIFORCE/MAJORA/MASTERSWORD: rodando
- itch-monitor: rodando

### Validação e otimização LLM (segunda parte da sessão)

**Bugs corrigidos:**
- `_call_delirius_llm`: `/ia/chatgpt` retornava `data['data']` como string, código chamava `.get()` → AttributeError silencioso. Nunca funcionou em produção. Corrigido.
- Ordem Delirius invertida: gemini (~2.2s) primeiro, chatgpt (~3.4s) depois.
- `gpt-oss-120b` (32s) e modelos com 429 constante removidos de `OPENROUTER_MODELS`.

**Arquitetura de tiers (`llm.py`):**
- `_call_fast(timeout=5)`: classify, resolver_pendente, ia_escolher_args, extract_image_query
- `_call_quality(timeout=12)`: gerar_pergunta_skill, spotify_search_queries, rewrite_for_tts
- `choose_reaction_emoji`: Ollama only (era OpenRouter 5-17s bloqueando toda resposta)
- `chat()`: manual — OpenRouter → Delirius → Ollama compact (único lugar com Delirius)
- Delirius não entra nos helpers — não respeita system prompt, só serve pra conversa livre

**Latências medidas:**
- Ollama qwen3:8b: 0.5–2.5s local
- Delirius gemini: ~2.2s | chatgpt: ~3.4s
- OpenRouter gpt-oss-20b: 4–17s (variável, único modelo na lista)

**Bridge (index.js):**
- `documentMessage?.contextInfo` e `stickerMessage?.contextInfo` adicionados ao quoted
- `quotedTextFrom` cobre buttonsResponseMessage e listResponseMessage

## Adicionado em 2026-05-15 — Cerebras + Mistral

### Novos providers em `llm.py`
- **Cerebras** (3 chaves em `hyrule_env.py` como `CEREBRAS_KEYS`):
  - `_call_cerebras()` com User-Agent de browser (Cloudflare bloqueia urllib sem isso)
  - Modelo fast: `llama3.1-8b` (~0.29s)
  - Modelo quality: `llama3.3-70b`
  - Entra no topo do `_call_fast` → Cerebras → OpenRouter → Ollama
- **Mistral** (3 chaves em `hyrule_env.py` como `MISTRAL_KEYS`):
  - `_call_mistral()` com `mistral-small-latest`
  - Entra como fallback em `_call_quality` → OpenRouter → Mistral → Ollama
  - Entra como fallback em `chat()` → OpenRouter → Mistral → Ollama

### Nova hierarquia
- `_call_fast`: Cerebras (~0.3s) → OpenRouter → Ollama
- `_call_quality`: OpenRouter → Mistral → Ollama
- `chat()`: OpenRouter → Mistral → Ollama

## Pendente
- Testar no grupo frases naturais de mídia/funções

## Estado final da sessão — tudo funcionando em produção

## Cuidados
- Nao reverter as mudancas existentes em `llm.py`, `main.py`, `delirius_dl.py` que ja estavam modificadas antes desta sessao.
- Manter a regra nova como arquitetura: nao voltar a exigir `!` quando a intencao estiver clara.
