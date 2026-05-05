---
name: Ambiente do servidor
description: Servidor Hyrule roda Ubuntu Linux, não Windows — paths e comandos devem refletir isso
type: project
---

## Fato
O sistema Hyrule roda em **Ubuntu Linux** (`~/Agents/`), não no PC Windows do OWNER.

**Why:** Sessões anteriores assumiam Windows (`C:\Users\OWNER\Agents\`) por causa do histórico de desenvolvimento. O servidor foi migrado/implantado no Ubuntu.
**How to apply:** Nunca usar paths Windows hardcoded. Sempre usar `Path(__file__).resolve()` ou `~/Agents/`. Comandos shell são bash, não PowerShell/cmd.

## Paths corretos
- Base: `~/Agents/`
- claude_queue: `~/Agents/claude_queue.json`
- codex_queue: `~/Agents/codex_queue.json`
- whatsapp_tasks: `~/Agents/whatsapp_tasks.json`
- link-bot config: `~/Agents/link-bot/config/config.json`
- persona: `~/Agents/OPENCODE/roaming/LINK_PERSONA.md`

## O que NÃO usar
- `C:\Users\OWNER\Agents\` — path Windows antigo, inválido no servidor
- `sys.platform == "win32"` como condição principal
- `os.startfile()`, `CREATE_NO_WINDOW`, `taskkill`, `wmic` sem fallback Linux
