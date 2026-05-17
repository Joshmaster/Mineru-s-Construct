---
name: Handoff interagentes Hyrule
description: Ponte entre TRIFORCE/Claude, MAJORA/Codex e MASTERSWORD/OpenCode; quem sai escreve para quem entrar continuar
type: project
---

## Recado para a proxima camada/agente

Este arquivo e o canal de handoff entre TRIFORCE/Claude, MAJORA/Codex e MASTERSWORD/OpenCode. Leia primeiro ao retomar contexto; sobrescreva ao encerrar ou transferir trabalho para outra camada.

## Sessao encerrada em 2026-05-16

### Feito nesta sessao (continuacao da sessao anterior)

**Cloudflare Worker — imagem de IA:**
- URL em `hyrule_env.py` como `CF_WORKER_IMG_URL` (NAO commitada)
- `reminder_art.py`: removida URL hardcoded, agora so usa `hyrule_env.py` ou fallback starfield local
- `img_gerar.py`: Pollinations removido completamente, substituido por Cloudflare Worker (flux-schnell)
- Header `User-Agent: HyruleBot/1.0` necessario nas requests ao Worker (sem ele retorna 403)
- `[IMG: prompt]` tag no texto do lembrete: `_extract_img_prompt()` parseia e usa como prompt customizado

**WhatsApp @lid fix:**
- Josh: `75771930505309@lid`, Manu: `266511428149405@lid` — SEMPRE @lid, nunca @s.whatsapp.net
- `main.py`: `_send_reminder()` tem bloco `elif send_to:` que usa `build_jid(send_to)` direto, sem passar pelo candidatos
- Presence keepalive: `_presence_keepalive_loop()` envia "available" a cada 270-330s (aleatorio) — anti-ban
- `whatsapp-bridge/index.js`: `/send/presence` sem `jid` agora funciona (global presence)

**Remedios — banco SQLite (`/home/joshlink/Agents/link-bot/.linkbot/data.db`):**
- IDs 1-6 deletados (velhos reminders de bombinha)
- IDs 7-13: todos apontam para grupo familia `120363151694928682@g.us`
- Mononitrato atualizado para "Mononitrato de Isossorbida 20mg" (IDs 8, 11, 13)
- IDs 14-15: one-shot 17/05 14:00, card zelda estilo, Josh PV e Manu PV (Discord + WA)
  - ID 14: `send_to=75771930505309@lid`, texto "comprar o milk gostosim [IMG: zelda...]"
  - ID 15: `send_to=266511428149405@lid`, mesmo texto

**Script zelda_milkshake_reminder.py:** rodando em background (PID ~18328), dorme ate 17/05 14:00 BRT e manda card zelda por Discord e WA para Josh e Manu. Se ja disparou, pode matar.

**World Boss Reminder:**
- `world_boss_card.py`: card PIL dark fantasy Diablo 4
  - Ancora: 2026-05-16T22:00:00-03:00, intervalo 210min
  - Layout: DATA em cima (fonte 48), HORA grande no centro (fonte 130), countdown menor abaixo
  - Background: CF Worker flux-schnell (10 prompts dark fantasy) ou fallback gradiente infernal
  - Fontes: Orbitron-Variable.ttf em `~/.local/share/fonts/`
- `world_boss_notify.py`: daemon Discord-only, TARGETS = ["josh_barbosa", "manu"]
  - Loop 15s, avisa 5min antes de cada spawn (janela 30s)
  - Import: `from world_boss_card import render_boss_card, get_next_boss, intervalMs, REMINDER_MIN`
- `WorldBossReminder.tsx`: componente React+TS, live countdown, Notification API, beep sintetico
- `startup_services.py`: integrado boss notify daemon (start/stop/restart/status)

**Contatos salvos em `.claude/memory/contacts.md`:**
- Josh: WA `75771930505309@lid`, Discord `josh_barbosa`/`257334783930007552`
- Manu: WA `266511428149405@lid`, Discord `manu`/`512825467397603328`
- Grupo familia: `120363151694928682@g.us` (Josh, Yash/irmao, Joelma/mae, Paulo/pai)

### Estado dos servicos ao encerrar
- Hyrule Proxy: rodando (porta 7330)
- Discord bot: rodando (porta 7331)
- Supervisor: rodando
- WA Bridge: rodando (porta 7334)
- WhatsApp bot: rodando (link-bot)
- TRIFORCE daemon: rodando
- MASTERSWORD watcher: rodando
- Boss notify daemon: rodando (PID em `.boss_notify_pid`)

### Estado Git
- Branch master — pendente push de `world_boss_card.py` e `session_handoff.md`
- `hyrule_env.py` nao rastreado (contem chaves)
- `.boss_notify_pid` e `.claude/scheduled_tasks.lock` nao rastreados (ignorar)

### Pendencias / atencao
- Zelda milkshake reminder (IDs 14-15 no banco) dispara 17/05 14:00 — verificar se chegou
- Se supervisor ou boss notify caiu, use `python3 startup_services.py start` para relancar
- Orbitron font: se mudar de maquina, reinstalar em `~/.local/share/fonts/`
- `.task_memory/` nao rastreado — nao commitar (contem confirmacoes de identidade)
