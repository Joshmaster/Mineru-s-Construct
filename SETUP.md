# Hyrule - Guia de Instalacao Atual

Alvo principal: Ubuntu Server 24.04 LTS em `~/Agents`.

Este guia instala o estado atual do projeto: Discord Link, WhatsApp Link,
supervisor, Hyrule Proxy, TRIFORCE daemon, MAJORA watcher, Ollama local e
Claude Code via npm global do nvm.

## 1. Pacotes base

```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y python3 python3-pip python3-venv git curl wget procps xdg-utils libgomp1 ffmpeg
```

## 2. Ollama

```bash
curl -fsSL https://ollama.com/install.sh | sh
sudo systemctl enable --now ollama
ollama pull qwen2.5:7b
ollama list
curl http://localhost:11434/api/tags
```

## 3. Node via nvm

O servidor atual usa nvm, evitando `sudo npm -g`.

```bash
curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.39.7/install.sh | bash
source ~/.bashrc
nvm install 22
nvm alias default 22
nvm use 22
node -v
npm -v
```

## 4. Claude Code CLI

```bash
npm i -g @anthropic-ai/claude-code
which claude
claude --version
claude update
```

Estado esperado validado em 2026-05-06:

```text
Currently running: npm-global
Auto-updates: enabled
Update permissions: Yes
Auto-update channel: latest
```

Se o auto-update falhar:

```bash
claude doctor
npm i -g @anthropic-ai/claude-code
claude update
```

## 5. Clonar repo

```bash
git clone https://github.com/OWNERmaster/Mineru-s-Construct.git ~/Agents
cd ~/Agents
```

## 6. Credenciais

Credenciais reais nao entram no git. Gere `hyrule_env.py` com env vars:

```bash
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
```

`setup.sh` tambem instala:

```text
discord.py aiohttp requests flask neonize qrcode httpx segno
```

Para instalar deps sem regenerar credenciais:

```bash
pip3 install discord.py aiohttp requests flask neonize qrcode httpx segno
```

## 7. Discord

No Discord Developer Portal:

1. Ative `Message Content Intent`.
2. Ative `Server Members Intent`.
3. Ative `Presence Intent`.
4. Convide o bot com permissao adequada para DM/servidor.

Validar API local depois do start:

```bash
curl http://localhost:7331/status
```

## 8. WhatsApp

Editar:

```bash
nano ~/Agents/link-bot/config/config.json
```

Campos importantes:

```json
{
  "OWNER": "5537...",
  "ALLOW_FROM": ["5537..."],
  "STORAGE_PATH": ".linkbot/data.db",
  "SESSION_PATH": ".linkbot/session.sqlite"
}
```

Primeiro pareamento:

```bash
cd ~/Agents/link-bot
python3 -m bot.main
```

O QR fica em:

```text
~/Agents/link-bot/.linkbot/qr.png
```

Copiar via SSH se precisar:

```bash
scp usuario@servidor:~/Agents/link-bot/.linkbot/qr.png ~/Desktop/
```

Para migrar sem novo QR, copie:

```text
~/Agents/link-bot/.linkbot/session.sqlite
```

## 9. Subir servicos

```bash
cd ~/Agents
python3 startup_services.py start
python3 startup_services.py status
```

Status esperado:

```text
Hyrule Proxy: rodando
Discord bot: online
Supervisor: rodando
WhatsApp bot: rodando
Triforce: rodando
Majora: rodando
```

Comandos:

```bash
python3 startup_services.py start
python3 startup_services.py status
python3 startup_services.py restart
python3 startup_services.py restart-nolimp
python3 startup_services.py stop
```

`restart` limpa historico e memoria operacional. `restart-nolimp` preserva.

## 10. Systemd

Criar `/etc/systemd/system/hyrule.service`:

```bash
sudo tee /etc/systemd/system/hyrule.service > /dev/null <<'EOF'
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
EOF

sudo systemctl daemon-reload
sudo systemctl enable hyrule
sudo systemctl start hyrule
sudo systemctl status hyrule
```

## 11. Filas e escalonamento

TRIFORCE:

- Entrada: `claude_queue.json`
- Executor daemon: `triforce_daemon.py`
- Comando: `claude --print --continue --dangerously-skip-permissions`
- Canais: Discord e WhatsApp
- Sem fallback LLM: falha do Claude aparece explicitamente
- Alerta token OAuth quando restam menos de 120 min

MAJORA:

- Entrada: `codex_queue.json`
- Executor: `watch_codex_queue.py`
- Comando: `codex exec`
- Lock: `.majora_processing.lock`
- Lock stale: 15 min
- Canais: Discord e WhatsApp

Watcher interativo:

- `watch_discord_queue.py` usa `asyncRewake` para acordar sessoes interativas
- Respeita campo `canal`; WhatsApp responde em `localhost:7332`

## 12. Healthcheck

```bash
python3 check_llms.py
python3 check_discord_logs.py
python3 check_claude_queue.py
curl http://localhost:7331/status
curl http://localhost:7332/status
curl http://localhost:8765/v1/models
curl http://localhost:11434/api/tags
```

`check_llms.py` le `OPENROUTER_KEYS` e `GROQ_KEYS` de `hyrule_env.py`.

## 13. Logs

```bash
tail -f ~/Agents/DISCORD/supervisor_out.log
tail -f ~/Agents/DISCORD/bot_error.log
tail -f ~/Agents/DISCORD/discord.log
tail -f ~/Agents/link-bot/.linkbot/whatsapp.log
tail -f ~/Agents/link-bot/.linkbot/whatsapp_err.log
tail -f ~/Agents/triforce_daemon.log
tail -f ~/Agents/majora.log
tail -f ~/Agents/CLAUDE\ CODE/proxy_runtime.log
```

## 14. Arquivos que nao vao para o git

- `hyrule_env.py`
- `.claude/.credentials.json`
- `claude_queue.json`
- `codex_queue.json`
- `.majora_processing.lock`
- `link-bot/.linkbot/`
- logs, pids e historicos de conversa

## 15. Problemas comuns

| Problema | Solucao |
|---|---|
| `claude` nao encontrado | `source ~/.bashrc`, `nvm use 22`, `npm i -g @anthropic-ai/claude-code` |
| Auto-update falhou | `claude doctor`, `claude update`, `npm i -g @anthropic-ai/claude-code` |
| TRIFORCE 401 | Abrir `claude` interativo e renovar login OAuth |
| WhatsApp pede QR | Restaurar `session.sqlite` ou parear novamente |
| Discord offline | Conferir token e intents no Developer Portal |
| OpenRouter/Groq 429 | Rate limit; supervisor rotaciona chaves automaticamente |
| MAJORA processando duas vezes | Ver `majora.log` e remover lock stale se necessario |

## Windows - referencia curta

O projeto roda melhor no Ubuntu. Para Windows:

```powershell
pip install discord.py aiohttp requests flask neonize qrcode httpx segno
python startup_services.py start
```

Use o Agendador de Tarefas para autostart, apontando para:

```text
python C:\Users\SEU_USUARIO\Agents\startup_services.py start
```
