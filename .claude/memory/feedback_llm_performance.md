---
name: feedback-llm-performance
description: LLM local Ollama — configurações de performance para respostas rápidas
metadata:
  type: feedback
---

Ao usar Ollama (qwen3:8b) como fallback, usar sempre `think=False` e persona compacta.

**Por que:** `think=True` dobra o tempo de geração (gera tokens de raciocínio antes da resposta). Prompt enorme (persona 8KB + histórico 20 msgs) causa timeout no CPU. Testes mostraram: `think=True` = 90s+, `think=False` com prompt compacto = 3-5s.

**Como aplicar:**
- `think=False` sempre para fallback Ollama em conversa
- Persona compacta para Ollama: 2-3 linhas, nunca o LINK_PERSONA.md completo
- Histórico limitado a 4 mensagens para Ollama (não 20)
- `num_predict`: 80-100 tokens para conversa, 60 para classify/JSON
- Timeouts Ollama: classify=25s, chat=60s, emoji=5s
- Circuit breaker: após 3 falhas 401, bloqueia cloud provider por 180s
- 401 em provider: `break` no loop de modelos (não tenta os outros modelos da mesma chave)
- `_AUTH_ERROR` sentinel em `_post()` distingue 401 de timeout

**Resultado atual (sem cloud):** Discord ~4s/msg, WhatsApp ~28s/msg (2 Ollamas: classify + chat)
