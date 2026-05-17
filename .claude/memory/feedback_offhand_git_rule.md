---
name: Regra offhand + git após aprovação
description: Após OWNER gostar de uma mudança, sempre atualizar session_handoff.md e fazer git push — automaticamente, sem precisar pedir
type: feedback
---

Após OWNER aprovar ou gostar de qualquer mudança (código, config, feature), executar sempre na ordem:

1. Atualizar `session_handoff.md` com o que foi feito
2. `git add` nos arquivos modificados + `session_handoff.md`
3. `git commit` com mensagem descritiva
4. `git push origin master`

**Why:** OWNER quer o projeto sempre sincronizado sem ter que lembrar de pedir o push. Regra hierárquica: vem logo abaixo da REGRA 0 (dados sensíveis nunca vão pro git).

**How to apply:** Toda vez que OWNER der um sinal de aprovação ("perfeito", "obrigado", "ficou bom", "gostei", ou simplesmente parar de pedir ajustes e mudar de assunto), disparar o ciclo offhand + git automaticamente sem aguardar pedido explícito.
