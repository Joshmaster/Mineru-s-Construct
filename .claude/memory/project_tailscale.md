---
name: project_tailscale
description: Conexão SSH remota ao servidor Hyrule é feita via Tailscale VPN
metadata:
  type: project
---

Acesso remoto ao servidor usa **Tailscale VPN**.

**Why:** Permite SSH seguro sem expor portas públicas — Josh acessa de qualquer lugar via rede Tailscale privada.

**How to apply:** Ao falar sobre acesso remoto, configuração de SSH ou conectividade com o servidor, assumir Tailscale como o método de conexão.

## Nós na rede (último check: 2026-05-14)
- `mineru` (servidor Hyrule, Linux Ubuntu) — `100.121.86.1`
- `pcbrs1291411` (PC Windows de Josh) — `100.85.111.78`
- `poco-f7` (Android de Josh) — `100.120.120.43`
- Conta Tailscale: `joshuevieirabarbosa@`
