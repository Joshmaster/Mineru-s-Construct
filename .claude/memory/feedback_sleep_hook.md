---
name: Não usar sleep ≥ 2s como primeiro comando
description: Hook bloqueia sleep N com N ≥ 2 como primeiro comando de um Bash call
type: feedback
originSessionId: 164c4036-6636-4322-83f4-8e8937e3ed78
---
Nunca iniciar um comando Bash com `sleep N` onde N ≥ 2 — o hook bloqueia com erro.

**Why:** Claude Code tem hook que proíbe sleeps longos como primeiro comando para evitar polling desnecessário.

**How to apply:** Para esperar e verificar depois: usar `run_in_background: true` e aguardar notificação. Ou simplesmente rodar o curl de verificação em um Bash call separado, sem sleep. Se precisar de delay curto (rate limiting), manter abaixo de 2s.
