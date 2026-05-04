# Hyrule — Guia Completo de Instalação e Restauração

Sistema de bots e automação pessoal: bot Discord (Link), bot WhatsApp, supervisor de LLMs, Triforce daemon e proxy para Claude Code.

---

## Arquitetura Resumida

```
Agents/
├── startup_services.py       ← gerencia todos os serviços (start/stop/restart/status)
├── bot_supervisor.py         ← supervisor Discord + roteamento de LLMs
├── triforce_daemon.py        ← fila de pedidos OWNER ↔ Claude Code via Discord/WhatsApp
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
│   ├── bot/skills/           ← skills: clima, cep, cotacao, lembretes, etc.
│   └── config/config.json    ← configuração WhatsApp (numero dono, allow list)
│
└── CLAUDE CODE/
    └── global/proxy.py       ← proxy Hyrule (intercepta Claude Code → redireciona para Ollama/OpenRouter)
```

### Fluxo de LLMs (hierarquia de custo)

```
OpenRouter (gpt-oss free)   → 1a tentativa
      ↓ falhou (429 / erro)
Groq (llama/kimi)           → 0.3s latência, free tier
      ↓ falhou
Ollama qwen2.5:1.5b         → LOCAL, zero custo, ~7s CPU
      ↓ falhou
Claude Code (sessão ativa)  → último recurso
```

---

## Pré-requisitos

- **Windows 10/11** (ou Linux com pequenas adaptações nos paths)
- **Python 3.12+** → https://www.python.org/downloads/
- **Git** → https://git-scm.com/download/win
- **Ollama** → https://ollama.com/download

---

## 1. Instalar Ollama e baixar modelo local

```powershell
# Instale o Ollama pelo site acima, depois:
ollama pull qwen2.5:1.5b
```

Verifique: `ollama list` deve mostrar `qwen2.5:1.5b`.

---

## 2. Clonar o repositório

```powershell
git clone https://github.com/SEU_USUARIO/hyrule.git "C:\Users\SEU_USUARIO\Agents"
cd "C:\Users\SEU_USUARIO\Agents"
```

---

## 3. Instalar dependências Python

```powershell
# Dependências principais
pip install discord.py aiohttp requests flask

# Bot WhatsApp
pip install neonize qrcode httpx segno

# Verificar instalação
pip list | Select-String "discord|aiohttp|neonize|qrcode|requests|flask"
```

---

## 4. Configurar credenciais

```powershell
copy hyrule_env.example.py hyrule_env.py
notepad hyrule_env.py
```

Preencha no arquivo:

| Variável | Onde obter |
|---|---|
| `DISCORD_TOKEN` | discord.com/developers → Bot → Reset Token |
| `OPENROUTER_KEYS` | openrouter.ai/keys (free tier disponível) |
| `GROQ_KEYS` | console.groq.com/keys (free tier disponível) |
| `WA_OWNER` | Seu número com DDI, sem + (ex: `5537999990000`) |
| `WA_ALLOW_FROM` | Lista de números autorizados |

---

## 5. Configurar bot WhatsApp

Edite `link-bot/config/config.json`:

```json
{
  "MODE": "TOTK + LLM fallback",
  "OWNER": "SEU_NUMERO_COM_DDI",
  "ALLOW_FROM": ["SEU_NUMERO_COM_DDI"],
  "STORAGE_PATH": "C:/Users/SEU_USUARIO/Agents/link-bot/.linkbot/data.db",
  "SESSION_PATH": "C:/Users/SEU_USUARIO/Agents/link-bot/.linkbot/session.sqlite",
  "ENABLE_PC_CONTROL": true
}
```

> Troque `SEU_USUARIO` pelo nome do usuário Windows no novo servidor.

---

## 6. Configurar bot Discord

No Discord Developer Portal:
1. Crie uma aplicação em https://discord.com/developers/applications
2. Vá em Bot → ative **Message Content Intent**, **Server Members Intent**, **Presence Intent**
3. Copie o token para `hyrule_env.py`
4. Invite link: `https://discord.com/api/oauth2/authorize?client_id=SEU_CLIENT_ID&permissions=8&scope=bot`

Em `DISCORD/link_discord.py`, confirme os IDs dos usuários no dict `USUARIOS`:
```python
USUARIOS = {
    "OWNER": SEU_DISCORD_USER_ID,
    "USER2": DISCORD_USER_ID_2,
}
```

---

## 7. Primeiro pareamento WhatsApp

Na primeira execução o bot vai gerar um QR code:

```powershell
cd "C:\Users\SEU_USUARIO\Agents\link-bot"
python -m bot.main
```

Escaneie o QR com o WhatsApp no celular (Configurações → Dispositivos conectados → Conectar dispositivo).

Após parear, pare o processo (`Ctrl+C`) — a sessão fica salva em `.linkbot/session.sqlite`.

---

## 8. Iniciar todos os serviços

```powershell
cd "C:\Users\SEU_USUARIO\Agents"
python startup_services.py start
```

Para verificar status:
```powershell
python startup_services.py status
```

Para reiniciar tudo (limpa histórico):
```powershell
python startup_services.py restart
```

---

## 9. Autostart no boot (opcional — Windows)

Crie um arquivo `link.bat` na pasta `Agents/` (já existe no repo):
```batch
@echo off
cd /d "%~dp0"
python startup_services.py start
```

Adicione ao Task Scheduler para rodar no login:
1. Abra `taskschd.msc`
2. Criar tarefa básica → "Hyrule Boot"
3. Gatilho: "Quando fizer logon"
4. Ação: Iniciar programa → `C:\Users\SEU_USUARIO\Agents\link.bat`

---

## 10. Proxy Hyrule (Claude Code com LLMs alternativos)

Para rodar o Claude Code apontando para Ollama/OpenRouter em vez da API Anthropic:

```powershell
# Terminal 1 — sobe o proxy
cd "C:\Users\SEU_USUARIO\Agents\CLAUDE CODE\global"
python proxy.py

# Terminal 2 — inicia o Claude Code via proxy
.\hyrule_proxy.bat
```

---

## Portas utilizadas

| Serviço | Porta | Descrição |
|---|---|---|
| Discord bot HTTP API | 7331 | `/send`, `/delete`, `/history`, `/status` |
| WhatsApp bot HTTP API | 7332 | `/send` |
| Hyrule Proxy | 8765 | Proxy para Claude Code |
| Ollama | 11434 | LLM local |

---

## Verificação rápida

```powershell
# Status dos serviços
python startup_services.py status

# APIs
curl http://localhost:7331/status
curl http://localhost:11434/api/tags

# Processos Python rodando
Get-Process python* | Select-Object Id, @{N='MB';E={[math]::Round($_.WorkingSet/1MB,1)}}
```

---

## Estrutura de arquivos gerados em runtime (não vão pro git)

```
Agents/
├── hyrule_env.py              ← credenciais
├── claude_queue.json          ← fila de pedidos ao Claude
├── pedidos_vistos.json        ← controle de deduplicação
├── token_usage.json/.log      ← uso de tokens por chave/dia
├── triforce_daemon.log        ← log do daemon
├── DISCORD/discord.log        ← log do bot Discord
├── DISCORD/history/           ← histórico de conversas
├── DISCORD/user_context.json  ← contexto por usuário
└── link-bot/.linkbot/
    ├── session.sqlite         ← sessão WhatsApp (preserve ao migrar!)
    └── data.db                ← storage do bot
```

> **Importante ao migrar:** copie `link-bot/.linkbot/session.sqlite` para o novo servidor para não precisar parear o WhatsApp novamente.

---

## Variáveis de ambiente opcionais

Nenhuma variável de ambiente é obrigatória — tudo é configurado via `hyrule_env.py` e `config.json`.

---

## Problemas comuns

**Bot Discord não conecta**
- Verifique o token em `hyrule_env.py`
- Confirme que os Intents estão ativados no Developer Portal

**WhatsApp pede QR toda vez**
- O arquivo `session.sqlite` foi perdido ou corrompido
- Re-execute `python -m bot.main` e escaneie o QR novamente

**Ollama não responde**
- Execute `ollama serve` e `ollama list`
- Confirme que o modelo `qwen2.5:1.5b` está baixado

**Groq/OpenRouter retornam 429**
- Rate limit atingido — o supervisor faz rotação automática entre as 3 chaves
- Aguarde alguns minutos ou adicione mais chaves em `hyrule_env.py`
