# Hyrule Stack — Guia Técnico de Migração

> Documento gerado em 2026-04-08.  
> Descreve toda a infraestrutura do ambiente customizado — agnóstico de agent,  
> permitindo migração ou replicação para outro agent/LLM runner.

---

## 1. Visão Geral da Arquitetura

```
┌──────────────────────────────────────────────────────────────────┐
│                        USUÁRIO (OWNER)                           │
└────────────────────────────┬─────────────────────────────────────┘
                             │  digita: link
                             ▼
┌──────────────────────────────────────────────────────────────────┐
│                     link.bat  (launcher)                        │
│  ~/.claude/bin/link.bat                                         │
│  1. Verifica se proxy já está na porta 8765                     │
│  2. Instala dependências Python se necessário                   │
│  3. Exibe menu de seleção de provider (--select)                │
│  4. Sobe proxy.py em background (--serve)                       │
│  5. Aguarda porta 8765 ativa                                    │
│  6. Inicia `%HYRULE_AGENT%` com vars de ambiente injetadas      │
└────────────────────────────┬─────────────────────────────────────┘
                             │  ANTHROPIC_BASE_URL=http://localhost:8765
                             │  ANTHROPIC_API_KEY=proxy-key
                             ▼
┌──────────────────────────────────────────────────────────────────┐
│                  Agent configurado pelo usuário                  │
│  Recebe vars de ambiente e fala Anthropic Messages API          │
│  Envia: POST /v1/messages  (formato Anthropic Messages API)     │
└────────────────────────────┬─────────────────────────────────────┘
                             │
                             ▼
┌──────────────────────────────────────────────────────────────────┐
│              Hyrule Proxy — proxy.py  (Flask, porta 8765)       │
│                                                                  │
│  Endpoints:                                                      │
│    GET  /v1/models    → lista modelos (mock)                    │
│    POST /v1/messages  → intercepta, converte, roteia            │
│    POST /select       → troca provider sem reiniciar            │
│                                                                  │
│  Conversão de formatos:                                         │
│    Anthropic → OpenAI/Ollama (entrada)                          │
│    OpenAI/Ollama → Anthropic SSE ou JSON (saída)               │
│                                                                  │
│  Roteamento:                                                     │
│    ┌──────────┐   falha   ┌─────────────────────────────┐      │
│    │  Ollama  │ ────────► │  Menu Interativo de Fallback │      │
│    │ :11434   │           │  OpenRouter  /  Groq         │      │
│    └──────────┘           └─────────────────────────────┘      │
└──────────────────────────────────────────────────────────────────┘
```

---

## 2. Arquivos e Responsabilidades

| Arquivo | Localização | Função |
|---|---|---|
| `HYRULE.md` | `~/.claude/HYRULE.md` | System prompt global + config YAML de fallback |
| `settings.json` | `~/.claude/settings.json` | Configurações do stack |
| `proxy.py` | `~/.claude/proxy.py` | Proxy Flask — coração do sistema |
| `hyrule_fallback.py` | `~/.claude/hyrule_fallback.py` | CLI de fallback standalone (sem proxy) |
| `link.bat` | `~/.claude/bin/link.bat` | Launcher principal (instala + sobe proxy + abre agent) |
| `install_link.bat` | `~/.claude/install_link.bat` | Instalador único do stack completo |
| `start_proxy.bat` | `~/.claude/start_proxy.bat` | Sobe apenas o proxy (janela separada) |
| `hyrule_proxy.bat` | `~/.claude/hyrule_proxy.bat` | Inicia agent apontando para o proxy |

---

## 3. Configuração Central — HYRULE.md

O `HYRULE.md` é o arquivo de configuração mestre. Tem duas seções:

### 3.1 System Prompt (persona)
Tudo **antes** de `## Configuração de Fallback` é o system prompt injetado em todas as requisições.

Contém:
- Idioma obrigatório (português do Brasil)
- Persona (Link, herói de Hyrule)
- Regras de código (quando usar str_replace vs create_file)
- Estilo de comunicação

### 3.2 Bloco YAML de Fallback
Delimitado por ` ```yaml ` dentro da seção `## Configuração de Fallback`.

Estrutura:
```yaml
fallback:
  ollama:
    endpoint: http://localhost:11434/api/chat
    model: <nome-do-modelo>
    timeout: 60

  openrouter:
    endpoint: https://openrouter.ai/api/v1/chat/completions
    api_key: OPENROUTER_KEY
    models:
      - modelo-gratuito:free
      - modelo-pago
    no_tool_use:
      - modelos-sem-suporte-a-function-calling

  groq:
    endpoint: https://api.groq.com/openai/v1/chat/completions
    api_key: GROQ_KEY
    models:
      - llama-3.3-70b-versatile
    no_tool_use:
      - modelos-sem-suporte
```

**Como é lido:** ambos `proxy.py` e `hyrule_fallback.py` usam regex para extrair o bloco YAML e fazem parse com PyYAML (ou parser interno minimalista se PyYAML não estiver instalado).

---

## 4. Hyrule Proxy (proxy.py) — Detalhamento Técnico

### 4.1 Stack
- **Python 3.10+**
- **Flask** — servidor HTTP
- **requests** — chamadas às APIs externas
- **PyYAML** (opcional) — parse da config

### 4.2 Conversão de Formatos

#### Anthropic → OpenAI (entrada)
Função: `anthropic_to_openai(body, system_prompt)`

| Tipo de mensagem Anthropic | Conversão para OpenAI |
|---|---|
| `role: user` com texto simples | `role: user, content: string` |
| `role: assistant` com `tool_use` blocks | `role: assistant, tool_calls: [...]` |
| `role: user` com `tool_result` blocks | `role: tool, tool_call_id: ..., content: ...` |
| `tools: [...]` (Anthropic schema) | `tools: [{type: "function", function: {...}}]` |

Tool schema Anthropic usa `input_schema`, OpenAI usa `parameters` — o proxy converte automaticamente.

#### OpenAI → Anthropic (saída)
Função: `build_sse_stream()` / `build_json_response()`

- Respostas de texto viram `content_block` do tipo `text`
- `tool_calls` do OpenAI viram blocos `tool_use` do Anthropic
- Suporte completo a **SSE streaming** (Server-Sent Events) no formato Anthropic
- `stop_reason` calculado automaticamente (`end_turn` ou `tool_use`)

### 4.3 Fluxo de uma Requisição

```
Agent → POST /v1/messages (Anthropic format)
                │
                ▼
        anthropic_to_openai()
                │
                ▼
        _call_session()  ──► provider configurado na sessão
                │
          falhou?
                │ sim
                ▼
        interactive_fallback() → menu no terminal do proxy
                │
                ▼
        build_sse_stream() ou build_json_response()
                │
                ▼
        Agent recebe resposta (Anthropic format)
```

### 4.4 Endpoints Flask

| Método | Rota | Descrição |
|---|---|---|
| `GET` | `/v1/models` | Retorna lista mock de modelos para o agent |
| `POST` | `/v1/messages` | Endpoint principal — processa mensagens |
| `POST` | `/select` | Troca provider/modelo sem reiniciar o proxy |

### 4.5 Estado Global da Sessão (variáveis em memória)
```python
_config            # dict com toda a config do HYRULE.md
_system_prompt     # string com a persona/instruções
_session_provider  # "ollama" | "openrouter" | "groq"
_session_model     # nome do modelo ativo
_session_cfg       # config do provider ativo
_session_no_tool_use  # lista de modelos sem suporte a tools
```

---

## 5. Hyrule Fallback CLI (hyrule_fallback.py)

CLI **standalone** — funciona **sem** proxy. Útil como alternativa standalone.

### Comandos internos
| Comando | Ação |
|---|---|
| `/historico` | Exibe resumo da conversa atual |
| `/limpar` | Apaga histórico e inicia nova conversa |
| `/reload` | Recarrega HYRULE.md sem reiniciar |
| `/status` | Mostra status do Ollama, APIs configuradas, etc. |
| `/fallback` | Toggle: força uso do fallback na próxima mensagem |
| `/sair` | Encerra o programa |
| `/ajuda` | Lista os comandos |

### Histórico de conversa
- Salvo em: `~/.claude/conversation_history.json`
- Formato:
```json
{
  "updated_at": "2026-04-08T12:00:00Z",
  "total_messages": 4,
  "messages": [
    {"role": "user", "content": "..."},
    {"role": "assistant", "content": "..."}
  ]
}
```

---

## 6. Ordem de Fallback

```
1. Ollama (localhost:11434)        ← principal, gratuito, local
       │ falhou
       ▼
2. Menu interativo no terminal
       │ usuário escolhe:
       ├── OpenRouter → modelos gratuitos (:free) ou pagos
       └── Groq       → modelos com cota diária gratuita
```

**Detecção de suporte a tools:** modelos listados em `no_tool_use` no YAML recebem as ferramentas removidas automaticamente da requisição, com aviso visual (`⚠`) no terminal.

---

## 7. Variáveis de Ambiente Injetadas pelo link.bat

| Variável | Valor | Efeito |
|---|---|---|
| `ANTHROPIC_BASE_URL` | `http://localhost:8765` | Agent aponta para o proxy local |
| `ANTHROPIC_API_KEY` | `proxy-key` | Valor fake; o proxy não valida |

---

## 8. Dependências Python

```bash
pip install flask requests pyyaml
```

| Pacote | Versão mínima | Uso |
|---|---|---|
| `flask` | 2.x+ | Servidor HTTP do proxy |
| `requests` | 2.x+ | Chamadas às APIs externas |
| `pyyaml` | qualquer | Parse do YAML no HYRULE.md (opcional — há parser interno) |

---

## 9. Como Migrar para Outro Agent

### 9.1 O que precisar migrar obrigatoriamente

| Componente | O que fazer |
|---|---|
| **System prompt** | Copiar o conteúdo do `HYRULE.md` (antes da seção de fallback) |
| **Chaves de API** | OpenRouter (`OPENROUTER_KEY`) e Groq (`GROQ_KEY`) do bloco YAML |
| **Lógica de fallback** | Reimplementar a cadeia Ollama → OpenRouter → Groq |

### 9.2 O que NÃO migrar (específico do proxy Flask)

- `proxy.py` inteiro — só necessário quando o agent fala Anthropic Messages API nativamente (sem a var `ANTHROPIC_BASE_URL`)
- `link.bat` / `start_proxy.bat` — launchers específicos para Windows
- Conversão Anthropic ↔ OpenAI — só necessária para agents que falam formato Anthropic

### 9.3 Receita para outro agent (ex: Open WebUI, LangChain, custom)

```python
# 1. Leia o system prompt de HYRULE.md (até "## Configuração de Fallback")
# 2. Configure o cliente HTTP com as chaves:
OPENROUTER_KEY = "OPENROUTER_KEY"
GROQ_KEY       = "GROQ_KEY"

# 3. Implemente a cadeia de fallback:
def chat(messages, tools=None):
    # Tenta Ollama
    resp = ollama_call(messages, tools)
    if resp: return resp

    # Tenta OpenRouter
    resp = openrouter_call(messages, "qwen/qwen3.6-plus-preview:free", tools)
    if resp: return resp

    # Tenta Groq
    resp = groq_call(messages, "llama-3.3-70b-versatile", tools)
    if resp: return resp

    raise RuntimeError("Todos os providers falharam")
```

### 9.4 Modelos recomendados por tier

| Tier | Provider | Modelo | Suporta Tools |
|---|---|---|---|
| Local gratuito | Ollama | `kimi-k2.5:cloud` | Sim (Ollama >= 0.3) |
| Gratuito cloud | OpenRouter | `qwen/qwen3.6-plus-preview:free` | Sim |
| Gratuito cloud | OpenRouter | `deepseek/deepseek-chat-v3-0324:free` | Sim |
| Gratuito cota | Groq | `llama-3.3-70b-versatile` | Sim |
| Pago | OpenRouter | `google/gemini-2.5-pro-preview` | Sim |
| Pago | OpenRouter | `google/gemini-2.5-pro-preview` | Sim |

---

## 10. Estrutura de Diretórios Completa

```
~/.claude/
├── HYRULE.md                    ← config mestre (system prompt + YAML)
├── settings.json                ← configurações do stack
├── proxy.py                     ← proxy Flask principal
├── hyrule_fallback.py           ← CLI standalone de fallback
├── link.bat                     ← launcher principal
├── install_link.bat             ← instalador do stack
├── start_proxy.bat              ← sobe apenas o proxy
├── hyrule_proxy.bat             ← abre agent apontando para o proxy
├── conversation_history.json    ← histórico da CLI de fallback
├── history.jsonl                ← histórico de sessões
├── bin/
│   └── link.bat                 ← cópia no PATH
├── backups/                     ← backups automáticos
├── sessions/                    ← sessões salvas
├── projects/                    ← conversas por projeto
├── file-history/                ← histórico de arquivos editados
├── plans/                       ← planos de execução
├── tasks/                       ← tasks criadas nas sessões
├── paste-cache/                 ← cache de pastes
└── shell-snapshots/             ← snapshots de shell
```

---

## 11. Fluxo de Instalação (do zero)

```bash
# Pré-requisitos
pip install flask requests pyyaml          # dependências Python

# Instalação do Hyrule Stack
# Execute install_link.bat — ele:
# 1. Verifica Python
# 2. Copia proxy.py para ~/.claude/
# 3. Copia link.bat para ~/.claude/bin/
# 4. Copia HYRULE.md (se não existir)
# 5. Adiciona ~/.claude/bin/ ao PATH do usuário (HKCU\Environment)

# Configure o agent no link.bat:
set HYRULE_AGENT=nome-do-seu-agent

# Uso diário
link        # abre menu de provider → sobe proxy → abre agent
```

---

## 12. Segurança e Chaves Expostas

> **Atenção:** As chaves abaixo estão no HYRULE.md em texto claro.  
> Se migrar o stack, rotacione-as antes.

| Serviço | Chave (prefixo) | Onde revogar |
|---|---|---|
| OpenRouter | `OPENROUTER_KEY` | openrouter.ai -> Keys |
| Groq | `GROQ_KEY` | console.groq.com -> API Keys |

---

*Documento gerado automaticamente com base na leitura de todos os arquivos do stack Hyrule em 2026-04-08.*
