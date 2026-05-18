---
name: Handoff interagentes Hyrule
description: Ponte entre TRIFORCE/Claude, MAJORA/Codex e MASTERSWORD/OpenCode; quem sai escreve para quem entrar continuar
type: project
---

## Recado para a proxima camada/agente

Sessao atualizada em 2026-05-18 (terceira parte — BREAKTHROUGH mage.space).

### Feito nesta sessao

**Pesquisa de plataformas externas de imagem IA:**
- Google Gemini API — billing exige R$200 pre-pago; descartada.
- HuggingFace, fal.ai — requerem credito/pagamento para uso real.

**Engenharia reversa mage.space — CONCLUIDA COM SUCESSO:**

API privada Next.js completamente desbloqueada. Geracao com Mango 2 validada via API.

DESCOBERTA CHAVE: `fast_mode: true` e o flag de gasto de gems no servidor.
- fast_mode=false → plano pago exigido (erro 4262)
- fast_mode=true + __session cookie valido → server debita gems e gera

Custo em gems (fast_mode=true):
- mango (v1): 45 gems
- mango-v3: 55 gems
- mango-v2: 60 gems
- guava: 79 gems, guava (Z1): 37 gems

Fluxo completo validado:
1. refresh_token Firebase → id_token fresco (dura 1h)
2. POST / com Next-Action 40f8302e... → cria __session cookie (auth)
3. POST /explore com Next-Action 407ca2a0... → retorna history_id imediatamente
4. Poll POST /explore com Next-Action 40d312579... → aguarda status=success e URL da imagem
5. Credenciais em /tmp/mage_investigation.zip (nunca comitar)

Config validada para Mango 2 portrait:
- architecture: mango, model_id: mango-v2, resolution: 2K (maiusculo!), fast_mode: true
- aspect_ratio: portrait → gera 1792x2304, ~13s, 60 gems
- Saldo atual: 180 gems (240 signup - 60 gastos)

Erros de plano (sem fast_mode):
- 4261 = Basic requerido (sdxl, flux)
- 4262 = Pro requerido (mango, hidream)
- 4260 = gems insuficientes (quando fast_mode=true mas saldo zerado)

**Comparativo de qualidade:**
- Mango 2 via mage.space: qualidade muito superior, 1792x2304, alta fidelidade
- Cloudflare Flux Schnell: rapido e gratuito ilimitado, qualidade boa mas inferior
- Conclusao: mage.space e melhor para artes de qualidade (enquanto tiver gems), CF para volume

### Integracao a fazer (pendente)

- Criar `mage_client.py` em ~/Agents/ com o fluxo completo encapsulado
- Integrar como backend premium em `world_boss_card.py` quando gems disponivel, CF como fallback

### Regra importante gravada

Boss Mundial/Diablo:
- aviso automatico 5 min antes;
- somente Discord, nunca WhatsApp;
- card e legenda mostram horario real por dia/hora;
- nao mostrar countdown, "faltam X minutos", "em 5 minutos" ou "encerra em".

### Estado dos servicos

- Todos os servicos rodando (validado 2026-05-17).

### Pendencias / atencao

- Nao alterar modelo de imagem em `world_boss_card.py` sem testar — Flux Schnell CF e o padrao atual validado.
- mage.space: credenciais ficam SOMENTE em /tmp durante sessao — nunca comitar.
- Saldo mage gems: 180 restantes de 240 signup (cada Mango 2 custa 60).
