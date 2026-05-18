---
name: Handoff interagentes Hyrule
description: Ponte entre TRIFORCE/Claude, MAJORA/Codex e MASTERSWORD/OpenCode; quem sai escreve para quem entrar continuar
type: project
---

## Recado para a proxima camada/agente

Sessao atualizada em 2026-05-17.

### Feito nesta sessao

**Card Boss Mundial / Diablo corrigido:**
- `world_boss_card.py`
  - Removido countdown/tempo relativo do card (`Em 00:xx`, `Encerra em`, etc.).
  - Card agora mostra data/dia do boss e hora grande do boss.
  - Rodape mostra `Boss Mundial - DD/MM as HH:MM`.
  - `get_next_boss()` agora respeita janela ativa de 15 min: durante a janela mostra o boss atual; depois avanca para o proximo.
- `world_boss_notify.py`
  - Continua disparando o aviso 5 min antes (`REMINDER_MIN = 5`).
  - Legenda nao menciona "em 5 minutos"; usa `Boss Mundial - DD/MM as HH:MM`.
  - Envio travado para Discord only (`localhost:7331/send-file`); se mudar para outro endpoint, o script falha.
- `WorldBossReminder.tsx`
  - Removido countdown da tela.
  - Proximos bosses mostram apenas data/hora, sem `+Xh` nem contador.
- Criada memoria permanente `.claude/memory/feedback_world_boss_card.md`.
- `project_hyrule.md` e `MEMORY.md` atualizados com a regra do card.

### Regra importante gravada

Boss Mundial/Diablo:
- aviso automatico 5 min antes;
- somente Discord, nunca WhatsApp;
- card e legenda mostram horario real por dia/hora;
- nao mostrar countdown, "faltam X minutos", "em 5 minutos" ou "encerra em".

### Validacoes feitas

- `python3 -m py_compile world_boss_card.py world_boss_notify.py`
- Testes de borda do calculo:
  - `17/05 18:59 -> 17/05 19:00`
  - `17/05 19:00 -> 17/05 19:00`
  - `17/05 19:10 -> 17/05 19:00`
  - `17/05 19:15 -> 17/05 22:30`
  - `17/05 22:00 -> 17/05 22:30`
  - `17/05 22:40 -> 17/05 22:30`
  - `17/05 22:46 -> 18/05 02:00`
- `git diff --check`
- Busca confirmou que `Boss Mundial`/`boss_card` nao aparece em fluxo do WhatsApp; apenas `world_boss_notify.py` e log local.

### Estado dos servicos

Validado com `python3 startup_services.py status`:
- Hyrule Proxy: rodando
- Discord bot: online
- Supervisor: rodando
- WA Bridge: rodando na porta 7334
- WhatsApp bot: rodando
- TRIFORCE daemon: rodando
- MAJORA watcher: rodando
- MASTERSWORD watcher: rodando
- itch-monitor: rodando
- Boss notify: rodando, reiniciado apos a mudanca
- FFmpeg: instalado

### Pendencias / atencao

- As alteracoes foram preparadas para commit/push pela Regra 0.1.
- Se mexer no card de Boss Mundial no futuro, seguir `.claude/memory/feedback_world_boss_card.md`.
