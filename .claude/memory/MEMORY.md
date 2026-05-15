# Memory Index

- [REGRA 0 — Dados sensíveis local only](feedback_regra0_dados_sensiveis.md) — tokens, chaves e credenciais NUNCA vão pro git; somente servidor local

- [Projeto Hyrule](project_hyrule.md) — arquitetura completa: bot Link, supervisor, watcher, proxy, hooks, fluxo de pedidos
- [Rotina e comportamento padrão](feedback_session_start.md) — o que fazer a cada sessão, como responder ao "claude link", o que monitorar proativamente
- [Modelos Ollama](project_ollama_models.md) — qwen3:8b em uso, histórico de modelos testados
- [Sleep hook bloqueado](feedback_sleep_hook.md) — não usar sleep ≥ 2s como primeiro comando Bash
- [WebSearch com data correta](feedback_websearch_date.md) — sempre usar mês/ano atual nas queries
- [Handoff de sessão](session_handoff.md) — estado da última sessão (Claude Code ou Codex), lido ao iniciar e escrito ao encerrar
- [TRIFORCE e MAJORA](feedback_triforce_majora.md) — TRIFORCE chama Claude Code, MAJORA chama Codex CLI; ambos canal-aware (discord/whatsapp)
- [Ambiente do servidor](project_environment.md) — Ubuntu Linux `~/Agents/`, nunca usar paths Windows hardcoded com username
- [Segurança antes de Git](feedback_git_security.md) — validar estado atual e histórico antes de push/pull; perguntar ao OWNER quando algo parecer pessoal mas ambíguo
- [Nomes de contato](feedback_contact_names.md) — usar "josh"/"manu" em DMs Discord e WA, nunca "OWNER"/"USER2"
- [Performance LLM Ollama](feedback_llm_performance.md) — think=False, persona compacta, circuit breaker 401, timeouts por função
- [Tailscale VPN](project_tailscale.md) — acesso SSH remoto via Tailscale; mineru (100.121.86.1) ↔ pcbrs1291411 (100.85.111.78)
