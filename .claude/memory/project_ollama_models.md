---
name: Modelos Ollama — sessão 2026-04-12
description: Decisões sobre modelos locais Ollama para o Hyrule — o que foi testado, removido e configurado
type: project
---

## Fato
Em 2026-05-07, o modelo ativo no servidor e em `bot_supervisor.py` é **qwen3.5:9b** (~6.6GB no disco, 9.7B Q4_K_M) como executor primário das tools.

**Why:** `qwen3.5:9b` tem capacidade `tools` nativa no Ollama e conseguiu chamar tool em teste direto e no fluxo ReAct do supervisor com todas as 17 tools disponíveis.

**How to apply:** Quando OWNER mencionar modelos Ollama, o atual do supervisor é `qwen3.5:9b`. O qwen2.5 foi removido. Para voltar ao modo leve, baixar outro modelo e trocar `OLLAMA_MODEL`.

## Modelos removidos
- `glm-4.7-flash:latest` (19GB) — não cabe em 16GB RAM
- `qwen2.5:7b` — removido em 2026-05-07 ao migrar para qwen3.5:9b
- `qwen3-fast:latest`, `qwen3:4b`, `qwen2.5:3b` — removidos
- `qwen3:14b`, `qwen2.5-coder:14b` — descartados
- `granite3.2:2b` — removido (tool calling inconsistente)
- `kimi-k2.5:cloud` — removido dos scripts (OLLAMA_CLOUD = None)

## Modelo atual
`qwen3.5:9b` — ~6.6GB, 9.7B Q4_K_M, tool calling via Ollama API
- Capabilities do Ollama: `completion`, `vision`, `tools`, `thinking`
- Supervisor envia `think=False` e `temperature=0.3` para tool calling mais direto
- `_selecionar_tools()` retorna todas as 17 tools com `OLLAMA_ALL_TOOLS=True`
- Teste direto: chamada de tool `get_time` retornou `tool_calls`
- Teste supervisor: `executar_qwen_react("qual a data e hora do pc?")` chamou `executar_comando` e respondeu corretamente
- Timeout local do Ollama aumentado para 180s por causa do primeiro carregamento do 9B

## Arquivos atualizados
- `bot_supervisor.py`: `OLLAMA_MODEL = "qwen3.5:9b"`, `OLLAMA_ALL_TOOLS=True`
- `/swap.img`: ampliado para 10G e mantido em `/etc/fstab`

## Suporte oficial Claude Code + Ollama
Ollama v0.14+ expõe API compatível com Anthropic em localhost:11434.
Env vars configuradas no startup_services.py:
- ANTHROPIC_BASE_URL=http://localhost:11434
- ANTHROPIC_AUTH_TOKEN=ollama
- ANTHROPIC_API_KEY=ollama
