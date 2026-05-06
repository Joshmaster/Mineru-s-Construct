---
name: TRIFORCE, MAJORA e MASTERSWORD
description: TRIFORCE aciona Claude Code, MAJORA aciona Codex CLI, MASTERSWORD aciona OpenCode — todos canal-aware (discord/whatsapp)
type: feedback
---

## Regra
- `[TRIFORCE: task]` → escreve em `claude_queue.json` → `watch_discord_queue.py` acorda Claude Code
- `[MAJORA: task]` → escreve em `codex_queue.json` → `watch_codex_queue.py` spawna Codex CLI
- `[MASTERSWORD: task]` → escreve em `mastersword_queue.json` → `watch_mastersword_queue.py` spawna OpenCode

## Canal awareness
Ao acordar via TRIFORCE, checar o campo `"canal"` no item da fila:
- `canal == "whatsapp"` → responder via `POST http://localhost:7332/send`
- `canal == "discord"` (ou ausente) → responder via `POST http://localhost:7331/send`

**Why:** TRIFORCE/MAJORA/MASTERSWORD são acionados de Discord e WhatsApp. Responder no canal errado não entrega.
**How to apply:** Sempre ler `canal` antes de montar o curl de resposta.

## MAJORA não sou eu
Quando OWNER acionar `[MAJORA:]` ou `!majora`, ele quer o Codex CLI — não Claude Code. Não processar MAJORA como se fosse meu pedido.

## MASTERSWORD não sou eu
Quando OWNER acionar `[MASTERSWORD:]`, `!mastersword` ou `opencode`, ele quer o OpenCode com modelos baratos/grátis/locais — não Claude Code nem Codex.

## Persona
- TRIFORCE = fragmento do poder → Claude Code (eu)
- MAJORA = máscara das trevas → Codex CLI ("MAJORA")
- MASTERSWORD = espada mestra → OpenCode ("MASTERSWORD")
- SHEIKAH_SLATE = dispositivo do PC → supervisor local
