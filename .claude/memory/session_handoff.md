---
name: Handoff de sessão
description: Estado da última sessão — lido ao iniciar para retomar sem perder contexto
type: project
---

## O que estava em andamento
Configuração do OpenCode como **MASTERSWORD**, terceira opção de agente ao lado de TRIFORCE/Claude Code e MAJORA/Codex.

## O que foi alterado
- Instalado `opencode-ai` global via nvm; `opencode --version` = 1.14.39.
- Criado `watch_mastersword_queue.py`.
- Nova fila `mastersword_queue.json`.
- Novo lock `.mastersword_processing.lock`.
- `startup_services.py` agora inicia, para e mostra status da MASTERSWORD.
- `bot_supervisor.py` roteia `[MASTERSWORD-PEDIDO]` e tarefas WhatsApp tipo `mastersword`.
- Discord aceita `mastersword`, `opencode` e tag `[MASTERSWORD: ...]`.
- WhatsApp aceita `!mastersword`, `!opencode` e tag `[MASTERSWORD: ...]`.
- Persona em `OPENCODE/roaming/LINK_PERSONA.md` documenta MASTERSWORD.
- Config versionada em `OPENCODE/mastersword.opencode.json`.
- Config local ativa em `~/.config/opencode/opencode.json`; watcher copia o template se faltar.
- Docs e memórias atualizadas.

## Modelos MASTERSWORD
Ordem automática:
1. `openrouter/openai/gpt-oss-20b:free`
2. `openrouter/google/gemma-4-31b-it:free`
3. `openrouter/nvidia/nemotron-3-super-120b-a12b:free`
4. `ollama/qwen2.5:7b`

Groq foi removido da ordem automática porque `opencode run` + tool context excedeu o limite de contexto dos modelos Groq testados.

## Validação
- `python3 -m py_compile` passou nos arquivos Python alterados.
- `git diff --check` passou.
- Busca por tokens reais em arquivos versionados não encontrou segredos.
- `check_llms.py` mostra OpenCode/MASTERSWORD respondendo.
- Teste direto de MASTERSWORD com `openrouter/openai/gpt-oss-20b:free` retornou `OK_MASTERSWORD`.
- `startup_services.py restart-nolimp` executado; todos os serviços voltaram.

## Estado dos serviços
- Hyrule Proxy: rodando.
- Discord bot: online.
- Supervisor: rodando.
- WhatsApp bot: rodando.
- TRIFORCE daemon: rodando.
- MAJORA watcher: rodando.
- MASTERSWORD watcher: rodando.

## Pendente
- Fazer commit/push se ainda não tiver sido feito nesta sessão.
- Ideia futura do OWNER: discutir LLM local.

---
*Atualizado ao encerrar cada sessão. Não acumula — sobrescreve.*
