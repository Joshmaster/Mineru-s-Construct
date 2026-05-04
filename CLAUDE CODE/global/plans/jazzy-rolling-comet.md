# Plano: Agente Tool-Calling + Fallback Ollama

## Contexto
Tokens semanais do Claude Code estão acabando. OWNER quer que o máximo de pedidos do Discord sejam resolvidos pelos modelos OpenRouter (sem acionar o Claude Code), usando tool calling. Também quer um fallback via Ollama/kimi quando os tokens acabarem.

## Resultados dos testes
Modelos com tool calling funcionando (em ordem de velocidade):
1. `nvidia/nemotron-3-super-120b-a12b:free` — 0.9s ✅
2. `openai/gpt-oss-20b:free` — 1.5s ✅
3. `arcee-ai/trinity-large-preview:free` — 1.5s ✅
4. `openai/gpt-oss-120b:free` — 1.9s ✅

---

## Parte 1 — Agente Tool-Calling no Supervisor

### Arquivo: `C:/Users/OWNER/Agents/bot_supervisor.py`

### Tools a definir para o agente
```json
apagar_mensagens(usuario, data)       → chama /delete via chamar_api_local()
buscar_internet(query)                → usa urllib para DuckDuckGo instant answer API
listar_processos()                    → subprocess Get-Process (já existe)
ler_arquivo(caminho)                  → Path.read_text (já existe)
abrir_programa(nome)                  → subprocess (já existe)
fechar_programa(nome)                 → taskkill (já existe)
enviar_mensagem(usuario, mensagem)    → chama /send via chamar_api_local()
```

### Nova função: `chamar_agente_tools(pedido, usuario)`
Fluxo:
1. Envia pedido + definições das tools para o modelo
2. Se modelo responde com tool_call → executa a tool localmente → devolve resultado ao modelo
3. Modelo gera resposta final → enviar_discord()
4. Máx 3 rodadas (evita loop)
5. Fallback: se modelo não usa tool nem responde bem → enfileira pro Claude Code

### Novo fluxo em `responder_pedido()`
```
1. executar_pedido()         → resolve local simples (sem LLM)
2. chamar_agente_tools()     → resolve via LLM+tools (OpenRouter)
3. enfileirar_para_claude()  → só chega aqui se tudo falhar
```

### Ordem de modelos atualizada (baseada nos testes)
```python
MODELOS = [
    'openai/gpt-oss-20b:free',        # 1o — mais rápido (3s), args limpos
    'openai/gpt-oss-120b:free',        # 2o — backup maior
    'nvidia/nemotron-3-super-120b-a12b:free',  # 3o — funciona mas mais lento (7s)
    'arcee-ai/trinity-large-preview:free',     # 4o — reserva
    'meta-llama/llama-3.3-70b-instruct:free',  # 5o — rate limit frequente
    'google/gemma-4-31b-it:free',              # 6o — rate limit frequente
]
```

---

## Parte 2 — Fallback Ollama/Kimi

### Arquivo novo: `C:/Users/OWNER/Agents/CLAUDE CODE/ollama_fallback.py`

Comando que OWNER usa: `ollama launch claude --model kimi-k2.5:cloud`

Função: script que o supervisor chama quando `claude_queue.json` tem pedidos mas Claude Code não está disponível. Roda o modelo via Ollama e responde via `/send`.

### Fluxo
```
claude_queue.json tem pedido
  ↓
Claude Code disponível? → processa normal
  ↓ não
ollama_fallback.py → ollama run kimi-k2.5:cloud + pedido → responde via /send
```

---

## Verificação
1. Mandar pedido pro Link: "apaga as mensagens de hoje"
2. Verificar log do supervisor: deve aparecer `TOOL: apagar_mensagens` e executar sem acordar Claude Code
3. Mandar: "qual previsao do tempo em SP?"
4. Verificar: deve buscar e responder sem Claude Code
5. Testar fallback Ollama: parar Claude Code e verificar se kimi responde pedidos da fila
