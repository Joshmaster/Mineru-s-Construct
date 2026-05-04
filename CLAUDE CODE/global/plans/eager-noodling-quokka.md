# Plano — Fix definitivo: execução de pedidos simples sem LLM

## Contexto

O bot Discord recebe pedidos como "me manda esse arquivo C:\...\foto.png".
O fluxo esperado é: Camada 1 (Python puro) → Qwen (LLM local) → OpenRouter → Triforce.

Dois bugs combinados impedem que pedidos simples sejam resolvidos:

1. **`executar_pedido()` desativada** (`bot_supervisor.py:757`) — retorna `None` imediatamente, tornando todo código de pattern matching inacessível (linhas 759-1047).
2. **`_selecionar_tools()` retorna todas as 16 tools** (`bot_supervisor.py:489`) — qwen2.5:1.5b se perde e chama 0 tools (confirmado por pesquisa: accuracy cai de ~85% com 2-3 tools para ~40-50% com 16 tools).
3. **Bug de escopo em `executar_pedido`** — a função legada usa variável `usuario` mas não a recebe como parâmetro.

Resultado: pedidos simples como "enviar arquivo" nunca são executados por nenhuma camada.

---

## Arquivo crítico

`C:\Users\OWNER\Agents\bot_supervisor.py`

---

## Mudanças

### 1. Reativar `executar_pedido` e corrigir assinatura (linha 755)

```python
# ANTES
def executar_pedido(pedido: str) -> str:
    """Delegado ao LLM — não usa mais padrões hardcoded."""
    return None
    # código legado abaixo (desativado)
    ...

# DEPOIS
def executar_pedido(pedido: str, usuario: str = "OWNER") -> str | None:
    """Camada 1: executa pedidos simples via Python puro, sem LLM."""
    import re as _re
    import unicodedata as _ud
    ...  # código legado existente, com usuario como parâmetro
```

- Remover `return None` da linha 757
- Remover comentário "código legado abaixo (desativado)"
- Adicionar `usuario: str = "OWNER"` à assinatura
- O código existente abaixo (linhas 759-1047) já tem a lógica correta

### 2. Atualizar chamada em `responder_pedido` (linha 1432)

```python
# ANTES
resultado = executar_pedido(pedido)

# DEPOIS
resultado = executar_pedido(pedido, usuario)
```

### 3. Reescrever `_selecionar_tools` com filtro por intent (linha 488)

Substituir a função atual por classificação por keyword em 5 categorias:

```python
def _selecionar_tools(pedido: str) -> list:
    p = _normalizar(pedido)  # sem acentos, lowercase

    # (a) Enviar arquivo local
    if any(x in p for x in ["enviar", "manda", "send", "arquivo", "file", "foto", "imagem", "png", "jpg", "pdf"]):
        nomes = {"enviar_arquivo_local"}

    # (b) Apagar mensagens
    elif any(x in p for x in ["apag", "delet", "remov", "limpa"]):
        nomes = {"apagar_mensagens"}

    # (c) Processos / programas
    elif any(x in p for x in ["process", "program", "abre", "fecha", "roda", "aberto"]):
        nomes = {"listar_processos", "abrir_programa", "fechar_programa"}

    # (d) Busca na internet
    elif any(x in p for x in ["busca", "pesquis", "internet", "google", "procur"]):
        nomes = {"buscar_internet"}

    # (e) Sistema / OS (IP, disco, data, etc.)
    elif any(x in p for x in ["ip", "disco", "data", "hora", "espaco", "memoria", "cmd", "powershell"]):
        nomes = {"executar_comando"}

    # (f) Arquivo no PC (ler, escrever, listar)
    elif any(x in p for x in ["le", "ler", "escreve", "lista", "pasta", "diretorio", "conteudo"]):
        nomes = {"ler_arquivo", "escrever_arquivo", "listar_arquivos"}

    else:
        # Pedido ambíguo — passa subset menor (não todas)
        nomes = {"executar_comando", "enviar_mensagem", "buscar_internet"}

    tools = [t for t in TOOLS_DEFINICAO if t["function"]["name"] in nomes]
    log(f"QWEN tools: {[t['function']['name'] for t in tools]}")
    return tools
```

---

## Por que funciona

- **Caso "enviar arquivo C:\...\foto.png"**: `executar_pedido` (camada 1) bate no Padrão C (linha 805) — regex captura o caminho, chama `/send-file` direto, sem LLM. Resolução em <100ms.
- **Se camada 1 não capturar**: `_selecionar_tools` classifica como "enviar arquivo" e passa só `enviar_arquivo_local` pro qwen → qwen com 1 tool tem ~95% de accuracy.
- **Pedidos realmente complexos**: fallback OpenRouter com tools selecionadas.

---

## Verificação

1. Reiniciar supervisor: `startup_services.py restart`
2. Mandar no Discord: `C:\Users\...\foto.png me manda`
3. Verificar `supervisor_out.log` — deve aparecer `PEDIDO:` seguido de resultado da camada 1, **sem** linha `QWEN tools:`
4. Arquivo deve chegar no Discord em <5s
5. Mandar mesmo pedido de novo — não deve aparecer como duplicado (chave tem timestamp)
