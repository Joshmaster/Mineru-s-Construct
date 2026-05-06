---
name: Handoff de sessão
description: Estado da última sessão — lido ao iniciar para retomar sem perder contexto
type: project
---

## O que estava em andamento
Correções aplicadas no fluxo TRIFORCE/MAJORA e no autostart do Hyrule.

## O que ficou pendente
Nenhum bloqueio conhecido.

## Estado dos serviços
`hyrule.service` está habilitado no systemd e foi validado com restart pelo próprio systemd.

Serviços ativos:
- Hyrule Proxy em `127.0.0.1:8765`
- Discord HTTP API em `127.0.0.1:7331`
- Supervisor
- WhatsApp HTTP API em `127.0.0.1:7332`
- TRIFORCE daemon
- MAJORA watcher
- Ollama em `127.0.0.1:11434`

## Notas rápidas
- `!MAJORA` no Discord agora entra direto em `[MAJORA-PEDIDO]` e não depende do LLM.
- O supervisor não drena mais `codex_queue.json`; só o watcher da MAJORA consome a fila.
- WhatsApp não repete mais o texto do pedido nas mensagens de acionamento de TRIFORCE/MAJORA.
- `startup_services.py` agora sobe processos desacoplados, gerencia proxy, evita duplicar MAJORA e mostra proxy/majora no status.
- `CLAUDE CODE/HYRULE.md` tem alteração local de chave OpenRouter e não deve ser commitado.

---
*Atualizado ao encerrar cada sessão. Não acumula — sobrescreve.*
