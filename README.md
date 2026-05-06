# Mineru's Construct — Sistema Hyrule

Bot Discord (Link) + Bot WhatsApp integrados a um supervisor de LLMs com hierarquia de fallback automático: OpenRouter → Groq → Ollama local. Inclui daemon Triforce para fila de pedidos via Discord/WhatsApp e gerenciador de serviços unificado.

**Dono:** OWNER (`OWNER_EMAIL`)  

---

## Início rápido — SSH → Claude Code

Após conectar via SSH, execute:

```bash
cd ~/Agents && claude
```

Isso carrega automaticamente:
- `CLAUDE.md` — identidade, regras e hierarquia de LLMs
- `.claude/memory/` — arquitetura do Hyrule, rotinas, feedbacks
- `.claude/settings.local.json` — permissões

O Claude Code acorda com contexto completo do projeto. Se quiser retomar o estado da sessão anterior, diga **"claude link"**.

Para adicionar o atalho permanente no shell:

```bash
echo "alias hyrule='cd ~/Agents && claude'" >> ~/.bashrc && source ~/.bashrc
```

Depois é só digitar `hyrule` para abrir.

---
**Servidor alvo:** Ubuntu Server 24.04 LTS  
**Repo:** https://github.com/OWNERmaster/Mineru-s-Construct

---

## Para Claude Code — instalação no Ubuntu

> Se você está lendo isto numa sessão nova, siga os passos abaixo na ordem.

### Pré-requisitos que devem estar instalados antes de começar

```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y python3 python3-pip git curl wget procps xdg-utils
```

### 1. Instalar Ollama e baixar modelo local

```bash
curl -fsSL https://ollama.com/install.sh | sh
sudo systemctl enable ollama && sudo systemctl start ollama
ollama pull qwen2.5:1.5b
ollama list  # deve mostrar qwen2.5:1.5b
```

### 2. Instalar Claude Code CLI

```bash
curl -fsSL https://deb.nodesource.com/setup_22.x | sudo -E bash -
sudo apt install -y nodejs
sudo npm install -g @anthropic-ai/claude-code
claude --version
```

### 3. Clonar o repositório

```bash
git clone https://github.com/OWNERmaster/Mineru-s-Construct.git ~/Agents
cd ~/Agents
```

### 4. Instalar dependências Python

```bash
pip3 install discord.py aiohttp requests flask neonize qrcode httpx segno
```

### 5. Gerar hyrule_env.py com as credenciais

As credenciais estão salvas como **GitHub Secrets** no repositório.  
OWNER deve exportá-las e rodar o script:

```bash
# OWNER exporta as variáveis (vindas dos GitHub Secrets ou do arquivo salvo)
export DISCORD_TOKEN="..."
export OPENROUTER_KEY_1="..." OPENROUTER_KEY_2="..." OPENROUTER_KEY_3="..."
export GROQ_KEY_1="..."       GROQ_KEY_2="..."       GROQ_KEY_3="..."
export WA_OWNER="..."         WA_ALLOW_FROM="NUMERO1,NUMERO2"

# Gera hyrule_env.py + instala deps
bash ~/Agents/setup.sh
```

### 6. Configurar bot WhatsApp — editar config.json

```bash
nano ~/Agents/link-bot/config/config.json
```

Preencher `OWNER` e `ALLOW_FROM` com os números do OWNER (com DDI, sem +).  
`SESSION_PATH` e `STORAGE_PATH` já estão como caminhos relativos — não mudar.

### 7. Parear WhatsApp (primeira vez)

```bash
cd ~/Agents/link-bot
python3 -m bot.main
```

QR salvo em `.linkbot/qr.png`. Para ver via SSH:
```bash
scp usuario@servidor:~/Agents/link-bot/.linkbot/qr.png ~/Desktop/
```

Após parear: `Ctrl+C`. Sessão salva em `.linkbot/session.sqlite`.

> **Se migrando de outro servidor:** copiar o `session.sqlite` evita o re-pareamento:
> ```bash
> scp servidor_antigo:~/Agents/link-bot/.linkbot/session.sqlite ~/Agents/link-bot/.linkbot/
> ```

### 8. Iniciar todos os serviços

```bash
cd ~/Agents
python3 startup_services.py start
python3 startup_services.py status
```

### 9. Configurar autostart com systemd

```bash
sudo tee /etc/systemd/system/hyrule.service > /dev/null <<EOF
[Unit]
Description=Hyrule Bot System
Wants=network-online.target ollama.service
After=network-online.target ollama.service

[Service]
Type=oneshot
User=$USER
WorkingDirectory=$HOME/Agents
ExecStart=/usr/bin/python3 $HOME/Agents/startup_services.py start
ExecReload=/usr/bin/python3 $HOME/Agents/startup_services.py restart-nolimp
ExecStop=/usr/bin/python3 $HOME/Agents/startup_services.py stop
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

---

## Arquitetura

```
~/Agents/
├── startup_services.py       ← start / stop / restart / status
├── bot_supervisor.py         ← supervisor Discord + roteamento LLMs
├── triforce_daemon.py        ← fila de pedidos → Claude Code
├── link_console.py           ← console local
├── hyrule_env.py             ← credenciais (NÃO está no git)
├── hyrule_env.example.py     ← template
├── setup.sh                  ← gera hyrule_env.py a partir de env vars
│
├── DISCORD/
│   └── link_discord.py       ← bot Discord — HTTP API :7331
│
└── link-bot/
    ├── bot/main.py           ← bot WhatsApp — HTTP API :7332
    ├── bot/skills/           ← clima, cep, cotação, lembretes...
    └── config/config.json    ← número dono + allow list
```

### Hierarquia de LLMs

```
OpenRouter (free)  →  Groq (free, 0.3s)  →  Ollama qwen2.5:1.5b (local)  →  Claude Code
```

### Portas

| Serviço | Porta |
|---|---|
| Discord HTTP API | 7331 |
| WhatsApp HTTP API | 7332 |
| Hyrule Proxy (Claude Code) | 8765 |
| Ollama | 11434 |

---

## Comandos do dia a dia

```bash
# Status
python3 ~/Agents/startup_services.py status

# Restart completo (limpa histórico)
python3 ~/Agents/startup_services.py restart

# Logs em tempo real
tail -f ~/Agents/DISCORD/supervisor_out.log
tail -f ~/Agents/link-bot/.linkbot/whatsapp_err.log
tail -f ~/Agents/triforce_daemon.log

# Testar APIs
curl http://localhost:7331/status
curl http://localhost:11434/api/tags
```

---

## Troubleshooting

| Problema | Solução |
|---|---|
| Bot Discord não conecta | Verificar `DISCORD_TOKEN` em `hyrule_env.py` e Intents no Developer Portal |
| WhatsApp pede QR toda vez | `session.sqlite` perdido — re-executar `python3 -m bot.main` |
| Ollama não responde | `sudo systemctl restart ollama` + `ollama list` |
| 429 Groq/OpenRouter | Rate limit — supervisor rotaciona chaves automaticamente |
| `pgrep` não encontrado | `sudo apt install -y procps` |
