---
name: feedback-llm-performance
description: Ordem de providers por latência real — tiers, timeouts e por que OpenRouter é último recurso
metadata:
  type: feedback
---

## Regra principal

OpenRouter é lento e imprevisível (10–91s em produção). Cerebras e Mistral são os providers primários.
Não reverter essa ordem.

**Why:** `_post()` com urllib não enforça timeout total — respostas lentas bloqueiam mesmo com `timeout=N`.
Fix aplicado: `_post()` usa `threading.Thread` + `t.join(timeout)` para hard timeout real.

## Latências medidas (2026-05-15)

| Provider | Tempo | Observação |
|---|---|---|
| Cerebras llama3.1-8b | ~0.3–0.5s | requer User-Agent de browser (Cloudflare bloqueia urllib) |
| Mistral small | ~0.5–1s | sem headers especiais |
| Ollama qwen3:8b | 0.5–2.5s | local, depende da carga CPU |
| OpenRouter gpt-oss-20b:free | 10–91s | imprevisível; grátis |

## Ordem por tier (em produção, validada)

| Tier | Cadeia | Motivo |
|---|---|---|
| `_call_fast` | Cerebras 8b → OpenRouter → Ollama | sub-segundo para JSON/classify |
| `_call_quality` | Mistral → OpenRouter → Ollama | ~0.7s para Spotify/TTS |
| `chat()` | Cerebras 8b → Mistral → OpenRouter → Ollama | Cerebras responde conversa casual bem |
| `choose_reaction_emoji` | Ollama only | latência cloud não justifica para reação |

## Comportamento de Ollama

- Sempre `think=False` — `think=True` dobra tokens gerados, causa timeout no CPU
- Persona compacta (2–3 linhas), nunca LINK_PERSONA.md completo
- Histórico limitado a últimas 4 mensagens
- `num_predict`: 80–100 para conversa, 60 para JSON/classify
- Timeouts: classify=15–20s, chat=60s, emoji=4s

## Circuit breaker (cloud)

- 3 falhas consecutivas → provider bloqueado por 180s
- 429 → chave entra em cooldown de 60s; segunda passagem tenta chaves em cooldown como último recurso
- 401/403 → `_AUTH_ERROR` sentinel; `break` no loop de modelos dessa chave

## Funções por tier

| Função | Tier |
|---|---|
| `choose_reaction_emoji` | Ollama only |
| `classify_skill_intent` | Cerebras → OpenRouter → Ollama |
| `resolver_pendente` | `_call_fast` |
| `ia_escolher_args` | `_call_fast` |
| `extract_image_query` | `_call_fast` |
| `gerar_pergunta_skill` | `_call_quality` |
| `spotify_search_queries` | `_call_quality` |
| `rewrite_for_tts` | `_call_quality` |
| `chat()` | manual: Cerebras → Mistral → OpenRouter → Ollama |

**Regra:** nova função LLM → usar `_call_fast` ou `_call_quality`. Nunca `_call_openrouter` direto sem fallback.
