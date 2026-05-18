---
name: Handoff interagentes Hyrule
description: Ponte entre TRIFORCE/Claude, MAJORA/Codex e MASTERSWORD/OpenCode; quem sai escreve para quem entrar continuar
type: project
---

## Recado para a proxima camada/agente

Sessao atualizada em 2026-05-18.

### Feito nesta sessao

**Pesquisa de plataformas externas de imagem IA (esta sessao):**
- Google Gemini API testada — billing exige R$200 pre-pago; descartada.
- Testadas outras plataformas gratuitas — nenhuma superou o Cloudflare Workers AI.
- Comparativo feito com 2 prompts (Diablo 4 e Zelda/Master Sword).

**Resultado final do comparativo:**
- **Cloudflare Workers AI Flux Schnell continua imbativel** — ganhou nas duas rodadas.
- Nenhuma alteracao feita no codigo — Flux Schnell permanece padrao em `world_boss_card.py`.

### Regra importante gravada

Boss Mundial/Diablo:
- aviso automatico 5 min antes;
- somente Discord, nunca WhatsApp;
- card e legenda mostram horario real por dia/hora;
- nao mostrar countdown, "faltam X minutos", "em 5 minutos" ou "encerra em".

### Estado dos servicos

- Todos os servicos rodando no inicio da sessao (validado 2026-05-17).
- Git com M em session_handoff.md — precisa commitar.

### Pendencias / atencao

- Nao alterar modelo de imagem em `world_boss_card.py` sem testar — Flux Schnell CF e o padrao validado em 2 rodadas.
- Pesquisa de plataformas externas concluida: nao ha alternativa gratuita melhor que o CF atual sem ativar billing.
