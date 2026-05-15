---
name: Handoff de sessao
description: Estado da última sessão - lido ao iniciar para retomar sem perda de contexto
type: project
---

## Feito nesta sessao (2026-05-14)

### Roteamento por linguagem natural com clarificação IA (`llm.py`, `link_discord.py`, `bot/main.py`)
- `classify_skill_intent` agora retorna `confidence` no JSON; se `< 0.7` → trata como conversa
- Funções compartilhadas adicionadas ao `llm.py` (sync, usadas por Discord e WA via `run_in_executor`):
  - `gerar_pergunta_skill(skill, msg_original)` → LLM gera pergunta natural ao usuário
  - `resolver_pendente(skill, resposta)` → LLM extrai args ou detecta "você escolhe"
  - `ia_escolher_args(skill)` → LLM sugere um argumento quando usuário pede que a IA escolha
- `_pending_clarification` dict em ambos os bots: `{user_id: (skill, msg_orig, timestamp, retries)}`
  - TTL 600s (evicção automática a cada mensagem)
  - Máx 2 retries antes de cair para conversa normal

### Discord (`link_discord.py`)
- `_CODE_AGENTS` dict colapsa triforce/majora/mastersword
- `_gerar_pergunta_skill`, `_resolver_pendente`, `_ia_escolher_e_executar` delegam para `_llm`
- Bloco clarificação em `on_message` antes do classify normal

### WhatsApp (`bot/main.py`)
- `self._pending_clarification` em `__init__`
- Fluxo de clarificação inserido antes do URL auto-detect

### Rotação de chave 429 OpenRouter (`llm.py`)
- `_key_429` rastreia cooldown por chave (60s)
- 2-pass em `_call_openrouter`: chaves disponíveis primeiro, depois em cooldown

## Estado atual dos serviços
- WA Bridge: ● rodando (porta 7334)
- WhatsApp bot: ● rodando (PID 210607)
- Discord bot: ● rodando (PID 209762)
- Supervisor: ● rodando
- TRIFORCE/MAJORA/MASTERSWORD: ● rodando

## Pendente
- Testar fluxo de clarificação em produção (Josh vai testar)

## Cuidados com dados sensíveis
- NUNCA mandar chaves no chat
- Para atualizar chaves: editar `hyrule_env.py` direto no terminal
- Não commitar: `link-bot/config/config.json`, `link-bot/.linkbot/`, `whatsapp-bridge/auth/`, `DISCORD/reminders.json`, `hyrule_env.py`, `local_secrets/`

---
Atualizado ao encerrar cada sessao. Nao acumula - sobrescreve.
