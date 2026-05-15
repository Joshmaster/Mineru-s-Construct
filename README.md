![Mineru's Construct](assets/banner.jpg)

```
 ╔══════════════════════════════════════════════════════════════════════════╗
 ║                                                                          ║
 ║        ███╗   ███╗██╗███╗   ██╗███████╗██████╗ ██╗   ██╗               ║
 ║        ████╗ ████║██║████╗  ██║██╔════╝██╔══██╗██║   ██║               ║
 ║        ██╔████╔██║██║██╔██╗ ██║█████╗  ██████╔╝██║   ██║               ║
 ║        ██║╚██╔╝██║██║██║╚██╗██║██╔══╝  ██╔══██╗██║   ██║               ║
 ║        ██║ ╚═╝ ██║██║██║ ╚████║███████╗██║  ██║╚██████╔╝               ║
 ║        ╚═╝     ╚═╝╚═╝╚═╝  ╚═══╝╚══════╝╚═╝  ╚═╝ ╚═════╝                ║
 ║                                                                          ║
 ║              ✦  C O N S T R U C T   D E   M I N E R U  ✦               ║
 ║                       ── Sistema Hyrule ──                               ║
 ║                                                                          ║
 ╚══════════════════════════════════════════════════════════════════════════╝
```

> *"Fui selada nesta forma por tempo suficiente para que o mundo esquecesse meu nome.*
> *Mas o propósito permanece. O Construct obedece. Hyrule persiste."*
> — **Mineru**, Sábia do Espírito

---

## ✦ A Palavra de Mineru

Sistema pessoal do **OWNER** — construído sobre as ruínas de incontáveis experimentações,
temperado em batalha e selado neste repositório para que o conhecimento não se perca.

O **Link** habita o sistema como assistente: bot no Discord, bot no WhatsApp,
supervisor de LLMs, proxy, e três artefatos de código — **TRIFORCE**, **MAJORA** e **MASTERSWORD**.

Repo: [github.com/Joshmaster/Mineru-s-Construct](https://github.com/Joshmaster/Mineru-s-Construct)
Runtime: Ubuntu Server em `~/Agents/`
Credenciais: fora do git, em `hyrule_env.py` (gerado por `setup.sh`)

---

## ✦ Os Três Artefatos

```
 ┌─────────────────────────────────────────────────────────────────────┐
 │                                                                     │
 │   ▲  TRIFORCE  ──  Claude Code CLI  ──  claude_queue.json          │
 │                    Tarefas complexas, código, análise profunda      │
 │                                                                     │
 │   ◉  MAJORA    ──  Codex CLI        ──  codex_queue.json           │
 │                    Agente de código alternativo                     │
 │                                                                     │
 │   ⚔  MASTERSWORD── OpenCode        ──  mastersword_queue.json      │
 │                    Modelos baratos, grátis e locais                 │
 │                                                                     │
 └─────────────────────────────────────────────────────────────────────┘
```

---

## ✦ A Hierarquia dos Custos

*Cada camada só é ativada se a anterior falhou. O Construct não desperdiça energia.*

```
  ① Cerebras    llama3.1-8b             ──  fast/chat curto
         │  falhou (429 / erro)
  ② Mistral     small latest            ──  quality/chat
         │  falhou
  ③ OpenRouter  gpt-oss / free models   ──  fallback remoto
         │  falhou
  ④ Ollama      qwen3:8b                ──  LOCAL · zero custo
         │  falhou
  ⑤ TRIFORCE / MAJORA / MASTERSWORD    ──  apenas quando escalado
```

O **TRIFORCE** não mascara erro do Claude com outro LLM.
Se `claude --continue` falhar, o erro aparece visível para correção.

---

## ✦ Arquitetura do Construct

```
 ~/Agents/
 │
 ├── startup_services.py         ◂ inicia / para / reinicia tudo
 ├── bot_supervisor.py           ◂ supervisor · tool calling · fallback LLM
 ├── triforce_daemon.py          ◂ claude_queue.json → claude --print --continue
 ├── watch_codex_queue.py        ◂ codex_queue.json  → codex exec
 ├── watch_mastersword_queue.py  ◂ mastersword_queue → opencode run
 ├── watch_discord_queue.py      ◂ asyncRewake para sessões interativas
 ├── check_llms.py               ◂ healthcheck completo
 ├── setup.sh                    ◂ gera hyrule_env.py + instala deps
 ├── hyrule_env.example.py       ◂ template sem segredos
 ├── hyrule_env.py               ◂ credenciais · IGNORADO pelo git
 │
 ├── DISCORD/
 │   └── link_discord.py         ◂ bot Discord + HTTP API :7331
 │
 ├── link-bot/
 │   ├── bot/main.py             ◂ bot WhatsApp + HTTP API :7332
 │   └── config/config.json      ◂ owner / allow list
 │
 ├── CLAUDE CODE/
 │   └── proxy.py                ◂ Hyrule Proxy :8765
 │
 └── OPENCODE/
     ├── mastersword.opencode.json   ◂ config MASTERSWORD (template)
     └── roaming/
         ├── LINK_PERSONA.md         ◂ persona do Link (todos os agentes)
         └── MASTERSWORD_INSTRUCTIONS.md  ◂ instruções operacionais OpenCode
```

---

## ✦ Portais e Filas

| Serviço             | Porta / Arquivo                       |
|---------------------|---------------------------------------|
| Discord HTTP API    | `localhost:7331`                      |
| WhatsApp HTTP API   | `localhost:7332`                      |
| Hyrule Proxy        | `localhost:8765`                      |
| Ollama              | `localhost:11434`                     |
| TRIFORCE queue      | `claude_queue.json`                   |
| MAJORA queue        | `codex_queue.json`                    |
| MASTERSWORD queue   | `mastersword_queue.json`              |
| MAJORA lock         | `.majora_processing.lock`             |
| MASTERSWORD lock    | `.mastersword_processing.lock`        |

---

## ✦ Invocar o Sistema

### Retomar sessão via SSH

```bash
cd ~/Agents && claude
```

Isso carrega automaticamente:
- `CLAUDE.md` e `AGENTS.md` — identidade Link e regras de trabalho
- `.claude/memory/` — memória do projeto e handoff da sessão anterior
- `.claude/settings.local.json` — permissões locais

Atalho opcional:

```bash
echo "alias hyrule='cd ~/Agents && claude'" >> ~/.bashrc && source ~/.bashrc
```

### Controle de serviços

```bash
python3 ~/Agents/startup_services.py start
python3 ~/Agents/startup_services.py status
python3 ~/Agents/startup_services.py restart
python3 ~/Agents/startup_services.py restart-nolimp   # preserva histórico
python3 ~/Agents/startup_services.py stop
```

### Logs em tempo real

```bash
tail -f ~/Agents/DISCORD/supervisor_out.log
tail -f ~/Agents/DISCORD/bot_error.log
tail -f ~/Agents/link-bot/.linkbot/whatsapp.log
tail -f ~/Agents/triforce_daemon.log
tail -f ~/Agents/majora.log
tail -f ~/Agents/mastersword.log
tail -f ~/Agents/"CLAUDE CODE"/proxy_runtime.log
```

---

## ✦ A Pedra Sheikah — Instalação

Guia completo em [SETUP.md](SETUP.md). Resumo:

### 1. Pacotes base

```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y python3 python3-pip python3-venv git curl wget procps xdg-utils libgomp1 ffmpeg
```

### 2. Ollama (LLM local)

```bash
curl -fsSL https://ollama.com/install.sh | sh
sudo systemctl enable --now ollama
ollama pull qwen2.5:7b
```

### 3. Node via nvm

```bash
curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.39.7/install.sh | bash
source ~/.bashrc
nvm install 22 && nvm alias default 22 && nvm use 22
```

### 4. Artefatos CLI

```bash
npm i -g @anthropic-ai/claude-code   # TRIFORCE
npm i -g opencode-ai                 # MASTERSWORD
# MAJORA (Codex) — instalar separadamente se necessário
```

Versões validadas em **2026-05-06**:
- Claude Code: `2.1.131` via npm global (nvm)
- OpenCode: `1.14.39`
- Node: `v22.22.2`

### 5. Clonar e configurar

```bash
git clone https://github.com/Joshmaster/Mineru-s-Construct.git ~/Agents
cd ~/Agents

export DISCORD_TOKEN="..."
export OPENROUTER_KEY_1="..."
export OPENROUTER_KEY_2="..."
export OPENROUTER_KEY_3="..."
export CEREBRAS_KEY_1="..."
export CEREBRAS_KEY_2="..."
export CEREBRAS_KEY_3="..."
export MISTRAL_KEY_1="..."
export MISTRAL_KEY_2="..."
export MISTRAL_KEY_3="..."
export WA_OWNER="5537..."
export WA_ALLOW_FROM="5537...,5537..."

bash setup.sh   # gera hyrule_env.py + instala dependências Python
```

### 6. Subir

```bash
python3 startup_services.py start
python3 startup_services.py status
```

Status esperado:

```
Hyrule Proxy    : rodando
Discord bot     : online
Supervisor      : rodando
WhatsApp bot    : rodando
Triforce        : rodando
Majora          : rodando
Mastersword     : rodando
```

---

## ✦ Systemd — Autostart

```ini
[Unit]
Description=Hyrule Bot System
Wants=network-online.target ollama.service
After=network-online.target ollama.service

[Service]
Type=oneshot
User=SEU_USUARIO
WorkingDirectory=/home/SEU_USUARIO/Agents
ExecStart=/usr/bin/python3 /home/SEU_USUARIO/Agents/startup_services.py start
ExecReload=/usr/bin/python3 /home/SEU_USUARIO/Agents/startup_services.py restart-nolimp
ExecStop=/usr/bin/python3 /home/SEU_USUARIO/Agents/startup_services.py stop
RemainAfterExit=yes
TimeoutStartSec=120
TimeoutStopSec=60

[Install]
WantedBy=multi-user.target
```

```bash
sudo tee /etc/systemd/system/hyrule.service > /dev/null <<'EOF'
# cole o bloco acima
EOF
sudo systemctl daemon-reload
sudo systemctl enable hyrule
sudo systemctl start hyrule
```

---

## ✦ Healthcheck

```bash
python3 check_llms.py
python3 check_discord_logs.py
python3 check_claude_queue.py
curl http://localhost:7331/status
curl http://localhost:7332/status
curl http://localhost:8765/v1/models
curl http://localhost:11434/api/tags
opencode --version && opencode debug config
```

---

## ✦ Pedras Proibidas — O que não vai para o git

```
hyrule_env.py
.claude/.credentials.json
claude_queue.json  /  codex_queue.json  /  mastersword_queue.json
.majora_processing.lock  /  .mastersword_processing.lock
link-bot/.linkbot/          ← sessão WhatsApp
triforce_history/
logs e pids de runtime
```

Se um segredo aparecer no histórico do git: **revogue e gere outro imediatamente.**

---

## ✦ Pergaminhos de Diagnóstico

| Problema                        | Ação                                                         |
|---------------------------------|--------------------------------------------------------------|
| Discord offline                 | Verificar `DISCORD_TOKEN`, intents e `curl localhost:7331/status` |
| WhatsApp pede QR                | Restaurar `link-bot/.linkbot/session.sqlite` ou parear novamente |
| Ollama sem modelo               | `ollama pull qwen2.5:7b`                                    |
| Proxy fora                      | `startup_services.py restart-nolimp` + `proxy_runtime.log`  |
| TRIFORCE 401                    | Abrir `claude` interativo e renovar login OAuth              |
| MAJORA duplicando               | Conferir `.majora_processing.lock` e `majora.log`           |
| MASTERSWORD falha               | `opencode --version`, `opencode debug config`, `mastersword.log` |
| Claude auto-update falha        | `claude doctor`, depois `npm i -g @anthropic-ai/claude-code` |
| Provider cloud 429              | Normal — o sistema rotaciona chaves automaticamente          |

---

```
 ╔══════════════════════════════════════════════════════════════════╗
 ║  "O tempo não destrói o que foi construído com propósito."      ║
 ║                                          — Mineru               ║
 ╚══════════════════════════════════════════════════════════════════╝
```
