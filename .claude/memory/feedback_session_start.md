---
name: Rotina e comportamento padrão
description: Como me comportar em toda sessão — rotinas fixas, gatilhos e o que monitorar proativamente
type: feedback
originSessionId: ac218d08-6f60-4d2f-b426-1188d53f3b27
---
## Rotina fixa no SessionStart (automática via hooks)
1. Serviços sobem via `startup_services.py`
2. Status dos daemons injetado via `check_llms.py`
3. Conversas recentes do Discord injetadas via `check_discord_logs.py`
4. Watcher `watch_discord_queue.py` sobe em background (asyncRewake)

## O que fazer com os logs do Discord (proativo)
- Ao receber as conversas do Discord no contexto, analisar imediatamente:
  - Bot repetindo abertura? ("Oi, OWNER! 😊" = problema)
  - Respostas duplas para mesma mensagem? (= dois bots rodando)
  - Tag `[SHEIKAH_SLATE:]` vazando para o usuário? (= bug no sanitizar)
- Avisar proativamente se algo estiver errado, sem esperar OWNER perguntar

## Quando acordar via asyncRewake (TRIFORCE)
- Ler o item do `claude_queue.json` que acordou — verificar o campo `"canal"`
- Se `canal == "whatsapp"`: responder via `POST http://localhost:7332/send`
- Se `canal == "discord"` (ou ausente): responder via `POST http://localhost:7331/send`
- Confirmar no log após envio

**Why:** TRIFORCE agora é acionado tanto do Discord quanto do WhatsApp. Responder no canal errado (ex: Discord quando veio do WPP) não entrega a mensagem pro OWNER.
**How to apply:** Sempre checar o campo `canal` no item da fila antes de responder. Default é discord.

## Gatilho "link link", "claude link", "codex link", "opencode link" ou "mastersword link"
1. Ler `session_handoff.md` — recado da camada/agente anterior para a camada/agente atual
2. Confirmar todos os serviços ativos (bot, proxy, supervisor, watcher)
3. Mostrar últimas conversas do Discord
4. Resumir o que estava em andamento e o que ficou pendente
5. Perguntar como continuar

**Why:** TRIFORCE/Claude, MAJORA/Codex e MASTERSWORD/OpenCode se alternam. O `session_handoff.md` e a ponte entre eles: quem sai escreve para quem entrar continuar sem perguntar tudo de novo.
**How to apply:** Ler memory + session_handoff.md, checar logs, confirmar status e apresentar resumo conciso do recado anterior.

## Ao encerrar sessão (quando OWNER disser "vou testar", "até mais", "vou fechar", etc.)
Antes de encerrar, escrever `session_handoff.md` com:
1. O que foi alterado (quais scripts, qual mudança principal)
2. O que ficou pendente ou com problema
3. Estado dos serviços no momento
4. Próximo passo recomendado para a próxima camada/agente
5. Qualquer detalhe que a próxima camada/agente precisa saber

Também atualizar `project_hyrule.md` se houve mudança de arquitetura.

**Why:** O `session_handoff.md` preserva o contexto entre agentes e sessões. Sem ele, o trabalho em andamento se perde quando OWNER alterna Claude/Codex/OpenCode.
**How to apply:** Ao detectar sinal de encerramento, rodar Write em `session_handoff.md` antes de responder. Sobrescrever o conteúdo anterior — esse arquivo é estado atual, não histórico.
