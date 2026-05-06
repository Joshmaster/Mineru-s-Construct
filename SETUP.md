# Hyrule - Guia de Instalacao Atual

Alvo principal: Ubuntu Server 24.04 LTS em `~/Agents`.

Este guia instala o estado atual do projeto: Discord Link, WhatsApp Link,
supervisor, Hyrule Proxy, TRIFORCE daemon, MAJORA watcher, MASTERSWORD watcher,
Ollama local, Claude Code e OpenCode via npm global do nvm.

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

## 5. OpenCode CLI (MASTERSWORD)

```bash
npm i -g opencode-ai
which opencode
opencode --version
```

O MASTERSWORD usa OpenCode com modelos baratos/gratis/locais:

```text
openrouter/openai/gpt-oss-20b:free
openrouter/google/gemma-4-31b-it:free
openrouter/nvidia/nemotron-3-super-120b-a12b:free
ollama/qwen2.5:7b
```

Config ativa:

```text
~/.config/opencode/opencode.json
~/Agents/OPENCODE/mastersword.opencode.json
```

Instrucoes carregadas pelo MASTERSWORD:

```text
~/Agents/OPENCODE/roaming/MASTERSWORD_INSTRUCTIONS.md
~/Agents/OPENCODE/roaming/LINK_PERSONA.md
```

O watcher garante essas instrucoes na config local existente ao iniciar.
`opencode link` e `mastersword link` seguem a mesma rotina de retomada de contexto
de `link link`, `claude link` e `codex link`.

## 6. Clonar repo

```bash
git clone https://github.com/OWNERmaster/Mineru-s-Construct.git ~/Agents
cd ~/Agents
```

## 7. Credenciais

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

### Como obter cada credencial

**DISCORD_TOKEN**
1. Acesse [discord.com/developers/applications](https://discord.com/developers/applications)
2. Crie um novo Application → clique em **Bot** → **Reset Token** → copie o token
3. Em **Privileged Gateway Intents**: ative `Message Content`, `Server Members` e `Presence`
4. Convide o bot com o link OAuth2 gerado na aba **OAuth2**

**OPENROUTER_KEY** (gratuito, varios modelos free tier)
1. Crie conta em [openrouter.ai](https://openrouter.ai)
2. Va em **Keys** → **Create Key** → copie
3. Basta uma chave; OPENROUTER_KEY_2 e _3 sao opcionais para rotacao

**GROQ_KEY** (gratuito, alta velocidade)
1. Crie conta em [console.groq.com](https://console.groq.com)
2. Va em **API Keys** → **Create API Key** → copie
3. Mesma logica: uma chave basta, as extras sao para rotacao

**WA_OWNER e WA_ALLOW_FROM** (numeros WhatsApp)
- Formato: `55` + DDD + numero, sem `+`, espacos ou traco
- Exemplo: numero `OWNER_PHONE` → `55XXXXXXXXXXX`
- `WA_OWNER` = seu numero (administrador do bot)
- `WA_ALLOW_FROM` = numeros que podem interagir com o bot, separados por virgula

**IDs Discord de usuarios** (opcional, para DMs pelo bot)
1. No Discord: Configuracoes → Avancado → **Modo desenvolvedor** ON
2. Clique com botao direito em qualquer usuario → **Copiar ID**
3. Adicione em `DISCORD/link_discord.py` no dict `USUARIOS`

`setup.sh` tambem instala:

```text
discord.py aiohttp requests flask neonize qrcode httpx segno
```

Para instalar deps sem regenerar credenciais:

```bash
pip3 install discord.py aiohttp requests flask neonize qrcode httpx segno
```

## 8. Discord

No Discord Developer Portal:

1. Ative `Message Content Intent`.
2. Ative `Server Members Intent`.
3. Ative `Presence Intent`.
4. Convide o bot com permissao adequada para DM/servidor.

Validar API local depois do start:

```bash
curl http://localhost:7331/status
```

## 9. WhatsApp

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

## 10. Subir servicos

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
Mastersword: rodando
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

## 11. Systemd

Criar `/etc/systemd/system/hyrule.service`:

```bash
sudo tee /etc/systemd/system/hyrule.service > /dev/null <<'EOF'
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
EOF

sudo systemctl daemon-reload
sudo systemctl enable hyrule
sudo systemctl start hyrule
sudo systemctl status hyrule
```

## 12. Filas e escalonamento

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

MASTERSWORD:

- Entrada: `mastersword_queue.json`
- Executor: `watch_mastersword_queue.py`
- Comando: `opencode run`
- Modelos: OpenRouter free -> Ollama local; Groq fica configurado para uso user2al
- Persona/config: `OPENCODE/roaming/MASTERSWORD_INSTRUCTIONS.md` + `OPENCODE/roaming/LINK_PERSONA.md`
- Lock: `.mastersword_processing.lock`
- Lock stale: 15 min
- Canais: Discord e WhatsApp

Watcher interativo:

- `watch_discord_queue.py` usa `asyncRewake` para acordar sessoes interativas
- Respeita campo `canal`; WhatsApp responde em `localhost:7332`

## 13. Healthcheck

```bash
python3 check_llms.py
python3 check_discord_logs.py
python3 check_claude_queue.py
curl http://localhost:7331/status
curl http://localhost:7332/status
curl http://localhost:8765/v1/models
curl http://localhost:11434/api/tags
opencode --version
opencode debug config
```

`check_llms.py` le `OPENROUTER_KEYS` e `GROQ_KEYS` de `hyrule_env.py`.

## 14. Logs

```bash
tail -f ~/Agents/DISCORD/supervisor_out.log
tail -f ~/Agents/DISCORD/bot_error.log
tail -f ~/Agents/DISCORD/discord.log
tail -f ~/Agents/link-bot/.linkbot/whatsapp.log
tail -f ~/Agents/link-bot/.linkbot/whatsapp_err.log
tail -f ~/Agents/triforce_daemon.log
tail -f ~/Agents/majora.log
tail -f ~/Agents/mastersword.log
tail -f ~/Agents/CLAUDE\ CODE/proxy_runtime.log
```

## 15. Arquivos que nao vao para o git

- `hyrule_env.py`
- `.claude/.credentials.json`
- `claude_queue.json`
- `codex_queue.json`
- `mastersword_queue.json`
- `.majora_processing.lock`
- `.mastersword_processing.lock`
- `link-bot/.linkbot/`
- logs, pids e historicos de conversa

## 16. Problemas comuns

| Problema | Solucao |
|---|---|
| `claude` nao encontrado | `source ~/.bashrc`, `nvm use 22`, `npm i -g @anthropic-ai/claude-code` |
| Auto-update falhou | `claude doctor`, `claude update`, `npm i -g @anthropic-ai/claude-code` |
| TRIFORCE 401 | Abrir `claude` interativo e renovar login OAuth |
| WhatsApp pede QR | Restaurar `session.sqlite` ou parear novamente |
| Discord offline | Conferir token e intents no Developer Portal |
| OpenRouter/Groq 429 | Rate limit; supervisor rotaciona chaves automaticamente |
| MAJORA processando duas vezes | Ver `majora.log` e remover lock stale se necessario |
| MASTERSWORD falha | `opencode --version`, `opencode debug config`, ver `mastersword.log` |

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
