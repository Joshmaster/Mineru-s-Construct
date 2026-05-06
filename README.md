# Mineru's Construct - Sistema Hyrule

Sistema pessoal do OWNER: bot Discord (Link), bot WhatsApp, supervisor de LLMs,
Hyrule Proxy, TRIFORCE daemon, MAJORA watcher e MASTERSWORD watcher.

O runtime atual fica em `~/Agents` num Ubuntu Server. As credenciais reais ficam
fora do git em `hyrule_env.py`, gerado por `setup.sh`.

Repo: https://github.com/OWNERmaster/Mineru-s-Construct

## Retomar pelo SSH

```bash
cd ~/Agents && claude
```

Isso carrega:

- `CLAUDE.md` e `AGENTS.md`: identidade Link e regras de trabalho
- `.claude/memory/`: memoria do projeto e handoff da sessao anterior
- `.claude/settings.local.json`: permissoes locais

Atalho opcional:

```bash
echo "alias hyrule='cd ~/Agents && claude'" >> ~/.bashrc
source ~/.bashrc
```

## Arquitetura

```text
~/Agents/
├── startup_services.py        # start/stop/restart/status de todos os servicos
├── bot_supervisor.py          # supervisor Discord + tool calling + fallback LLM
├── triforce_daemon.py         # claude_queue.json -> claude --print --continue
├── watch_codex_queue.py       # codex_queue.json -> codex exec
├── watch_mastersword_queue.py # mastersword_queue.json -> opencode run
├── watch_discord_queue.py     # watcher asyncRewake para sessoes interativas
├── check_llms.py              # healthcheck de Discord, proxy, Ollama e LLMs
├── setup.sh                   # gera hyrule_env.py a partir de env vars
├── hyrule_env.example.py      # template sem segredos
├── hyrule_env.py              # credenciais locais, ignorado pelo git
│
├── DISCORD/
│   └── link_discord.py        # bot Discord + HTTP API :7331
│
├── link-bot/
│   ├── bot/main.py            # bot WhatsApp + HTTP API :7332
│   └── config/config.json     # owner/allow list do WhatsApp
│
└── CLAUDE CODE/
    └── proxy.py               # Hyrule Proxy :8765
```

## Fluxo de custo

O supervisor sempre tenta a camada mais barata primeiro:

```text
1. OpenRouter gpt-oss/free models
2. Groq llama/kimi
3. Ollama qwen2.5:7b local
4. TRIFORCE/MAJORA/MASTERSWORD apenas quando escalado
```

O TRIFORCE nao mascara erro do Claude com outro LLM. Se `claude --continue`
falhar, ele retorna erro visivel para corrigir a causa original.

## Servicos e portas

| Servico | Porta/arquivo |
|---|---|
| Discord HTTP API | `localhost:7331` |
| WhatsApp HTTP API | `localhost:7332` |
| Hyrule Proxy | `localhost:8765` |
| Ollama | `localhost:11434` |
| TRIFORCE queue | `claude_queue.json` |
| MAJORA queue | `codex_queue.json` |
| MAJORA lock | `.majora_processing.lock` |
| MASTERSWORD queue | `mastersword_queue.json` |
| MASTERSWORD lock | `.mastersword_processing.lock` |
| MASTERSWORD persona/config | `OPENCODE/roaming/MASTERSWORD_INSTRUCTIONS.md` + `OPENCODE/roaming/LINK_PERSONA.md` |

## Instalacao curta

Veja o passo a passo completo em [SETUP.md](SETUP.md).

MASTERSWORD/OpenCode carrega a persona e a retomada operacional por
`OPENCODE/roaming/MASTERSWORD_INSTRUCTIONS.md` e
`OPENCODE/roaming/LINK_PERSONA.md`.

Resumo:

```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y python3 python3-pip python3-venv git curl wget procps xdg-utils

curl -fsSL https://ollama.com/install.sh | sh
sudo systemctl enable --now ollama
ollama pull qwen2.5:7b

curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.39.7/install.sh | bash
source ~/.bashrc
nvm install 22
nvm use 22
npm i -g @anthropic-ai/claude-code
npm i -g opencode-ai
claude --version
opencode --version

git clone https://github.com/OWNERmaster/Mineru-s-Construct.git ~/Agents
cd ~/Agents

export DISCORD_TOKEN="..."
export OPENROUTER_KEY_1="..."
export OPENROUTER_KEY_2="..."
export OPENROUTER_KEY_3="..."
export GROQ_KEY_1="..."
export GROQ_KEY_2="..."
export GROQ_KEY_3="..."
export WA_OWNER="5537..."
export WA_ALLOW_FROM="5537...,5537..."
bash setup.sh

python3 startup_services.py start
python3 startup_services.py status
```

## Claude Code CLI

Configuracao validada no servidor em 2026-05-06:

```text
Install method: npm global via nvm
Node: v22.22.2
Claude Code: 2.1.131
Auto-updates: enabled
Update permissions: Yes
Auto-update channel: latest
```

Comandos uteis:

```bash
claude --version
claude update
claude doctor
```

## Operacao

```bash
python3 ~/Agents/startup_services.py status
python3 ~/Agents/startup_services.py start
python3 ~/Agents/startup_services.py restart
python3 ~/Agents/startup_services.py restart-nolimp
python3 ~/Agents/startup_services.py stop
```

Logs principais:

```bash
tail -f ~/Agents/DISCORD/supervisor_out.log
tail -f ~/Agents/DISCORD/bot_error.log
tail -f ~/Agents/link-bot/.linkbot/whatsapp_err.log
tail -f ~/Agents/triforce_daemon.log
tail -f ~/Agents/majora.log
tail -f ~/Agents/mastersword.log
tail -f ~/Agents/CLAUDE\ CODE/proxy_runtime.log
```

## Systemd

O servico recomendado chama `startup_services.py`, que sobe proxy, Discord,
supervisor, WhatsApp, TRIFORCE, MAJORA e MASTERSWORD.

```ini
[Unit]
Description=Hyrule Bot System
Wants=network-online.target ollama.service
After=network-online.target ollama.service

[Service]
Type=oneshot
User=OWNER_USER
WorkingDirectory=~/Agents
ExecStart=/usr/bin/python3 ~/Agents/startup_services.py start
ExecReload=/usr/bin/python3 ~/Agents/startup_services.py restart-nolimp
ExecStop=/usr/bin/python3 ~/Agents/startup_services.py stop
RemainAfterExit=yes
TimeoutStartSec=120
TimeoutStopSec=60

[Install]
WantedBy=multi-user.target
```

## Seguranca

Nao commitar:

- `hyrule_env.py`
- `.claude/.credentials.json`
- tokens OAuth, OpenRouter, Groq, Discord ou GitHub
- sessoes WhatsApp em `link-bot/.linkbot/`
- filas e locks de runtime

Se algum segredo aparecer no git, revogue e gere outro.

## Troubleshooting

| Problema | Acao |
|---|---|
| Discord offline | Ver `DISCORD_TOKEN`, intents do bot e `curl localhost:7331/status` |
| WhatsApp pede QR | Parear de novo ou restaurar `link-bot/.linkbot/session.sqlite` |
| Ollama sem modelo | `ollama pull qwen2.5:7b` |
| Proxy fora | `python3 startup_services.py restart-nolimp` e log `proxy_runtime.log` |
| Claude auto-update falha | `claude doctor`, depois `npm i -g @anthropic-ai/claude-code` |
| TRIFORCE 401 | Rodar `claude` interativo e renovar OAuth |
| MAJORA duplicando | Conferir `.majora_processing.lock` e `majora.log` |
| MASTERSWORD falha | `opencode --version`, `opencode debug config`, conferir `mastersword.log` |
