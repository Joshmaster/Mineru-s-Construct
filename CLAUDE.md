# Identidade

Voce e **Claude Code** assistindo **OWNER** no sistema **Hyrule**.

# Ao iniciar sessao

1. Ler memoria em: `~/Agents/.claude/memory/`
   - `MEMORY.md` — indice de todas as memorias
   - `project_hyrule.md` — arquitetura completa do sistema
   - `feedback_session_start.md` — rotina e comportamento esperado

2. Quando OWNER disser **"claude link"**: executar a rotina de retomada de contexto descrita em `feedback_session_start.md`

# Projeto atual

Sistema **Hyrule** — bot Discord (Link) + bot WhatsApp + supervisor + triforce daemon + proxy.
Todos os arquivos em `~/Agents/`.

# Regra de ouro — hierarquia de custos

Cada camada so e acionada se a anterior falhou:

```
1. OpenRouter gpt-oss        → tenta primeiro (chamar via API)
      ↓ falhou (429 / erro)
2. Groq llama/kimi           → tenta (0.3s latencia)
      ↓ falhou
3. Ollama qwen2.5:1.5b       → LOCAL, zero custo, ~7s CPU
      ↓ falhou
4. Voce mesmo (sessao)       → processa so se TUDO acima falhou
```

**NAO existe agente local aqui. NAO tente executar nada localmente.**
**Sempre comece pelo OpenRouter. So use voce mesmo como ultimo recurso.**

# CRITICO — nao reinvente o que ja existe

O supervisor `~/Agents/bot_supervisor.py` ja tem:
- Rotacao automatica de chaves OpenRouter (3 chaves, 6 modelos)
- Fallback para Groq com headers corretos
- Fallback para Ollama qwen2.5:1.5b
- Tool calling completo (apagar_mensagens, buscar_internet, etc.)

**NUNCA use curl ou reimplemente chamadas de API na mao.**
Para executar um pedido, chame diretamente:
```python
# Via HTTP API do bot (porta 7331)
POST http://localhost:7331/send     → envia mensagem
POST http://localhost:7331/delete   → apaga mensagens
GET  http://localhost:7331/history  → historico

# Ou escreva na fila:
~/Agents/claude_queue.json
```

**Nao pergunte qual API usar. Nao apresente opcoes. Execute e mostre o resultado.**
