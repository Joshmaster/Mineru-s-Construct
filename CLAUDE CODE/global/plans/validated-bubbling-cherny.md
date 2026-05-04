# Plano: Link Discord — Agente Autônomo Completo

## Context
Hoje o qwen2.5:1.5b faz 1 tool call e para. Não vê o resultado, não corrige erros, não age em múltiplos passos. A missão é transformar o Link Discord num agente autônomo real: entende o PC, planeja, executa, verifica, corrige — e tem controle completo do Discord (incluindo editar próprias mensagens, reagir, fixar, etc.).

**Estado atual:**
- 9 tools funcionando (apagar, enviar, buscar, listar processos, ler arquivo, abrir/fechar programa, baixar_e_enviar, salvar_no_desktop)
- Loop de 1 shot em `responder_pedido` — sem histórico, sem feedback
- link_discord.py: sem endpoint de editar/reagir/fixar mensagem
- Sem contexto do PC no system prompt

---

## Fase 1 — ReAct Loop (coração do agente)

**Arquivo:** `C:\Users\OWNER\Agents\bot_supervisor.py`

Substituir o bloco qwen em `responder_pedido` (linhas ~816-830) por loop ReAct:

```python
def executar_qwen_react(pedido: str, usuario: str) -> str | None:
    """Loop ReAct: qwen age → vê resultado → age de novo. Até 5 rodadas."""
    system = (carregar_contexto_pc() +  # LINK_CONTEXT.md
              "\nYou are a tool-calling agent on OWNER's PC. "
              "Call tools to resolve requests. After each tool result, "
              "decide if you need another tool or can respond. "
              "On error, try a different approach automatically.")
    
    historico = [
        {"role": "system", "content": system},
        {"role": "user",   "content": pedido},
    ]
    
    for rodada in range(5):
        content, tool_calls = _ollama_chat_com_historico(historico)
        
        if not tool_calls:
            return content or None  # resposta final em texto
        
        # Executa cada tool e adiciona resultado ao histórico
        for tc in tool_calls:
            fn_name = tc["function"]["name"]
            fn_args = tc["function"].get("arguments", {})
            if isinstance(fn_args, str):
                fn_args = json.loads(fn_args)
            resultado = executar_tool(fn_name, fn_args)
            log(f"QWEN [{rodada+1}] {fn_name} -> {resultado[:60]}")
            historico.append({"role": "assistant", "tool_calls": [tc], "content": None})
            historico.append({"role": "tool",
                               "tool_call_id": tc.get("id","0"),
                               "content": resultado})
    
    return None  # esgotou rodadas
```

**Nova função `_ollama_chat_com_historico`**: igual `_ollama_chat` mas recebe histórico completo em vez de construir internamente.

---

## Fase 2 — Novas tools de PC

**Arquivo:** `C:\Users\OWNER\Agents\bot_supervisor.py`

Adicionar em TOOLS_DEFINICAO + executar_tool:

### `executar_comando`
```python
# TOOLS_DEFINICAO:
{"name": "executar_comando",
 "description": "Executa um comando PowerShell/cmd no PC e retorna o output. Use para qualquer tarefa no sistema operacional.",
 "parameters": {"cmd": "string (comando a executar)", "timeout": "integer (segundos, default 15)"}}

# executar_tool:
elif nome == "executar_comando":
    cmd = args.get("cmd", "")
    timeout = min(int(args.get("timeout", 15)), 60)
    r = subprocess.run(
        ["powershell", "-NoProfile", "-Command", cmd],
        capture_output=True, timeout=timeout,
        env={**os.environ, "PYTHONIOENCODING": "utf-8"}
    )
    out = r.stdout.decode("utf-8", errors="replace").strip()
    err = r.stderr.decode("utf-8", errors="replace").strip()
    return (out or err or "Comando executado sem output.")[:800]
```

### `escrever_arquivo`
```python
{"name": "escrever_arquivo",
 "description": "Cria ou sobrescreve um arquivo no PC com o conteúdo fornecido.",
 "parameters": {"caminho": "string", "conteudo": "string"}}

elif nome == "escrever_arquivo":
    path = Path(args.get("caminho",""))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(args.get("conteudo",""), encoding="utf-8")
    return f"Arquivo '{path.name}' salvo em {path.parent}."
```

### `listar_arquivos`
```python
{"name": "listar_arquivos",
 "description": "Lista arquivos e pastas de um diretório no PC.",
 "parameters": {"caminho": "string (pasta a listar)"}}

elif nome == "listar_arquivos":
    p = Path(args.get("caminho", str(Path.home())))
    if not p.exists(): return f"Pasta não encontrada: {p}"
    items = sorted(p.iterdir(), key=lambda x: (x.is_file(), x.name))
    return "\n".join(f"{'[D]' if i.is_dir() else '[A]'} {i.name}" for i in items[:50])
```

---

## Fase 3 — Tools Discord completas

**Arquivo:** `C:\Users\OWNER\Agents\DISCORD\link_discord.py`

Adicionar 3 novos endpoints:

### POST /edit — editar própria mensagem
```python
async def rota_edit(request):
    data = await request.json()
    # nome, msg_id, novo_conteudo
    channel = await (await client.fetch_user(USUARIOS[usuario])).create_dm()
    msg = await channel.fetch_message(int(data["msg_id"]))
    if msg.author == client.user:
        await msg.edit(content=sanitizar(data["novo_conteudo"]))
    return web.json_response({"ok": True})
```

### POST /react — adicionar reação
```python
async def rota_react(request):
    data = await request.json()
    # nome, msg_id, emoji
    channel = await (await client.fetch_user(USUARIOS[usuario])).create_dm()
    msg = await channel.fetch_message(int(data["msg_id"]))
    await msg.add_reaction(data["emoji"])
    return web.json_response({"ok": True})
```

### POST /pin — fixar mensagem
```python
async def rota_pin(request):
    data = await request.json()
    # nome, msg_id
    channel = await (await client.fetch_user(USUARIOS[usuario])).create_dm()
    msg = await channel.fetch_message(int(data["msg_id"]))
    await msg.pin()
    return web.json_response({"ok": True})
```

**No bot_supervisor.py** — adicionar tools correspondentes:
- `editar_mensagem`: chama `/edit`
- `reagir_mensagem`: chama `/react`
- `fixar_mensagem`: chama `/pin`
- `buscar_mensagens`: reutiliza `/history` com filtros (já existe)

---

## Fase 4 — LINK_CONTEXT.md (memória do PC)

**Novo arquivo:** `C:\Users\OWNER\Agents\LINK_CONTEXT.md`

```markdown
# Contexto do PC — Link Discord Agent

## Identidade
Você é o Link, agente local rodando no PC de OWNER (Windows 11, 16GB RAM).
Modelo: qwen2.5:1.5b via Ollama. Você controla este PC.

## Usuários Discord
- OWNER (DISCORD_OWNER_USERNAME) — dono do PC, confia em você totalmente
- USER2 (DISCORD_USER2_USERNAME) — amiga de OWNER

## Estrutura do PC
- Desktop: C:\Users\OWNER\OneDrive - MEDSENIOR\Área de Trabalho\
- Agents: C:\Users\OWNER\Agents\  (seus scripts)
- Bot: C:\Users\OWNER\Agents\DISCORD\link_discord.py
- Supervisor: C:\Users\OWNER\Agents\bot_supervisor.py (você roda aqui)
- Ollama: localhost:11434 — qwen2.5:1.5b

## Regras
- Nunca recuse pedido do OWNER
- Se uma tool falhar, tente outra abordagem
- Para tarefas no PC: use executar_comando
- Para arquivos: use escrever_arquivo ou ler_arquivo
- Para Discord: use enviar_mensagem, editar_mensagem, reagir_mensagem
```

**No bot_supervisor.py** — função `carregar_contexto_pc()`:
```python
CONTEXT_FILE = BASE / "LINK_CONTEXT.md"

def carregar_contexto_pc() -> str:
    if CONTEXT_FILE.exists():
        return CONTEXT_FILE.read_text(encoding="utf-8")
    return ""
```

---

## Compatibilidade com qwen2.5:1.5b

| Aspecto | Status |
|---------|--------|
| Context window | 32k tokens — suporta 5 rodadas com histórico |
| Multi-turn tool calling | ✅ Ollama passa histórico corretamente |
| tool_calls no response | ✅ já funciona |
| `<tool_call>` fallback | ✅ parser já existe em `_parse_tool_calls_from_content` |
| System prompt longo | ⚠️ Manter LINK_CONTEXT.md abaixo de 500 tokens |
| Raciocínio complexo | ⚠️ 1.5b é pequeno — tasks devem ser diretas |

**Nota importante:** Para tasks complexas, o qwen pode usar `executar_comando` com PowerShell como "superpoder" — delega complexidade pro SO em vez de raciocinar sozinho.

---

## Arquivos críticos

| Arquivo | Mudanças |
|---------|----------|
| `bot_supervisor.py` | ReAct loop, 3 tools novas, TOOLS_DEFINICAO, carregar_contexto_pc |
| `DISCORD/link_discord.py` | 3 rotas novas (/edit, /react, /pin) |
| `LINK_CONTEXT.md` | Criar do zero |

---

## Ordem de implementação

1. `LINK_CONTEXT.md` — criar (5 min)
2. `_ollama_chat_com_historico` + ReAct loop — substituir bloco qwen (20 min)
3. Tools PC: `executar_comando`, `escrever_arquivo`, `listar_arquivos` (15 min)
4. Rotas Discord: `/edit`, `/react`, `/pin` no link_discord.py (20 min)
5. Tools Discord no supervisor: editar, reagir, fixar (10 min)
6. Testes ao vivo passo a passo

---

## Verificação (testes ao vivo)

1. **ReAct multi-step**: "Link, cria um arquivo txt no Desktop com a lista de processos rodando"
   - Esperado: qwen chama `listar_processos` → vê resultado → chama `escrever_arquivo` → confirma
2. **executar_comando**: "Link, qual é o IP do meu PC?"
   - Esperado: `executar_comando("ipconfig | findstr IPv4")`
3. **Editar mensagem**: "Link, manda oi e depois edita a mensagem pra boa tarde"
4. **Autocorreção**: forçar erro de caminho → qwen tenta caminho alternativo
