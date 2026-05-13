---
name: feedback_regra0_dados_sensiveis
description: REGRA 0 — dados sensíveis (tokens, chaves, senhas, sessões) NUNCA vão pro git; somente local server
metadata:
  type: feedback
---

**REGRA 0 — dados sensíveis são LOCAL ONLY. Nunca vão pro git, nunca são expostos.**

Isso vale para qualquer: token Discord/GitHub/OpenRouter/Groq, chave de API, senha, sessão WhatsApp, credencial de qualquer serviço.

**Why:** O OWNER deixou isso explícito como regra número zero do projeto. Token que vaza no git é token que precisa ser revogado imediatamente — causa downtime e risco de segurança.

**How to apply:**
- Antes de qualquer `git add`, verificar se o arquivo contém dados sensíveis.
- Se um token/chave aparece num arquivo, confirmar que o arquivo está no `.gitignore` antes de continuar.
- Nunca sugerir commitar `hyrule_env.py`, `local_secrets/`, `*.key`, `*.token`, `*credentials*` ou qualquer variante.
- Se por engano algo sensível for commitado: alertar o OWNER para revogar o token IMEDIATAMENTE, depois remover do histórico com `git filter-repo` ou `BFG`.
- Dúvida? Não commita. Pergunta primeiro.

Relacionado: [[feedback_git_security]]
