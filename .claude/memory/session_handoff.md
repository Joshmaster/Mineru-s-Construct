---
name: Handoff interagentes Hyrule
description: Ponte entre TRIFORCE/Claude, MAJORA/Codex e MASTERSWORD/OpenCode; quem sai escreve para quem entrar continuar
type: project
---

## Recado para a proxima camada/agente

Sessao atualizada em 2026-05-17.

### Feito nesta sessao

**Card de rotina de remedios:**
- `link-bot/bot/core/reminder_art.py`
  - Adicionado `render_medication_schedule_card(reminders)`.
  - Gera imagem 1080x1520 estilo Star Wars/Hora do Remedio, mas como quadro de rotina.
  - Mostra todos os horarios diarios ativos e os remedios/doses de cada horario.
  - Corrigido layout para horarios com muitos remedios, sem sobreposicao.
- `link-bot/bot/skills/lembrete.py`
  - Nova skill `remedios_card`.
  - Gatilhos naturais: `card dos remedios`, `horarios dos remedios`, `horarios do remedio`, `rotina de remedios`, `!remedios`.
  - Quando acionada, manda imagem do card com legenda curta `Rotina de remedios`.
- Testado com os lembretes reais do banco SQLite.
- Card enviado no grupo familia `120363151694928682@g.us` via WhatsApp Bridge.

**Milkshake desativado/limpo:**
- IDs 14 e 15 do banco ja estavam `sent=1` e nao repetem.
- Confirmado que nao havia processo `zelda_milkshake_reminder.py` rodando.
- Removido `zelda_milkshake_reminder.py` do projeto, pois era one-shot vencido.

**Higiene e robustez:**
- `.gitignore`: adicionados `.boss_notify_pid` e `.claude/scheduled_tasks.lock`.
- Limpados caches Python (`__pycache__`/`.pyc`) regeneraveis.
- `watch_codex_queue.py` e `watch_mastersword_queue.py`:
  - Corrigido risco de perda de pedido quando lock esta ativo.
  - Agora watcher nao limpa/processa fila enquanto outro processo segura lock.
  - Se cair em lock no processamento, re-enfileira o item e apenas loga localmente.

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
- Boss notify: rodando
- FFmpeg: instalado

### Validacoes feitas

- `python3 -m compileall -q .`
- `node --check whatsapp-bridge/index.js`
- `PYTHONPATH=/home/joshlink/Agents/link-bot python3 -m compileall -q link-bot/bot/core/reminder_art.py link-bot/bot/skills/lembrete.py`
- `git diff --check`
- Teste local do router com a frase real do grupo:
  - `@26565077414035 manda ai os horarios do remedio` -> `remedios_card`

### Git

OWNER aprovou e pediu Regra 0.1: atualizar handoff/offhand e subir no git.
Arquivos esperados no commit:
- `.gitignore`
- `.claude/memory/session_handoff.md`
- `.claude/memory/project_hyrule.md`
- `link-bot/bot/core/reminder_art.py`
- `link-bot/bot/skills/lembrete.py`
- `watch_codex_queue.py`
- `watch_mastersword_queue.py`
- remocao de `zelda_milkshake_reminder.py`

### Pendencias / atencao

- O card de rotina usa os lembretes recorrentes ativos do proprio sender (`sender_jid`). No grupo familia funcionou porque os lembretes estao no JID do Josh.
- Se quiser que qualquer membro do grupo peca o card e receba a rotina do Josh, ajustar a skill para fallback no owner configurado.
- A legenda foi reduzida para `Rotina de remedios` porque OWNER queria via card/imagem, nao textao.
