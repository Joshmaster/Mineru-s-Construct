---
name: Modelos Ollama — sessão 2026-04-12
description: Decisões sobre modelos locais Ollama para o Hyrule — o que foi testado, removido e configurado
type: project
---

## Fato
Em 2026-05-07, o modelo ativo no servidor e em `bot_supervisor.py` é **qwen3:8b** (~5.2GB no disco, 8.2B Q4_K_M) como executor primário das tools.

**Why:** `qwen3:8b` tem capacidade `tools` e `thinking` nativa no Ollama, é menor que `qwen3.5:9b`, e conseguiu chamar tool no fluxo ReAct do supervisor com todas as 17 tools disponíveis.

**How to apply:** Quando OWNER mencionar modelos Ollama, o atual do supervisor, Discord `!z/!zpensa` e WhatsApp `!z/!zpensa` é `qwen3:8b`. O qwen2.5 foi removido. Para trocar, baixar outro modelo e atualizar `OLLAMA_MODEL`.

## Modelos removidos
- `glm-4.7-flash:latest` (19GB) — não cabe em 16GB RAM
- `qwen2.5:7b` — removido em 2026-05-07
- `qwen3.5:9b` — substituído em 2026-05-07 por `qwen3:8b` por estar pesado no uso local
- `qwen3-fast:latest`, `qwen3:4b`, `qwen2.5:3b` — removidos
- `qwen3:14b`, `qwen2.5-coder:14b` — descartados
- `granite3.2:2b` — removido (tool calling inconsistente)
- `kimi-k2.5:cloud` — removido dos scripts (OLLAMA_CLOUD = None)

## Modelo atual
`qwen3:8b` — ~5.2GB, 8.2B Q4_K_M, tool calling via Ollama API
- Capabilities do Ollama: `completion`, `tools`, `thinking`
- Supervisor envia `think=False` e `temperature=0.3` para tool calling mais direto
- `_selecionar_tools()` retorna todas as 17 tools com `OLLAMA_ALL_TOOLS=True`
- Teste direto do core WhatsApp: `chat_local(..., think=False)` respondeu em 8.1s; `chat_local(..., think=True)` respondeu em 12.2s.
- Teste supervisor: `executar_qwen_react("qual a data e hora do pc?")` chamou `executar_comando` com bash e respondeu corretamente em uma rodada.
- `!zpensa` agora usa tools: busca web direta por `buscar_internet()`, imagem por `buscar_imagem()`/download/envio, e ReAct filtrado por intent para outros comandos.
- Teste apos tools no `!zpensa`: busca web direta respondeu em ~0.2s; ReAct filtrado de data/hora chamou apenas `executar_comando` e respondeu em 34.2s.
- Timeout local do Ollama continua alto para cobrir primeiro carregamento e ReAct com tools.

## Arquivos atualizados
- `bot_supervisor.py`: `OLLAMA_MODEL = "qwen3:8b"`, `OLLAMA_ALL_TOOLS=True`
- `DISCORD/link_discord.py`: `OLLAMA_MODEL = "qwen3:8b"`
- `link-bot/bot/core/llm.py`: `OLLAMA_MODEL = "qwen3:8b"`
- `/swap.img`: ampliado para 10G e mantido em `/etc/fstab`

## Suporte oficial Claude Code + Ollama
Ollama v0.14+ expõe API compatível com Anthropic em localhost:11434.
Env vars configuradas no startup_services.py:
- ANTHROPIC_BASE_URL=http://localhost:11434
- ANTHROPIC_AUTH_TOKEN=ollama
- ANTHROPIC_API_KEY=ollama
