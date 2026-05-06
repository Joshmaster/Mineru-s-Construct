---
name: Modelos Ollama — sessão 2026-04-12
description: Decisões sobre modelos locais Ollama para o Hyrule — o que foi testado, removido e configurado
type: project
---

## Fato
Em 2026-05-06, o modelo ativo no servidor e em `bot_supervisor.py` é **qwen2.5:7b** (~4.7GB) como executor primário das tools.

**Why:** a instalação atual tem `qwen2.5:7b` baixado no Ollama e o supervisor foi ajustado para ele. Ele aguenta melhor tool calling com o filtro atual de tools.

**How to apply:** Quando OWNER mencionar modelos Ollama, o atual do supervisor é `qwen2.5:7b`. Se quiser voltar ao modo leve, trocar `OLLAMA_MODEL` e baixar `qwen2.5:1.5b`.

## Modelos removidos
- `glm-4.7-flash:latest` (19GB) — não cabe em 16GB RAM
- `qwen3-fast:latest`, `qwen3:4b`, `qwen2.5:3b` — removidos
- `qwen3:14b`, `qwen2.5-coder:14b` — descartados
- `granite3.2:2b` — removido (tool calling inconsistente)
- `kimi-k2.5:cloud` — removido dos scripts (OLLAMA_CLOUD = None)

## Modelo atual
`qwen2.5:7b` — ~4.7GB, tool calling via Ollama API
- Limitação: ainda precisa de filtro de tools por intent
- Solução: `_selecionar_tools()` filtra por relevância do pedido
- Single-tool calls: muito confiáveis (4/4 testes passam)
- Multi-step: usa `executar_pedido()` Python puro para padrões conhecidos

## Arquivos atualizados
- `bot_supervisor.py`: OLLAMA_MODEL = "qwen2.5:7b"

## Suporte oficial Claude Code + Ollama
Ollama v0.14+ expõe API compatível com Anthropic em localhost:11434.
Env vars configuradas no startup_services.py:
- ANTHROPIC_BASE_URL=http://localhost:11434
- ANTHROPIC_AUTH_TOKEN=ollama
- ANTHROPIC_API_KEY=ollama
