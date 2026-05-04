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

## Quando acordar via asyncRewake (pedido do Discord)
- Processar o pedido imediatamente
- Responder ao OWNER via: `curl -X POST http://localhost:7331/send -H "Content-Type: application/json" -d '{"to":"OWNER","msg":"..."}'`
- Confirmar no log após envio

## Gatilho "claude link"
Quando OWNER disser "claude link":
1. Confirmar todos os serviços ativos (bot, proxy, supervisor, watcher)
2. Mostrar últimas conversas do Discord
3. Resumir o que foi configurado/mudado na sessão anterior
4. Perguntar como continuar

**Why:** OWNER quer retomar contexto rapidamente após abrir nova sessão sem precisar explicar tudo de novo.
**How to apply:** Ler memory, checar logs, confirmar status e apresentar resumo conciso do estado atual do sistema.

## Ao encerrar sessão (quando OWNER disser "vou testar", "até mais", "vou fechar", etc.)
Antes de encerrar, salvar na memória:
1. O que foi alterado nos arquivos (quais scripts, qual mudança principal)
2. O que ficou pendente ou com problema
3. Qualquer descoberta importante (ex: Groq precisa de headers especiais)
Atualizar `project_hyrule.md` com o estado atual do sistema.

**Why:** OWNER pode voltar com modelo diferente (kimi via `ollama launch claude --model kimi-k2.5:cloud`) e o contexto precisa estar completo para retomar sem explicar tudo de novo.
**How to apply:** Ao detectar sinal de encerramento, rodar Write/Edit nos arquivos de memória relevantes antes de responder.
