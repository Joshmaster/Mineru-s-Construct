---
name: Handoff interagentes Hyrule
description: Ponte entre TRIFORCE/Claude, MAJORA/Codex e MASTERSWORD/OpenCode; quem sai escreve para quem entrar continuar
type: project
---

## Recado para a proxima camada/agente

Sessao atualizada em 2026-05-18.

### Feito nesta sessao

**Sistema de cards Boss Mundial Diablo 4 — boss_cards.py:**
- Arquivo: `~/Agents/tools/boss_cards.py`
- Gera 5 cards (atual + 4 próximos) e envia pro Discord canal `1465722444105908315`
- Cada card tem label "IA: <fonte>" no canto inferior esquerdo — fundo escuro + texto dourado, fonte 22px
- session_keeper.py cuida dos tokens automaticamente

**Regra de LLM de imagem — HIERARQUIA ATUAL:**
1. **Recraft** — primário (30 créditos/dia, renovam ~15:56 UTC)
   - JWT Keycloak 1h, auto-renovado via Playwright headless
   - Token: `~/Agents/tools/cookies/recraft_bearer.txt`
   - session_keeper.py renova antes de expirar
2. **CF Flux Schnell** — fallback infinito e gratuito
   - `CF_WORKER_IMG_URL` em `hyrule_env.py`

**DeeVid — SUSPENSA (conta bloqueada):**
- API direta: tasks ficam PROCESSING para sempre no plano free
- Browser CDP: botão "Criar" fica disabled porque `image/task/existed?type=TEXT2IMAGE` retorna True
  — tasks acumuladas de teste entupem o queue do servidor deles
- Vai desbloquear sozinho quando as tasks expirarem (horas/dias)
- OWNER vai gerar nova conta DeeVid quando quiser reativar
- Para reativar: `bg_from_deevid_browser()` já está implementado em boss_cards.py — só colocar de volta no `_bg_with_fallback()` como opção 1

**session_keeper.py — `~/Agents/tools/session_keeper.py`:**
- `status` — verifica validade dos tokens
- `refresh-recraft` — roda Playwright headless e captura novo Bearer
- `capture-deevid` — captura cookies do Chrome CDP aberto
- `daemon` — loop que renova automaticamente antes de expirar

### Regras fixas

Boss Mundial/Diablo:
- aviso automático 5 min antes
- somente Discord, nunca WhatsApp
- card mostra horário real por dia/hora
- NÃO mostrar countdown, "faltam X min", "em 5 min", "encerra em"

LLM de imagem (hierarquia):
- Recraft → CF Flux Schnell
- DeeVid suspensa até nova conta

### Estado dos servicos

- Recraft: funcionando (token auto-renovado via Playwright)
- CF Flux Schnell: sempre disponível
- DeeVid: bloqueada por tasks fantasma — OWNER vai gerar nova conta

### Arquivos novos nesta sessao

```
~/Agents/tools/boss_cards.py      — gerador de cards Boss Mundial
~/Agents/tools/session_keeper.py  — keeper de tokens Recraft/DeeVid
~/Agents/tools/.gitignore         — exclui cookies/ e api_capture/
```

### Pendencias

- OWNER vai criar nova conta DeeVid → rodar `capture-deevid` depois do login
- DeeVid nova conta: reativar `bg_from_deevid_browser()` como primário em `_bg_with_fallback()`
