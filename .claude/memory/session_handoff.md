---
name: Handoff de sessão
description: Estado da última sessão — lido ao iniciar para retomar sem perder contexto
type: project
---

## O que estava em andamento
Atualização completa do projeto no GitHub: código, documentação de instalação e configuração atual.

## O que foi alterado
- `README.md` e `SETUP.md` reescritos para refletir Ubuntu atual, nvm/Node 22, Claude Code auto-update, systemd, portas, filas, TRIFORCE, MAJORA e segurança.
- `check_llms.py` deixou de ter chaves hardcoded e agora lê `hyrule_env.py`.
- `CLAUDE CODE/HYRULE.md` e `CLAUDE CODE/global/HYRULE.md` foram saneados com placeholders de chave.
- `CLAUDE CODE/proxy.py` e `CLAUDE CODE/global/hyrule_fallback.py` agora resolvem placeholders usando `hyrule_env.py` ou env vars.
- `watch_codex_queue.py` tem lock `.majora_processing.lock` para evitar processamento paralelo/recursivo.
- `triforce_daemon.py` não usa fallback LLM para mascarar falha do Claude e alerta quando token OAuth está perto de expirar.
- Memórias do projeto atualizadas, incluindo Ollama atual `qwen2.5:7b`.
- Remote local do git trocado para URL sem token.

## Validação
- `python3 -m py_compile` passou para scripts alterados.
- Busca por tokens reais em arquivos versionados não encontrou segredos.
- `check_llms.py` mostrou Discord, proxy, Ollama, OpenRouter e Groq respondendo.
- `claude update` confirmou Claude Code `2.1.131` atualizado.

## Estado dos serviços
- Hyrule Proxy: rodando.
- Discord bot: online.
- Supervisor: rodando.
- WhatsApp bot: rodando.
- TRIFORCE daemon: rodando.
- MAJORA watcher: rodando.

## Pendente
- Fazer commit e push se ainda não tiver sido feito nesta sessão.

---
*Atualizado ao encerrar cada sessão. Não acumula — sobrescreve.*
