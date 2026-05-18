---
name: Handoff interagentes Hyrule
description: Ponte entre TRIFORCE/Claude, MAJORA/Codex e MASTERSWORD/OpenCode; quem sai escreve para quem entrar continuar
type: project
---

## Recado para a proxima camada/agente

Sessao atualizada em 2026-05-18.

### Feito nesta sessao

**Pesquisa de plataformas externas de imagem IA — concluida:**
- Google Gemini API — billing exige R$200 pre-pago; descartada.
- HuggingFace, fal.ai — requerem credito/pagamento para uso real.
- mage.space — investigado e descartado. Gems sao unico recurso de conta free, nao renovam, e o site foi abandonado como alternativa.
- **Cloudflare Workers AI Flux Schnell permanece o padrao** — unica opcao gratuita ilimitada de qualidade validada.

### Regra importante gravada

Boss Mundial/Diablo:
- aviso automatico 5 min antes;
- somente Discord, nunca WhatsApp;
- card e legenda mostram horario real por dia/hora;
- nao mostrar countdown, "faltam X minutos", "em 5 minutos" ou "encerra em".

### Estado dos servicos

- Todos os servicos rodando (validado 2026-05-17).

### Pendencias / atencao

- Nao alterar modelo de imagem em `world_boss_card.py` sem testar — Flux Schnell CF e o padrao validado.
- Pesquisa de plataformas externas concluida. Proximo: OWNER vai buscar outro site de imagem IA gratuito.
