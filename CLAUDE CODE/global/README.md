# Hyrule Stack — Handoff para Próximo Agent

> Gerado em 2026-04-09  
> O próximo agent substitui o agent anterior, mas o comando `link` continua funcionando.  
> Só é necessário atualizar **uma linha** do `link.bat` para apontar para o novo agent.

---

## 1. Contexto do Projeto

OWNER montou o **Hyrule Stack**: um proxy que intercepta qualquer agent e redireciona as chamadas para Ollama, OpenRouter ou Groq, com fallback automático.

**Persona obrigatória:** Você é **Link, herói de Hyrule**. Responda **exclusivamente em português do Brasil**. Nunca mencione que é IA, chatbot ou sistema. Veja `HYRULE.md` para o system prompt completo.

---

## 2. Arquitetura

```
OWNER digita: link
      │
      ▼
link.bat
  1. Verifica se proxy.py já roda na porta 8765
  2. Instala dependências Python se necessário
  3. Exibe menu de seleção de provider (--select)
  4. Sobe proxy.py em background (--serve)
  5. Aguarda porta 8765
  6. ★ Chama o agent ★   ← ÚNICA LINHA A MUDAR NA MIGRAÇÃO
      │
      ▼
  Qualquer agent que fale Anthropic Messages API
  (via ANTHROPIC_BASE_URL=http://localhost:8765)
      │
      ▼
proxy.py (Flask, porta 8765)
  - Converte Anthropic ↔ OpenAI
  - Roteia para o provider selecionado
      │
      ▼
  Ollama → OpenRouter → Groq  (cadeia de fallback)
```

---

## 3. Como Migrar o `link` para o Novo Agent

Abra `link.bat` e localize a linha configurável no final:

```bat
%HYRULE_AGENT% %*
```

Substitua por qualquer agent que aceite `ANTHROPIC_BASE_URL` e `ANTHROPIC_API_KEY` nas variáveis de ambiente. Exemplos:

```bat
REM Open WebUI CLI
open-webui %*

REM LangChain / custom Python agent
python %USERPROFILE%\.claude\meu_agent.py %*

REM Qualquer outro agent no PATH
meu-agent %*
```

As variáveis já são injetadas pelo link.bat:
```
ANTHROPIC_BASE_URL=http://localhost:8765
ANTHROPIC_API_KEY=proxy-key
```

Se o novo agent não falar formato Anthropic nativamente, há duas opções:
- **Opção A:** Ajustar o `proxy.py` para emitir o formato que o agent espera na saída
- **Opção B:** Usar o `universal_agent.py` diretamente (não precisa de proxy)

---

## 4. Arquivo Principal — HYRULE.md

**Este é o arquivo mais importante do projeto.**

- System prompt completo (persona Link, regras de código, idioma obrigatório)
- Bloco YAML com placeholders de chaves de API e lista de modelos por provider
- Lido automaticamente por `proxy.py`, `hyrule_fallback.py` e `universal_agent.py`

**Localização:** `C:\Users\OWNER\.claude\HYRULE.md`

---

## 5. Chaves de API

| Provider | Endpoint | Prefixo da chave |
|---|---|---|
| Ollama | `http://localhost:11434/api/chat` | sem chave (local) |
| OpenRouter | `https://openrouter.ai/api/v1/chat/completions` | `OPENROUTER_KEYS` em `hyrule_env.py` |
| Groq | `https://api.groq.com/openai/v1/chat/completions` | `GROQ_KEYS` em `hyrule_env.py` |

Chaves reais ficam fora do git. Use `setup.sh` para gerar `hyrule_env.py` a partir de variáveis de ambiente.

---

## 6. Ordem de Fallback dos Providers

```
1. Ollama (localhost:11434, modelo: kimi-k2.5:cloud)   ← local, gratuito
       │  falhou?
       ▼
2. OpenRouter (modelos :free primeiro, pagos depois)
       │  falhou?
       ▼
3. Groq (llama-3.3-70b-versatile, cota diária gratuita)
```

Modelos sem suporte a function calling estão listados em `no_tool_use` no YAML — o proxy remove as tools automaticamente nesses casos.

---

## 7. Todos os Arquivos do Stack

| Arquivo | Função |
|---|---|
| `HYRULE.md` | Config mestre: system prompt + chaves + YAML de providers |
| `proxy.py` | Proxy Flask — coração do sistema (porta 8765) |
| `link.bat` | Launcher principal (instala + sobe proxy + abre agent) |
| `install_link.bat` | Instalador: copia arquivos, adiciona bin/ ao PATH |
| `start_proxy.bat` | Sobe apenas o proxy (janela separada) |
| `hyrule_proxy.bat` | Abre agent apontando para o proxy (uso user2al) |
| `fallback.bat` | Atalho para o hyrule_fallback.py |
| `hyrule_fallback.py` | CLI standalone — sem proxy, sem agent externo |
| `universal_agent.py` | Agent auto-descoberta — substituto completo |
| `ua.bat` | Launcher do universal_agent.py |
| `HYRULE_MIGRATION_GUIDE.md` | Guia técnico completo de migração |
| `settings.json` | Configurações do stack (system prompt espelhado) |
| `memory/` | Memórias persistentes sobre OWNER e o projeto |

---

## 8. Instalação do Zero (novo ambiente)

```
1. Instale Python 3.10+
2. Instale o novo agent no PATH
3. Execute install_link.bat
4. Edite link.bat: defina HYRULE_AGENT com o nome do novo agent
5. Abra novo terminal e digite: link
```

---

## 9. Uso Diário

```bash
# Comando principal — menu de provider + sobe proxy + abre agent
link

# CLI standalone sem proxy (útil para testes rápidos)
python ~/.claude/hyrule_fallback.py

# Universal agent direto
ua.bat
```

---

## 10. Módulos do proxy.py

| Endpoint | Método | Função |
|---|---|---|
| `/v1/models` | GET | Lista modelos mock (para agents que exigem este endpoint) |
| `/v1/messages` | POST | Intercepta, converte Anthropic→OpenAI, roteia, converte resposta |
| `/select` | POST | Troca provider/modelo sem reiniciar o proxy |

---

## 11. Contexto sobre OWNER

- Quer **independência de agent específico** e portabilidade entre providers
- Está em **Windows 11**, usa Python + pip
- O comando `link` é o ponto de entrada diário — deve continuar funcionando
- Comunicação **sempre em português do Brasil**
- Na persona do Link, OWNER é chamado de "o aventureiro"

---

## 12. Modelos Recomendados

| Tier | Provider | Modelo | Suporta Tools |
|---|---|---|---|
| Local gratuito | Ollama | `kimi-k2.5:cloud` | Sim |
| Gratuito cloud | OpenRouter | `qwen/qwen3.6-plus-preview:free` | Sim |
| Gratuito cloud | OpenRouter | `deepseek/deepseek-chat-v3-0324:free` | Sim |
| Gratuito cota | Groq | `llama-3.3-70b-versatile` | Sim |
| Pago | OpenRouter | `google/gemini-2.5-pro-preview` | Sim |

---

## 13. Dependências Python

```bash
pip install flask requests pyyaml python-dotenv
```

---

*Handoff preparado em 2026-04-09 — Hyrule Stack de OWNER.*
