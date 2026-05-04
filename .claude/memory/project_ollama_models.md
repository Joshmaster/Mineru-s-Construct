---
name: Modelos Ollama — sessão 2026-04-12
description: Decisões sobre modelos locais Ollama para o Hyrule — o que foi testado, removido e configurado
type: project
---

## Fato
Em 2026-04-14, modelo trocado para **qwen2.5:1.5b** (~1GB RAM) como executor primário das tools.

**Why:** granite3.2:2b tinha tool calling inconsistente (10+ formatos JSON diferentes). qwen2.5:1.5b usa API Ollama padrão e chama tools corretamente quando dado 1-2 tools relevantes.

**How to apply:** Quando OWNER mencionar modelos Ollama, o atual é qwen2.5:1.5b em TODOS os scripts.

## Modelos removidos
- `glm-4.7-flash:latest` (19GB) — não cabe em 16GB RAM
- `qwen3-fast:latest`, `qwen3:4b`, `qwen2.5:3b` — removidos
- `qwen3:14b`, `qwen2.5-coder:14b` — descartados
- `granite3.2:2b` — removido (tool calling inconsistente)
- `kimi-k2.5:cloud` — removido dos scripts (OLLAMA_CLOUD = None)

## Modelo atual
`qwen2.5:1.5b` — ~1GB RAM, tool calling nativo via Ollama API
- Limitação: max 2-3 tools por vez (15 tools confundem o modelo)
- Solução: `_selecionar_tools()` filtra por relevância do pedido
- Single-tool calls: muito confiáveis (4/4 testes passam)
- Multi-step: usa `executar_pedido()` Python puro para padrões conhecidos

## Arquivos atualizados
- `bot_supervisor.py`: OLLAMA_MODEL = "qwen2.5:1.5b"
- `ollama_fallback.py`: OLLAMA_MODEL = "qwen2.5:1.5b"
- `proxy.py`: default model = "qwen2.5:1.5b"

## Suporte oficial Claude Code + Ollama
Ollama v0.14+ expõe API compatível com Anthropic em localhost:11434.
Env vars configuradas no startup_services.py:
- ANTHROPIC_BASE_URL=http://localhost:11434
- ANTHROPIC_AUTH_TOKEN=ollama
- ANTHROPIC_API_KEY=ollama
