# Hyrule — Guia de Instalação (Ubuntu Server 24.04 LTS)

Sistema de bots e automação pessoal: bot Discord (Link), bot WhatsApp, supervisor de LLMs, Triforce daemon e proxy para Claude Code.

> Funciona também no Windows — veja a seção [Windows](#windows-referência-rápida) no final.

---

## Arquitetura

```
~/Agents/
├── startup_services.py       ← gerencia todos os serviços (start/stop/restart/status)
├── bot_supervisor.py         ← supervisor Discord + roteamento de LLMs
├── triforce_daemon.py        ← fila de pedidos via Discord/WhatsApp → Claude Code
├── link_console.py           ← console interativo local
├── hyrule_env.py             ← CREDENCIAIS (não vai pro git — copie do .example)
├── hyrule_env.example.py     ← template de credenciais
│
├── DISCORD/
│   └── link_discord.py       ← bot Discord (HTTP API porta 7331)
│
├── link-bot/                 ← bot WhatsApp (HTTP API porta 7332)
│   ├── bot/main.py
│   ├── bot/core/             ← llm, router, storage, scheduler
│   ├── bot/skills/           ← clima, cep, cotacao, lembretes, etc.
│   └── config/config.json    ← número dono + allow list
│
└── CLAUDE CODE/
    └── global/proxy.py       ← proxy (Claude Code → Ollama/OpenRouter)
```

### Hierarquia de LLMs (custo crescente)

```
OpenRouter (free)  →  Groq (free)  →  Ollama local  →  Claude Code (sessão)
```

---

## 1. Atualizar sistema e instalar dependências base

```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y python3 python3-pip python3-venv git curl wget \
                    libgomp1 ffmpeg xdg-utils
```

---

## 2. Instalar Ollama

```bash
curl -fsSL https://ollama.com/install.sh | sh

# Habilitar como serviço systemd
sudo systemctl enable ollama
sudo systemctl start ollama

# Baixar modelo local
ollama pull qwen2.5:1.5b

# Verificar
ollama list
```

---

## 3. Instalar Claude Code CLI

```bash
# Via npm (requer Node.js)
curl -fsSL https://deb.nodesource.com/setup_22.x | sudo -E bash -
sudo apt install -y nodejs
sudo npm install -g @anthropic-ai/claude-code

# Verificar
claude --version
```

---

## 4. Clonar o repositório

```bash
git clone https://github.com/OWNERmaster/Mineru-s-Construct.git ~/Agents
cd ~/Agents
```

---

## 5. Instalar dependências Python

```bash
pip3 install discord.py aiohttp requests flask neonize qrcode httpx segno
```

---

## 6. Configurar credenciais

```bash
cp ~/Agents/hyrule_env.example.py ~/Agents/hyrule_env.py
nano ~/Agents/hyrule_env.py
```

Preencha:

| Campo | Onde obter |
|---|---|
| `DISCORD_TOKEN` | discord.com/developers → Bot → Reset Token |
| `OPENROUTER_KEYS` | openrouter.ai/keys (free tier) |
| `GROQ_KEYS` | console.groq.com/keys (free tier) |
| `WA_OWNER` | Seu número com DDI sem + (ex: `5537999990000`) |
| `WA_ALLOW_FROM` | Lista de números autorizados |

---

## 7. Configurar bot Discord

Em `DISCORD/link_discord.py`, confirme os IDs dos usuários:
```python
USUARIOS = {
    "OWNER": SEU_DISCORD_USER_ID,
    "USER2": DISCORD_USER_ID_2,
}
```

No Discord Developer Portal:
1. Ative **Message Content Intent**, **Server Members Intent**, **Presence Intent**
2. Invite: `https://discord.com/api/oauth2/authorize?client_id=SEU_CLIENT_ID&permissions=8&scope=bot`

---

## 8. Configurar bot WhatsApp

Edite `link-bot/config/config.json`:
```json
{
  "MODE": "TOTK + LLM fallback",
  "OWNER": "SEU_NUMERO_COM_DDI",
  "ALLOW_FROM": ["SEU_NUMERO_COM_DDI"],
  "STORAGE_PATH": ".linkbot/data.db",
  "SESSION_PATH": ".linkbot/session.sqlite",
  "ENABLE_PC_CONTROL": true
}
```

### Primeiro pareamento (gera QR)

```bash
cd ~/Agents/link-bot
python3 -m bot.main
```

O QR é salvo em `.linkbot/qr.png`. Para visualizar via SSH:
```bash
# Opção 1 — copiar para sua máquina
scp usuario@servidor:~/Agents/link-bot/.linkbot/qr.png ~/Desktop/

# Opção 2 — ver no terminal (ASCII)
# O bot já tenta exibir automaticamente via segno
```

Escaneie com WhatsApp → **Configurações → Dispositivos conectados → Conectar dispositivo**.  
Após parear, pare com `Ctrl+C` — sessão salva em `.linkbot/session.sqlite`.

---

## 9. Iniciar todos os serviços

```bash
cd ~/Agents
python3 startup_services.py start
```

Comandos disponíveis:
```bash
python3 startup_services.py status      # ver estado de cada serviço
python3 startup_services.py restart     # parar tudo + limpar histórico + reiniciar
python3 startup_services.py stop        # parar tudo
python3 startup_services.py restart-nolimp  # reiniciar sem limpar histórico
```

---

## 10. Autostart com systemd

Crie o serviço:
```bash
sudo nano /etc/systemd/system/hyrule.service
```

Conteúdo (ajuste o usuário):
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

Ativar:
```bash
sudo systemctl daemon-reload
sudo systemctl enable hyrule
sudo systemctl start hyrule
sudo systemctl status hyrule
```

---

## 11. Logs em tempo real

```bash
# Supervisor
tail -f ~/Agents/DISCORD/supervisor_out.log

# Bot Discord
tail -f ~/Agents/DISCORD/bot_error.log

# Bot WhatsApp
tail -f ~/Agents/link-bot/.linkbot/whatsapp_err.log

# Triforce daemon
tail -f ~/Agents/triforce_daemon.log
```

---

## Portas utilizadas

| Serviço | Porta |
|---|---|
| Discord bot HTTP API | 7331 |
| WhatsApp bot HTTP API | 7332 |
| Hyrule Proxy | 8765 |
| Ollama | 11434 |

---

## Migrar sessão WhatsApp do servidor antigo

Para não precisar escanear o QR novamente:
```bash
# No servidor antigo
scp ~/Agents/link-bot/.linkbot/session.sqlite usuario@novo_servidor:~/Agents/link-bot/.linkbot/
```

---

## Verificação rápida

```bash
python3 ~/Agents/startup_services.py status

curl http://localhost:7331/status
curl http://localhost:11434/api/tags

# Processos rodando
ps aux | grep python3 | grep -v grep
```

---

## Problemas comuns

**Bot Discord não conecta**
- Verifique o token em `hyrule_env.py`
- Confirme que os Intents estão ativados no Developer Portal

**WhatsApp pede QR toda vez**
- `session.sqlite` foi perdido — re-execute e escaneie o QR
- Se migrou de servidor, verifique se copiou o arquivo corretamente

**Ollama não responde**
- `sudo systemctl restart ollama` e `ollama list`
- Confirme que `qwen2.5:1.5b` está baixado

**Groq/OpenRouter retornam 429**
- Rate limit — o supervisor rotaciona automaticamente entre as 3 chaves
- Aguarde ou adicione mais chaves em `hyrule_env.py`

**`pgrep` não encontrado**
- `sudo apt install -y procps`

---

## Windows — referência rápida

O código é cross-platform. No Windows:

```powershell
# Instalar Ollama
# Baixe em https://ollama.com/download/windows

# Dependências
pip install discord.py aiohttp requests flask neonize qrcode httpx segno

# Iniciar
python startup_services.py start
```

Autostart: Task Scheduler → gatilho "Ao fazer logon" → `python C:\Users\SEU_USUARIO\Agents\startup_services.py start`
