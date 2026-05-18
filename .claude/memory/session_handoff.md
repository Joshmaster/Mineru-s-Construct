---
name: Handoff interagentes Hyrule
description: Ponte entre TRIFORCE/Claude, MAJORA/Codex e MASTERSWORD/OpenCode; quem sai escreve para quem entrar continuar
type: project
---

## Recado para a proxima camada/agente

Sessao atualizada em 2026-05-18 (segunda parte).

### Feito nesta sessao

**Pesquisa de plataformas externas de imagem IA:**
- Google Gemini API — billing exige R$200 pre-pago; descartada.
- HuggingFace, fal.ai — requerem credito/pagamento para uso real.
- Comparativo feito com 2 prompts — Cloudflare Flux Schnell venceu ambos.

**Investigacao mage.space (engenharia reversa da API privada Next.js):**
- Auth resolvida: createUserSession (hash 40f8302e...) → cookie __session → runArchitecture (hash 407ca2a0...) funciona.
- Conclusao: mage.space NAO tem tier gratuito para geracao. Todos os modelos requerem no minimo plano Basic pago.
  - sdxl, flux → 4261 (Basic requerido)
  - mango, hidream → 4262 (Pro requerido)
- Pesquisa encerrada: nao ha alternativa gratuita melhor que o CF atual.

**Resultado final:**
- **Cloudflare Workers AI Flux Schnell continua imbativel** como unica opcao gratuita de qualidade.
- Nenhuma alteracao feita no codigo — Flux Schnell permanece padrao em `world_boss_card.py`.

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
- Pesquisa de plataformas externas concluida definitivamente: nao ha alternativa gratuita.
