---
name: Seguranca antes de Git
description: Rotina obrigatoria para pull, commit e push sem vazar dados sensiveis ou pessoais
type: feedback
---

## Regra principal

Antes de qualquer `git push`, e depois de qualquer `git pull`/`fetch` que traga mudancas novas, validar o repositorio inteiro:

1. `git status -sb`
2. Conferir arquivos rastreados suspeitos:
   - `.env`, `hyrule_env.py`, `config.json`, `local_secrets/`, `.linkbot/`;
   - bancos SQLite/DB, sessoes, QR, logs, filas;
   - `token_usage.*`, `whatsapp_tasks.json`, `claude_queue.json`, `codex_queue.json`, `mastersword_queue.json`;
   - anexos/imagens temporarias e URLs assinadas.
3. Varrer estado atual e historico inteiro por:
   - tokens/API keys de OpenRouter, Groq, GitHub, Discord e headers Bearer;
   - numeros reais, JIDs/LIDs, codigos de acesso;
   - nomes pessoais, e-mails, usernames locais, caminhos como `/home/<usuario>`;
   - URLs assinadas de Discord/CDN.
4. Rodar checagem de alta entropia nos arquivos rastreados quando houver mudanca sensivel.
5. Se precisar limpar historico, usar `git filter-repo`, revalidar o historico inteiro e so entao fazer push com `--force-with-lease`.

## Quando perguntar ao OWNER

Se algo parecer pessoal, mas nao for claramente segredo tecnico, perguntar ao OWNER antes de decidir.

Exemplos para perguntar:
- nome/apelido de pessoa;
- e-mail ou username que talvez seja publico;
- caminho local com usuario;
- imagem/anexo que talvez seja exemplo intencional;
- texto de conversa ou frase que talvez seja privada.

Nao precisa perguntar para itens obviamente sensiveis: tokens, sessoes, bancos, QR, logs, numeros reais, JIDs/LIDs, codigos de acesso e URLs assinadas. Esses devem ser removidos/sanitizados direto antes de commit/push.

## INCIDENTE — 2026-05-18

Token HuggingFace (`hf_...`) foi commitado dentro de `session_handoff.md` porque foi colocado no texto do handoff junto com as notas de sessao. GitHub bloqueou o push. Corrigido com `git commit --amend`.

**Licao:** qualquer chave/token que aparecer na conversa **NUNCA** vai pro handoff nem pra memoria — nem como exemplo, nem com "somente local". Se precisar registrar que um token existe, escrever apenas "token configurado localmente" sem o valor.

## Estado conhecido

Na ultima limpeza, o historico foi sanitizado e validado com resultado zero para:
- tokens conhecidos;
- caminhos/nomes pessoais procurados;
- IDs/numeros reais especificos do WhatsApp;
- alta entropia suspeita em arquivos rastreados.

O Git local deste repo deve usar e-mail neutro:

```bash
git config user.email owner@example.local
```
