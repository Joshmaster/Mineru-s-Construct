#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Supervisor do Discord bot — daemon permanente.
Monitora discord.log em tempo real e:
  1. Executa [SHEIKAH_SLATE-PEDIDO] automaticamente (lê arquivos, lista processos, etc.)
  2. Corrige respostas ruins do bot (recusas indevidas)
"""
import json
import os
import subprocess
import sys
import time
import threading
import urllib.request
import urllib.error
from pathlib import Path

_log_lock       = threading.Lock()
_pedido_lock    = threading.Lock()

# Força UTF-8 no stdout/stderr (Windows usa cp1252 por padrão)
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

BASE         = Path(__file__).parent
DISCORD_DIR  = BASE / "DISCORD"
LOG_FILE     = DISCORD_DIR / "discord.log"
DM_SCRIPT    = DISCORD_DIR / "dm.py"
PERSONA_FILE = BASE / "OPENCODE" / "roaming" / "LINK_PERSONA.md"
CLAUDE_QUEUE = BASE / "claude_queue.json"
PYTHON       = sys.executable

TOKEN_USAGE_FILE = BASE / "token_usage.json"
TOKEN_LOG_FILE   = BASE / "token_usage.log"
_token_lock      = threading.Lock()

def _registrar_tokens(key: str, modelo: str, prompt_tokens: int, completion_tokens: int, fn: str):
    """Registra uso de tokens por chave/dia em JSON e em log de texto."""
    import datetime
    hoje = datetime.date.today().isoformat()
    key_label = f"or_key_{OPENROUTER_KEYS.index(key) + 1}" if key in OPENROUTER_KEYS else key[:12]
    total = prompt_tokens + completion_tokens
    with _token_lock:
        # JSON acumulado
        dados = {}
        if TOKEN_USAGE_FILE.exists():
            try:
                dados = json.loads(TOKEN_USAGE_FILE.read_text(encoding="utf-8"))
            except Exception:
                dados = {}
        dia = dados.setdefault(hoje, {})
        entry = dia.setdefault(key_label, {"prompt": 0, "completion": 0, "total": 0, "chamadas": 0})
        entry["prompt"]     += prompt_tokens
        entry["completion"] += completion_tokens
        entry["total"]      += total
        entry["chamadas"]   += 1
        TOKEN_USAGE_FILE.write_text(json.dumps(dados, indent=2, ensure_ascii=False), encoding="utf-8")
        # Log de texto linha a linha
        ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        line = f"[{ts}] {key_label} | {modelo.split('/')[-1][:20]:20s} | fn={fn:20s} | prompt={prompt_tokens:5d} compl={completion_tokens:5d} total={total:5d}\n"
        with open(TOKEN_LOG_FILE, "a", encoding="utf-8") as f:
            f.write(line)

OLLAMA_URL    = "http://localhost:11434/api/chat"
OLLAMA_MODEL  = "qwen2.5:1.5b"      # local fallback — tool calling via <tool_call>, ~1GB
OLLAMA_CLOUD  = None                # reservado — definir modelo cloud quando decidido

try:
    from hyrule_env import GROQ_KEYS, OPENROUTER_KEYS as _OR_KEYS_ENV
    _OPENROUTER_KEYS_ENV = _OR_KEYS_ENV
except ImportError:
    GROQ_KEYS = []
    _OPENROUTER_KEYS_ENV = []

GROQ_URL  = "https://api.groq.com/openai/v1/chat/completions"
GROQ_HEADERS = {
    "Content-Type": "application/json",
    "User-Agent":   "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept":       "application/json",
    "Origin":       "https://console.groq.com",
    "Referer":      "https://console.groq.com/",
}
# Modelos Groq com tool calling (0.3s latência)
GROQ_MODELOS = [
    "llama-3.3-70b-versatile",
    "moonshotai/kimi-k2-instruct",
    "openai/gpt-oss-20b",
    "llama-3.1-8b-instant",
]

OPENROUTER_KEYS = _OPENROUTER_KEYS_ENV
# Modelos validados com tool calling (ordenados por confiabilidade/velocidade)
MODELOS = [
    "openai/gpt-oss-20b:free",                 # 1o — 3s, args limpos
    "openai/gpt-oss-120b:free",                # 2o — backup maior
    "nvidia/nemotron-3-super-120b-a12b:free",  # 3o — 7s, funciona
    "arcee-ai/trinity-large-preview:free",     # 4o — reserva
    "meta-llama/llama-3.3-70b-instruct:free",  # 5o — rate limit frequente
    "google/gemma-4-31b-it:free",              # 6o — rate limit frequente
]

# Definição das tools disponíveis para o agente LLM
TOOLS_DEFINICAO = [
    {
        "type": "function",
        "function": {
            "name": "apagar_mensagens",
            "description": "Apaga mensagens enviadas pelo bot no Discord DM de um usuario",
            "parameters": {
                "type": "object",
                "properties": {
                    "usuario": {"type": "string", "description": "Nome do usuario: OWNER ou USER2"},
                    "data":    {"type": "string", "description": "Periodo: hoje, ontem, tudo"},
                },
                "required": ["usuario", "data"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "buscar_internet",
            "description": "Busca informacao na internet e retorna resumo",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Termo de busca"},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "buscar_imagem",
            "description": (
                "Busca uma imagem na web e retorna a URL direta para download. "
                "Use quando pedirem para buscar/procurar uma imagem na internet. "
                "Para itens de Zelda Breath of the Wild use wiki='botw'. "
                "Para outros itens Zelda use wiki='zelda'. "
                "Para imagens genéricas use wiki='commons'."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "termo": {"type": "string", "description": "Nome do item ou objeto a buscar (ex: 'master sword', 'hylian shield')"},
                    "wiki":  {"type": "string", "description": "Fonte preferida: 'botw', 'zelda' ou 'commons'. Default: 'zelda'"},
                },
                "required": ["termo"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "listar_processos",
            "description": "Lista programas e processos abertos no PC",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "ler_arquivo",
            "description": "Le o conteudo de um arquivo no PC",
            "parameters": {
                "type": "object",
                "properties": {
                    "caminho": {"type": "string", "description": "Caminho absoluto ou nome do arquivo"},
                },
                "required": ["caminho"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "abrir_programa",
            "description": "Abre um programa no PC",
            "parameters": {
                "type": "object",
                "properties": {
                    "nome": {"type": "string", "description": "Nome do programa (chrome, notepad, etc.)"},
                },
                "required": ["nome"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "fechar_programa",
            "description": "Fecha/encerra um programa no PC",
            "parameters": {
                "type": "object",
                "properties": {
                    "nome": {"type": "string", "description": "Nome do processo ou programa"},
                },
                "required": ["nome"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "enviar_mensagem",
            "description": "Envia uma mensagem de texto pelo Discord para um usuario",
            "parameters": {
                "type": "object",
                "properties": {
                    "usuario":  {"type": "string", "description": "Nome do usuario: OWNER ou USER2"},
                    "mensagem": {"type": "string", "description": "Texto da mensagem a enviar"},
                },
                "required": ["usuario", "mensagem"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "baixar_e_enviar",
            "description": "Baixa um arquivo da internet e envia pelo Discord para o usuario",
            "parameters": {
                "type": "object",
                "properties": {
                    "url":      {"type": "string", "description": "URL do arquivo a baixar"},
                    "filename": {"type": "string", "description": "Nome do arquivo com extensao"},
                    "usuario":  {"type": "string", "description": "Nome do usuario: OWNER ou USER2"},
                    "msg":      {"type": "string", "description": "Mensagem opcional junto ao arquivo"},
                },
                "required": ["url", "filename", "usuario"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "salvar_no_desktop",
            "description": "Baixa um arquivo de uma URL e salva localmente na Área de Trabalho (Desktop) do computador. Use esta tool quando pedirem para salvar/guardar um arquivo no PC, não para enviar pelo Discord.",
            "parameters": {
                "type": "object",
                "properties": {
                    "url":      {"type": "string", "description": "URL do arquivo a baixar"},
                    "filename": {"type": "string", "description": "Nome do arquivo com extensao (ex: foto.jpg)"},
                },
                "required": ["url", "filename"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "executar_comando",
            "description": "Executa um comando PowerShell no PC e retorna o output. Use para qualquer tarefa no sistema operacional: verificar IPs, mover arquivos, instalar, etc.",
            "parameters": {
                "type": "object",
                "properties": {
                    "cmd":     {"type": "string",  "description": "Comando PowerShell a executar"},
                    "timeout": {"type": "integer", "description": "Timeout em segundos (default 15, max 60)"},
                },
                "required": ["cmd"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "escrever_arquivo",
            "description": "Cria ou sobrescreve um arquivo no PC com o conteúdo fornecido.",
            "parameters": {
                "type": "object",
                "properties": {
                    "caminho":  {"type": "string", "description": "Caminho absoluto do arquivo (ex: C:/Users/OWNER/Desktop/nota.txt)"},
                    "conteudo": {"type": "string", "description": "Conteúdo a escrever no arquivo"},
                },
                "required": ["caminho", "conteudo"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "listar_arquivos",
            "description": "Lista arquivos e pastas de um diretório no PC.",
            "parameters": {
                "type": "object",
                "properties": {
                    "caminho": {"type": "string", "description": "Pasta a listar (ex: C:/Users/OWNER/Desktop)"},
                },
                "required": ["caminho"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "editar_mensagem",
            "description": "Edita o conteúdo de uma mensagem própria já enviada no Discord.",
            "parameters": {
                "type": "object",
                "properties": {
                    "usuario":       {"type": "string", "description": "Nome do usuário: OWNER ou USER2"},
                    "msg_id":        {"type": "string", "description": "ID da mensagem a editar"},
                    "novo_conteudo": {"type": "string", "description": "Novo texto da mensagem"},
                },
                "required": ["usuario", "msg_id", "novo_conteudo"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "reagir_mensagem",
            "description": "Adiciona uma reação (emoji) a uma mensagem no Discord.",
            "parameters": {
                "type": "object",
                "properties": {
                    "usuario": {"type": "string", "description": "Nome do usuário: OWNER ou USER2"},
                    "msg_id":  {"type": "string", "description": "ID da mensagem"},
                    "emoji":   {"type": "string", "description": "Emoji a reagir (ex: 👍, ❤️, 🔥)"},
                },
                "required": ["usuario", "msg_id", "emoji"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "fixar_mensagem",
            "description": "Fixa (pina) uma mensagem no canal do Discord.",
            "parameters": {
                "type": "object",
                "properties": {
                    "usuario": {"type": "string", "description": "Nome do usuário: OWNER ou USER2"},
                    "msg_id":  {"type": "string", "description": "ID da mensagem a fixar"},
                },
                "required": ["usuario", "msg_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "enviar_arquivo_local",
            "description": "Envia um arquivo já salvo no PC para o Discord. Use quando o arquivo já existe localmente (ex: C:\\Users\\...\\foto.png). Diferente de baixar_e_enviar que precisa de URL.",
            "parameters": {
                "type": "object",
                "properties": {
                    "caminho":  {"type": "string", "description": "Caminho completo do arquivo no PC (ex: C:\\Users\\OWNER\\Imagens\\foto.png)"},
                    "usuario":  {"type": "string", "description": "Nome do usuário: OWNER ou USER2"},
                    "msg":      {"type": "string", "description": "Mensagem opcional junto ao arquivo"},
                },
                "required": ["caminho", "usuario"],
            },
        },
    },
]

PADROES_RUINS = [
    "desculpe, não posso",
    "desculpe, nao posso",
    "não posso ajudar com isso",
    "nao posso ajudar com isso",
    "não é possível",
    "não tenho acesso",
    "não consigo fazer",
    "infelizmente não",
    "isso está fora",
    "não posso realizar",
    "não sou capaz",
]


# ── Utilitários ───────────────────────────────────────────────────────────────

def log(msg: str):
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    with _log_lock:
        print(f"[{ts}] {msg}", flush=True)


_LIXO_PADRAO = [
    "procure uma ferramenta", "apagando mensagens", "confirmado. arquivo",
    "tente novamente", "fazendo a chamada", "para interagir com o sistema",
    "okay, let me", "first,", "looking at", "i need to", "i will", "i'll",
    "let me", "to complete", "i can help", "escalar_claude",
    "[salvar no desktop]", "[enviar_arquivo_local",
]

def _e_lixo(texto: str) -> bool:
    """Retorna True se o texto parece raciocínio interno ou lixo do LLM."""
    t = texto.lower().strip()
    if not t:
        return True
    return any(p in t for p in _LIXO_PADRAO)


def enviar_discord(usuario: str, mensagem: str):
    if _e_lixo(mensagem):
        log(f"FILTRADO (lixo LLM) -> {usuario}: {mensagem[:80]}")
        return
    payload = json.dumps({"to": usuario, "msg": mensagem}).encode("utf-8")
    req = urllib.request.Request(
        "http://localhost:7331/send", data=payload,
        headers={"Content-Type": "application/json"}, method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            pass
    except Exception as e:
        log(f"Erro enviar_discord: {e}")
    log(f"ENVIADO -> {usuario}: {mensagem[:80]}")


def chamar_api_local(rota: str, payload: dict = None, metodo: str = "POST") -> dict | None:
    """Chama a HTTP API do bot em localhost:7331."""
    url = f"http://localhost:7331{rota}"
    data = json.dumps(payload).encode("utf-8") if payload else None
    req = urllib.request.Request(
        url, data=data,
        headers={"Content-Type": "application/json"},
        method=metodo,
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return json.loads(r.read())
    except Exception as e:
        log(f"Erro API local {rota}: {e}")
        return None


def chamar_groq_tools(pedido: str, system: str, tools: list) -> tuple[str | None, list]:
    """Chama Groq com tool calling. Retorna (texto, tool_calls)."""
    for modelo in GROQ_MODELOS:
        for key in GROQ_KEYS:
            payload = json.dumps({
                "model":       modelo,
                "messages":    [
                    {"role": "system", "content": system},
                    {"role": "user",   "content": pedido},
                ],
                "tools":       tools,
                "tool_choice": "auto",
                "max_tokens":  300,
                "temperature": 0.3,
            }).encode("utf-8")
            req = urllib.request.Request(
                GROQ_URL, data=payload,
                headers={**GROQ_HEADERS, "Authorization": f"Bearer {key}"},
                method="POST",
            )
            try:
                with urllib.request.urlopen(req, timeout=15) as r:
                    data       = json.loads(r.read())
                msg        = data["choices"][0]["message"]
                tool_calls = msg.get("tool_calls", [])
                content    = msg.get("content", "") or ""
                log(f"GROQ [{modelo}] respondeu")
                return content.strip(), tool_calls
            except urllib.error.HTTPError as e:
                if e.code in (401, 403, 429):
                    continue
            except Exception:
                continue
    return None, []


def ollama_disponivel() -> bool:
    try:
        with urllib.request.urlopen("http://localhost:11434/api/tags", timeout=3) as r:
            return r.status == 200
    except Exception:
        return False


def _ollama_chat(model: str, payload: dict) -> dict | None:
    """Chamada genérica ao Ollama. Retorna o dict da resposta ou None."""
    # Parâmetros otimizados para qwen2.5:1.5b tool calling (fonte: comunidade Ollama)
    defaults = {
        "model":              model,
        "stream":             False,
        "temperature":        0.7,
        "top_p":              0.8,
        "top_k":              20,
        "repeat_penalty":     1.05,
    }
    data = json.dumps({**defaults, **payload}).encode("utf-8")
    req  = urllib.request.Request(OLLAMA_URL, data=data,
           headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.loads(r.read())
    except Exception as e:
        log(f"Ollama [{model}] erro: {e}")
        return None


CONTEXT_FILE = BASE / "LINK_CONTEXT.md"


def carregar_contexto_pc() -> str:
    """Carrega LINK_CONTEXT.md para injetar no system prompt do qwen."""
    if CONTEXT_FILE.exists():
        return CONTEXT_FILE.read_text(encoding="utf-8").strip() + "\n\n"
    return ""


def _ollama_react(historico: list, tools: list) -> tuple[str, list]:
    """Chama Ollama com histórico completo. Retorna (content, tool_calls)."""
    payload = {"messages": historico}
    if tools:
        payload["tools"] = tools
    data = _ollama_chat(OLLAMA_MODEL, payload)
    if not data:
        return "", []
    msg = data.get("message", {})
    tool_calls = msg.get("tool_calls") or []
    content = (msg.get("content") or "").strip()
    if not tool_calls and content:
        tool_calls = _parse_tool_calls_from_content(content)
        if tool_calls:
            content = ""
    return content, tool_calls


def _normalizar(texto: str) -> str:
    """Remove acentos para comparação robusta de keywords."""
    import unicodedata
    return ''.join(
        c for c in unicodedata.normalize('NFD', texto.lower())
        if unicodedata.category(c) != 'Mn'
    )


def _selecionar_tools(pedido: str) -> list:
    """Filtra tools por intent do pedido. Max 3 tools — qwen2.5:1.5b trava com mais."""
    p = _normalizar(pedido)

    _busca_img = (
        any(x in p for x in ["busca", "pesquis", "procur", "acha", "encontra", "web", "internet"]) and
        any(x in p for x in ["imagem", "foto", "png", "jpg", "figura", "ilustracao", "artwork", "arte", "icon"])
    )
    if _busca_img:
        nomes = {"buscar_imagem", "baixar_e_enviar"}
    elif any(x in p for x in ["enviar", "manda", "send", "arquivo", "file", "foto", "imagem", "png", "jpg", "jpeg", "gif", "pdf", "mp4", "zip"]):
        nomes = {"enviar_arquivo_local"}
    elif any(x in p for x in ["apag", "delet", "remov", "limpa", "clear"]):
        nomes = {"apagar_mensagens"}
    elif any(x in p for x in ["process", "program", "abre", "fecha", "roda", "aberto", "rodando", "executando"]):
        nomes = {"listar_processos", "abrir_programa", "fechar_programa"}
    elif any(x in p for x in ["busca", "pesquis", "internet", "google", "procur", "duckduck"]):
        nomes = {"buscar_internet"}
    elif any(x in p for x in ["ip", "disco", "data", "hora", "espaco", "memoria", "cmd", "powershell", "comando"]):
        nomes = {"executar_comando"}
    elif any(x in p for x in ["le ", "ler", "escreve", "lista", "pasta", "diretorio", "conteudo", "listar"]):
        nomes = {"ler_arquivo", "escrever_arquivo", "listar_arquivos"}
    elif any(x in p for x in ["baixar", "download", "url", "http", "link"]):
        nomes = {"baixar_e_enviar", "salvar_no_desktop"}
    else:
        nomes = {"executar_comando", "enviar_mensagem", "buscar_internet"}

    tools = [t for t in TOOLS_DEFINICAO if t["function"]["name"] in nomes]
    log(f"QWEN tools selecionadas: {[t['function']['name'] for t in tools]}")
    return tools


def _gerar_hint_sequencia(pedido: str, tools: list) -> str:
    """Gera dica de sequenciamento para orientar qwen em pedidos multi-step.
    Para qwen 1.5b: sempre redireciona multi-step para executar_comando (1 PS command).
    """
    nomes = {t["function"]["name"] for t in tools}
    p = pedido.lower()

    # Multi-step com processos → PS one-liner via executar_comando
    if "executar_comando" in nomes and ("escrever_arquivo" in nomes or "listar_processos" in nomes):
        import re as _re
        desktop = r"C:\Users\OWNER\OneDrive - MEDSENIOR\Área de Trabalho"
        # Tenta extrair nome de arquivo do pedido
        m = _re.search(r'(?:chamado|chamada|nome|arquivo)\s+(\S+\.txt)', pedido, _re.IGNORECASE)
        fname = m.group(1) if m else "processos.txt"
        full_path = f"{desktop}\\{fname}"
        cmd = (f'Get-Process | Select-Object -ExpandProperty Name | Sort-Object -Unique | '
               f'Out-File -Encoding UTF8 "{full_path}"; Write-Host "Salvo em {full_path}"')
        return f' [Call executar_comando with this exact cmd: {cmd}]'

    # Tool única — nomeie explicitamente
    if len(tools) == 1:
        return f" [use the {tools[0]['function']['name']} tool]"

    return ""


def executar_qwen_react(pedido: str, usuario: str) -> str | None:
    """Loop ReAct: qwen age → vê resultado → age de novo. Até 5 rodadas.
    Usa subset de tools filtradas por relevância (max 3) para não confundir o modelo.
    """
    tools_filtradas = _selecionar_tools(pedido)
    nomes_tools = [t["function"]["name"] for t in tools_filtradas]
    tool_hint = _gerar_hint_sequencia(pedido, tools_filtradas)

    # Nome da tool disponível para forçar chamada explícita
    tool_name_hint = ""
    if len(tools_filtradas) == 1:
        tool_name_hint = f" You MUST call {nomes_tools[0]}."
    elif tools_filtradas:
        tool_name_hint = f" You MUST call one of: {', '.join(nomes_tools)}."

    system = (
        carregar_contexto_pc() +
        "You are Link, an autonomous PC agent on OWNER's Windows PC.\n"
        "CRITICAL: Do NOT answer from memory. Do NOT guess."
        f"{tool_name_hint}\n"
        "Call the tool to get real data, then reply to OWNER in Portuguese in one sentence.\n"
        "Use executar_comando for any OS query (IP, disk, processes, date, etc.)."
    )
    system_final = system + ("\nInstruction: " + tool_hint if tool_hint else "")
    historico = [
        {"role": "system", "content": system_final},
        {"role": "user",   "content": pedido},
    ]
    executou_alguma_tool = False
    for rodada in range(5):
        content, tool_calls = _ollama_react(historico, tools_filtradas)
        if not tool_calls:
            if executou_alguma_tool:
                log(f"QWEN ReAct finalizado em {rodada} rodadas (com tools)")
            else:
                log(f"QWEN ReAct finalizado em {rodada} rodadas (sem tools)")
            return content or None
        executou_alguma_tool = True
        for tc in tool_calls:
            fn_name = tc["function"]["name"]
            fn_args = tc["function"].get("arguments", {})
            if isinstance(fn_args, str):
                try: fn_args = json.loads(fn_args)
                except Exception: fn_args = {}
            resultado = executar_tool(fn_name, fn_args)
            log(f"QWEN [{rodada+1}] {fn_name} -> {resultado[:80]}")
            historico.append({"role": "assistant", "tool_calls": [tc], "content": None})
            historico.append({"role": "tool",
                               "tool_call_id": tc.get("id", "0"),
                               "content": resultado})
            # Ação terminal concluída → para imediatamente (evita reenvios)
            if fn_name in {"enviar_arquivo_local", "enviar_mensagem"} and "Erro" not in resultado:
                log(f"QWEN ação terminal concluída: {fn_name}")
                return resultado
    log("QWEN ReAct esgotou 5 rodadas")
    return None


def _parse_tool_calls_from_content(content: str) -> list:
    """Extrai tool calls do content em múltiplos formatos que qwen2.5:1.5b pode produzir.

    Formatos suportados:
    1. <tool_call>{"name": "fn", "arguments": {...}}</tool_call>
    2. ```json\n{"name": "fn", "arguments": {...}}\n```
    3. fn_name(arg1="val1", arg2="val2")   ← Python-style texto
    4. {"name": "fn", "arguments": {...}}   ← JSON inline
    """
    import re

    TOOL_NAMES = {t["function"]["name"] for t in TOOLS_DEFINICAO}
    result = []

    def _make_tc(name, args):
        if name not in TOOL_NAMES:
            return
        if isinstance(args, str):
            try: args = json.loads(args)
            except Exception: args = {}
        result.append({"id": str(len(result)), "type": "function",
                        "function": {"name": name, "arguments": args or {}}})

    # 1. <tool_call>JSON</tool_call>
    for m in re.finditer(r'<tool_call>\s*(\{.*?\})\s*</tool_call>', content, re.DOTALL):
        try:
            obj = json.loads(m.group(1))
            _make_tc(obj.get("name", ""), obj.get("arguments", {}))
        except Exception:
            pass

    if result:
        return result

    # 2. ```json ... ``` code block
    for m in re.finditer(r'```(?:json)?\s*(\{.*?\})\s*```', content, re.DOTALL):
        try:
            obj = json.loads(m.group(1))
            name = obj.get("name", "")
            args = obj.get("arguments", obj.get("parameters", {}))
            _make_tc(name, args)
        except Exception:
            pass

    if result:
        return result

    # 3. Python-style: fn_name(key="val", key2="val2")
    for tool_name in TOOL_NAMES:
        pat = rf'{re.escape(tool_name)}\s*\(([^)]*)\)'
        m = re.search(pat, content)
        if m:
            raw_args = m.group(1)
            args = {}
            for kv in re.finditer(r'(\w+)\s*=\s*["\']([^"\']*)["\']', raw_args):
                args[kv.group(1)] = kv.group(2)
            _make_tc(tool_name, args)

    if result:
        return result

    # 4. Whole content é JSON puro (qwen às vezes retorna só o JSON sem wrapper)
    stripped = content.strip()
    if stripped.startswith("{") and stripped.endswith("}"):
        try:
            obj = json.loads(stripped)
            name = obj.get("name", "")
            args = obj.get("arguments", obj.get("parameters", obj.get("args", {})))
            _make_tc(name, args)
            if result:
                return result
        except Exception:
            pass

    # 5. JSON inline com regex (tolera nested objects com depth=1)
    import re as _re2
    # Captura objetos JSON que contêm "name" — usa um regex mais robusto
    for m in _re2.finditer(r'\{(?:[^{}]|\{[^{}]*\})*"name"\s*:\s*"([^"]+)"(?:[^{}]|\{[^{}]*\})*\}',
                           content, _re2.DOTALL):
        try:
            obj = json.loads(m.group(0))
            _make_tc(obj.get("name",""), obj.get("arguments", obj.get("parameters", {})))
        except Exception:
            pass

    return result


def chamar_ollama_tools(pedido: str, system: str, tools: list) -> tuple[str | None, list]:
    """Tenta modelo local. Retorna (texto, tool_calls)."""
    for model in [m for m in [OLLAMA_MODEL, OLLAMA_CLOUD] if m]:
        data = _ollama_chat(model, {
            "messages": [
                {"role": "system", "content": system},
                {"role": "user",   "content": pedido},
            ],
            "tools": tools,
        })
        if data:
            msg        = data.get("message", {})
            tool_calls = msg.get("tool_calls") or []
            content    = (msg.get("content") or "").strip()
            # qwen2.5 às vezes retorna <tool_call> no content em vez de tool_calls
            if not tool_calls and content:
                tool_calls = _parse_tool_calls_from_content(content)
                if tool_calls:
                    content = ""
            log(f"Ollama [{model}] respondeu")
            return content, tool_calls
    return None, []


def chamar_ollama_simples(system: str, user: str) -> str | None:
    for model in [m for m in [OLLAMA_MODEL, OLLAMA_CLOUD] if m]:
        data = _ollama_chat(model, {
            "messages": [
                {"role": "system", "content": system},
                {"role": "user",   "content": user},
            ],
        })
        if data:
            return (data.get("message", {}).get("content") or "").strip()
    return None


def chamar_llm(system: str, user: str, max_tokens: int = 400) -> str | None:
    for model in MODELOS:
        for key in OPENROUTER_KEYS:
            payload = json.dumps({
                "model": model,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user",   "content": user},
                ],
                "max_tokens": max_tokens,
                "temperature": 0.7,
            }).encode("utf-8")
            req = urllib.request.Request(
                "https://openrouter.ai/api/v1/chat/completions",
                data=payload,
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {key}",
                    "HTTP-Referer": "http://localhost",
                },
                method="POST",
            )
            try:
                with urllib.request.urlopen(req, timeout=15) as r:
                    data = json.loads(r.read())
                usage = data.get("usage", {})
                _registrar_tokens(key, model, usage.get("prompt_tokens", 0), usage.get("completion_tokens", 0), "chamar_llm")
                return data["choices"][0]["message"]["content"].strip()
            except urllib.error.HTTPError as e:
                if e.code in (401, 403, 429):
                    continue
            except Exception:
                continue
    # Fallback Ollama/Kimi
    if ollama_disponivel():
        log("OpenRouter esgotado — fallback Ollama/Kimi")
        return chamar_ollama_simples(system, user)
    return None


# ── Executor de CLAUDE-PEDIDO ─────────────────────────────────────────────────

def _desktop_path() -> Path:
    """Retorna o caminho real do Desktop de OWNER."""
    for d in [
        Path.home() / "OneDrive - MEDSENIOR" / "Área de Trabalho",
        Path.home() / "Desktop",
        Path.home() / "OneDrive" / "Desktop",
    ]:
        if d.exists():
            return d
    return Path.home() / "Desktop"


# ── Navegação de pastas ───────────────────────────────────────────────────────

_pasta_atual: dict[str, Path] = {}  # usuario -> Path atual (reseta no restart)
_NAV_STATE_FILE = BASE / "nav_state.json"

def _salvar_nav_state(usuario: str, pasta: Path):
    """Persiste pasta atual + conteúdo real para o bot Link usar no prompt."""
    try:
        data = {}
        if _NAV_STATE_FILE.exists():
            data = json.loads(_NAV_STATE_FILE.read_text(encoding="utf-8"))
        # Lista nomes reais de pastas e arquivos (top 50, ordenado)
        itens: list[str] = []
        try:
            for p in sorted(pasta.iterdir(), key=lambda x: (not x.is_dir(), x.name.lower()))[:50]:
                itens.append(p.name)
        except Exception:
            pass
        data[usuario] = {"pasta": str(pasta), "itens": itens}
        _NAV_STATE_FILE.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    except Exception:
        pass

_ATALHOS_PASTA = {
    "desktop":    [Path.home() / "OneDrive - MEDSENIOR" / "Área de Trabalho",
                   Path.home() / "OneDrive" / "Desktop",
                   Path.home() / "Desktop"],
    "area de trabalho": [Path.home() / "OneDrive - MEDSENIOR" / "Área de Trabalho",
                         Path.home() / "Desktop"],
    "downloads":  [Path.home() / "Downloads"],
    "documentos": [Path.home() / "Documents"],
    "documents":  [Path.home() / "Documents"],
    "imagens":    [Path.home() / "Pictures"],
    "pictures":   [Path.home() / "Pictures"],
    "onedrive":   [Path.home() / "OneDrive - MEDSENIOR", Path.home() / "OneDrive"],
}

_PASTAS_BLOQUEADAS = {
    "windows", "system32", "syswow64",
    "system volume information", "$recycle.bin",
}

def _pasta_usuario(usuario: str) -> Path:
    """Retorna pasta atual do usuário, inicializando no Desktop se necessário."""
    if usuario not in _pasta_atual or not _pasta_atual[usuario].exists():
        _pasta_atual[usuario] = _desktop_path()
    return _pasta_atual[usuario]


def _is_bloqueada(path: Path) -> bool:
    """Retorna True se o caminho está em área bloqueada do sistema."""
    partes = [p.lower() for p in path.parts]
    return any(b in partes for b in _PASTAS_BLOQUEADAS)


def _emoji_arquivo(path: Path) -> str:
    ext = path.suffix.lower()
    if path.is_dir():
        return "📁"
    if ext in {".mp4", ".avi", ".mkv", ".mov", ".wmv", ".webm"}:
        return "🎬"
    if ext in {".mp3", ".wav", ".flac", ".aac", ".ogg", ".m4a"}:
        return "🎵"
    if ext in {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp", ".svg", ".ico"}:
        return "🖼️"
    if ext in {".pdf", ".doc", ".docx", ".odt"}:
        return "📄"
    if ext in {".zip", ".rar", ".7z", ".tar", ".gz"}:
        return "📦"
    if ext in {".exe", ".msi", ".bat", ".cmd", ".ps1"}:
        return "💻"
    if ext in {".xls", ".xlsx", ".csv"}:
        return "📊"
    if ext in {".py", ".js", ".ts", ".json", ".html", ".css", ".java", ".cpp", ".c"}:
        return "🧑‍💻"
    return "📝"


def _formatar_listagem(pasta: Path) -> str:
    """Lista até 30 itens de uma pasta, formatado para Discord."""
    try:
        itens = sorted(pasta.iterdir(), key=lambda x: (x.is_file(), x.name.lower()))
    except PermissionError:
        return "❌ Sem permissão para acessar essa pasta."
    except Exception as e:
        return f"❌ Erro ao listar: {e}"

    pastas_l = [i for i in itens if i.is_dir()]
    arquivos_l = [i for i in itens if i.is_file()]
    total = len(pastas_l) + len(arquivos_l)
    exibidos = (pastas_l + arquivos_l)[:30]

    linhas = [f"📂 `{pasta}`", "─────────────────"]
    for item in exibidos:
        emoji = _emoji_arquivo(item)
        if item.is_file():
            try:
                mb = item.stat().st_size / 1024 / 1024
                tamanho = f"  `{mb:.1f} MB`" if mb >= 0.1 else f"  `{item.stat().st_size} B`"
            except Exception:
                tamanho = ""
            linhas.append(f"{emoji} {item.name}{tamanho}")
        else:
            linhas.append(f"{emoji} {item.name}/")
    linhas.append("─────────────────")
    rodape = f"{len(pastas_l)} pasta(s), {len(arquivos_l)} arquivo(s)"
    if total > 30:
        rodape += f"  (mostrando 30 de {total})"
    linhas.append(rodape)
    return "\n".join(linhas)


def executar_pedido(pedido: str, usuario: str = "OWNER") -> str | None:
    """Camada 1: executa pedidos simples via Python puro, sem LLM."""
    import re as _re
    import unicodedata as _ud
    def _normalizar(t):
        return ''.join(c for c in _ud.normalize('NFD', t.lower()) if _ud.category(c) != 'Mn')
    p = pedido.lower()
    pn = _normalizar(pedido)

    # ── Navegação de pastas ───────────────────────────────────────────────────

    # ── !Link acorde — reset completo do sistema ─────────────────────────────
    if "acorde sistema completo" in pn:
        # 1. Limpa histórico em memória e disco
        chamar_api_local("/clear-history", {})
        # 2. Apaga mensagens do Discord
        for u in ["OWNER", "USER2"]:
            chamar_api_local("/delete", {"to": u, "count": 100})
        # 3. Reinicia o bot (supervisor continua rodando)
        _reiniciar_bot()
        return "sistema acordado! bot reiniciado, mensagens apagadas e memória limpa."

    # Onde estou?
    if any(x in pn for x in ["onde estou", "qual pasta estou", "caminho atual", "diretorio atual", "em qual pasta"]):
        return f"📂 Você está em:\n`{_pasta_usuario(usuario)}`"

    # Saltar para atalho conhecido (antes de listar — pedido pode ter "listar no desktop")
    def _descer_subpastas(base: Path, profundidade: int = 3) -> Path:
        """Desce níveis de subpastas enquanto encontrar nomes mencionados no pedido."""
        atual_nav = base
        for _ in range(profundidade):
            try:
                subs = [d for d in atual_nav.iterdir() if d.is_dir()]
            except Exception:
                break
            proximo = None
            for d in sorted(subs, key=lambda x: len(x.name), reverse=True):
                nome_d = _normalizar(d.name)
                if nome_d in pn and nome_d not in {_normalizar(k) for k in _ATALHOS_PASTA}:
                    proximo = d; break
            if proximo and not _is_bloqueada(proximo):
                atual_nav = proximo
            else:
                break
        return atual_nav

    for nome_atalho, caminhos in _ATALHOS_PASTA.items():
        if nome_atalho in pn:
            for c in caminhos:
                if c.exists():
                    if _is_bloqueada(c):
                        return "❌ Acesso bloqueado a essa área do sistema."
                    destino_final = _descer_subpastas(c)
                    _pasta_atual[usuario] = destino_final
                    _salvar_nav_state(usuario, destino_final)
                    return _formatar_listagem(destino_final)

    # Listar pasta atual
    if any(x in pn for x in ["o que tem", "o que esta", "lista", "listar", "mostrar arquivos",
                               "ver arquivos", "conteudo", "ver pasta", "mostrar pasta"]):
        if not any(x in pn for x in ["processo", "programa", "aberto", "rodando"]):
            return _formatar_listagem(_pasta_usuario(usuario))

    # Voltar (subir nível)
    if any(x in pn for x in ["volta", "voltar", "sair da pasta", "nivel acima", "pasta anterior", "subir pasta"]):
        atual = _pasta_usuario(usuario)
        pai = atual.parent
        if pai == atual:
            return "já estou na raiz, não dá pra subir mais."
        if _is_bloqueada(pai):
            return "❌ Acesso bloqueado a essa área do sistema."
        _pasta_atual[usuario] = pai
        _salvar_nav_state(usuario, pai)
        return _formatar_listagem(pai)

    # Entrar em pasta (por nome)
    # Entrar em pasta — estratégia: encontrar subpasta cujo nome aparece no pedido
    _verbos_nav = ["abr", "entr", "vai", "ir ", "vou", "acessa", "naveg", "open", "mostr", "ver a pasta", "quero ver"]
    _tem_intencao_nav = any(x in pn for x in _verbos_nav) or "pasta" in pn
    if _tem_intencao_nav and not _re.search(r'[A-Za-z]:\\', pedido):
        atual = _pasta_usuario(usuario)
        try:
            subpastas = [d for d in atual.iterdir() if d.is_dir()]
        except Exception:
            subpastas = []
        # Tenta match exato primeiro, depois parcial
        destino = None
        for d in subpastas:
            if _normalizar(d.name) == _normalizar(pn.strip('"').strip("'")):
                destino = d; break
        if not destino:
            for d in sorted(subpastas, key=lambda x: len(x.name), reverse=True):
                if _normalizar(d.name) in pn:
                    destino = d; break
        if not destino:
            # Busca parcial — nome da pasta contém palavra do pedido com 4+ chars
            palavras = [w for w in pn.split() if len(w) >= 4 and w not in
                        {"abra", "abre", "abrir", "pasta", "para", "minha", "nosso", "nossa", "esse", "esta", "este",
                         "aqui", "essa", "voce", "lista", "listar", "mostrar", "arquivo", "discord", "desktop"}]
            for palavra in palavras:
                for d in subpastas:
                    if palavra in _normalizar(d.name):
                        destino = d; break
                if destino:
                    break
        if not destino and subpastas:
            # Fuzzy match — cobre typos e variações ("python" → "pyton", etc.)
            import difflib as _diff
            for palavra in [w for w in pn.split() if len(w) >= 4]:
                for d in subpastas:
                    primeiro_termo = _normalizar(d.name).split()[0]
                    ratio = _diff.SequenceMatcher(None, palavra, primeiro_termo).ratio()
                    if ratio >= 0.8:
                        destino = d; break
                if destino:
                    break
        if destino:
            if _is_bloqueada(destino):
                return "❌ Acesso bloqueado a essa área do sistema."
            _pasta_atual[usuario] = destino
            _salvar_nav_state(usuario, destino)
            return _formatar_listagem(destino)

    # Enviar arquivo da pasta atual (sem caminho absoluto)
    _verbos_envia = ["me manda", "manda", "envia", "envia o", "envia a", "send", "me envia", "quero o arquivo", "me passa"]
    _tem_intencao_envia = any(x in pn for x in _verbos_envia)
    if _tem_intencao_envia and not _re.search(r'[A-Za-z]:\\', pedido):
        atual = _pasta_usuario(usuario)
        try:
            arquivos = [f for f in atual.iterdir() if f.is_file()]
        except Exception:
            arquivos = []
        # Procura nome de arquivo mencionado no pedido
        arq_destino = None
        for f in arquivos:
            if _normalizar(f.name) in pn:
                arq_destino = f; break
        if not arq_destino:
            # Busca por extensão ou nome parcial (palavras 4+ chars)
            palavras = [w for w in pn.split() if len(w) >= 3]
            for palavra in palavras:
                for f in arquivos:
                    if palavra in _normalizar(f.name):
                        arq_destino = f; break
                if arq_destino:
                    break
        if arq_destino:
            resultado = chamar_api_local("/send-file", {"to": usuario, "file": str(arq_destino)})
            return f"Arquivo '{arq_destino.name}' enviado." if resultado and resultado.get("ok") else f"Erro ao enviar '{arq_destino.name}'."

    # ── Padrão A: arquivo já baixado localmente → move para Desktop ─────────────
    # Formato: "move para desktop LOCAL:/caminho/arquivo.jpg nome:arquivo.jpg"
    if "local:" in p and any(x in p for x in ["desktop", "move", "salva"]):
        local_match = _re.search(r'LOCAL:(\S+)', pedido, _re.IGNORECASE)
        nome_match  = _re.search(r'nome:(\S+)',  pedido, _re.IGNORECASE)
        if local_match:
            src = Path(local_match.group(1))
            nome_arq = nome_match.group(1) if nome_match else src.name
            dst = _desktop_path() / nome_arq
            if src.exists():
                import shutil as _shutil
                _shutil.copy2(str(src), str(dst))
                return f"Arquivo '{nome_arq}' copiado para o Desktop."
            else:
                return f"Arquivo local não encontrado: {src}"

    # ── Padrão B: baixar de URL do Discord e salvar no Desktop ───────────────
    # Formato: "salva no desktop URL:https://... nome:arquivo.jpg"
    if "url:" in p and any(x in p for x in ["salva", "desktop", "baixa", "guarda"]):
        url_match  = _re.search(r'URL:(https?://\S+)', pedido, _re.IGNORECASE)
        nome_match = _re.search(r'nome:(\S+)',         pedido, _re.IGNORECASE)
        if url_match:
            url = url_match.group(1).rstrip(")")
            nome_arq = (nome_match.group(1).split("?")[0] if nome_match
                        else url.split("/")[-1].split("?")[0] or "arquivo.jpg")
            if "." not in nome_arq[-6:]:
                nome_arq += ".jpg"
            path = _desktop_path() / nome_arq
            try:
                import urllib.request as _ur
                req_dl = _ur.Request(url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"})
                with _ur.urlopen(req_dl, timeout=30) as resp_dl:
                    path.write_bytes(resp_dl.read())
                return f"Arquivo salvo no Desktop."
            except Exception as e:
                return f"Não consegui baixar o arquivo — tenta mandar de novo."

    # ── Padrão C: enviar arquivo do PC para o Discord ────────────────────────
    # Detecta caminho absoluto no pedido: "enviar arquivo C:\...\arquivo.ext para OWNER"
    _caminho_match = _re.search(r'(?:enviar?\s+arquivo\s+)([A-Za-z]:[^\s]+(?:\s[^\s]+)*?)(?:\s+para|\s+no\s+discord|$)', pedido, _re.IGNORECASE)
    if _caminho_match:
        caminho_arq = Path(_caminho_match.group(1).strip())
        # Corrige drive letter errado (LLM às vezes gera A:\ ou D:\ em vez de C:\)
        # Se começa com X:\Users\ e não existe, tenta C:\ automaticamente
        def _tentar_caminho(p: Path) -> Path:
            try:
                if p.exists() and p.is_file():
                    return p
            except Exception:
                pass
            # Tenta corrigir drive letter para C:
            s = str(p)
            if len(s) >= 3 and s[1] == ':' and s[0].upper() != 'C':
                c_path = Path("C:" + s[2:])
                try:
                    if c_path.exists() and c_path.is_file():
                        return c_path
                except Exception:
                    pass
            # Tenta busca case-insensitive pelo nome do arquivo na pasta pai
            try:
                pasta_pai = Path("C:" + str(p.parent)[2:]) if str(p)[1] == ':' and str(p)[0].upper() != 'C' else p.parent
                nome_alvo = _normalizar(p.name)
                for f in pasta_pai.iterdir():
                    if f.is_file() and _normalizar(f.name) == nome_alvo:
                        return f
            except Exception:
                pass
            return None
        arq_real = _tentar_caminho(caminho_arq)
        if arq_real:
            resultado = chamar_api_local("/send-file", {"to": usuario, "file": str(arq_real)})
            return f"Arquivo '{arq_real.name}' enviado no Discord." if resultado and resultado.get("ok") else f"Erro ao enviar '{arq_real.name}'."
        return f"❌ Arquivo não encontrado: {caminho_arq.name}"

    # Formato: "envia pro discord arquivo:nome.ext" ou "envia pro discord o ultimo arquivo do Desktop"
    if any(x in p for x in ["envia pro discord", "enviar pro discord", "envia pro discord"]):
        nome_match = _re.search(r'arquivo:(\S+)', pedido, _re.IGNORECASE)
        # Pastas de busca
        _pastas = [
            _desktop_path(),
            Path.home() / "Downloads",
            Path.home() / "Documents",
            Path.home() / "Pictures",
        ]
        if nome_match:
            nome_arq = nome_match.group(1)
            for pasta in _pastas:
                candidato = pasta / nome_arq
                if candidato.exists():
                    resultado = chamar_api_local("/send-file", {"to": usuario, "file": str(candidato)})
                    return f"Arquivo '{nome_arq}' enviado no Discord." if resultado and resultado.get("ok") else f"Erro ao enviar '{nome_arq}'."
            return f"Arquivo '{nome_arq}' não encontrado em Desktop/Downloads/Documents."
        else:
            # Envia o arquivo mais recente do Desktop
            desktop = _desktop_path()
            if desktop.exists():
                arquivos = sorted(desktop.iterdir(), key=lambda f: f.stat().st_mtime, reverse=True)
                recentes = [f for f in arquivos if f.is_file() and not f.name.startswith(".")][:1]
                if recentes:
                    f = recentes[0]
                    resultado = chamar_api_local("/send-file", {"to": usuario, "file": str(f)})
                    return f"Arquivo '{f.name}' enviado no Discord." if resultado and resultado.get("ok") else f"Erro ao enviar '{f.name}'."
            return "Nenhum arquivo encontrado no Desktop."

    # ── Atalhos rápidos de OS — Python puro, sem LLM ────────────────────────────
    pn = _normalizar(pedido)  # sem acentos

    # Qual o IP
    if any(x in pn for x in ["qual o ip", "meu ip", "endereco ip", "ip do pc", "ip local"]):
        r = subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             "(Get-NetIPAddress -AddressFamily IPv4 | Where-Object {$_.InterfaceAlias -notlike '*Loopback*' -and $_.InterfaceAlias -notlike '*Virtual*'} | Select-Object -First 1).IPAddress"],
            capture_output=True, env={**os.environ, "PYTHONIOENCODING": "utf-8"},
        )
        ip = r.stdout.decode("utf-8", errors="replace").strip()
        return f"Seu IP é {ip}." if ip else "Não consegui obter o IP."

    # Nome do computador
    if any(x in pn for x in ["nome do pc", "nome do computador", "qual o nome do pc",
                               "nome do meu pc", "como se chama o pc", "nome da maquina",
                               "qual e o nome do pc", "qual o nome do meu"]):
        r = subprocess.run(
            ["powershell", "-NoProfile", "-Command", "$env:COMPUTERNAME"],
            capture_output=True, env={**os.environ, "PYTHONIOENCODING": "utf-8"},
        )
        nome = r.stdout.decode("utf-8", errors="replace").strip()
        return f"Seu PC se chama {nome}." if nome else "Não consegui obter o nome."

    # Espaço em disco
    if any(x in pn for x in ["espaco livre", "disco livre", "hd livre", "ssd livre",
                               "espaco no disco", "espaco no hd", "quanto tem no hd", "quanto tem no disco"]):
        r = subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             "Get-PSDrive C | Select-Object @{N='Livre_GB';E={[math]::Round($_.Free/1GB,1)}},@{N='Total_GB';E={[math]::Round(($_.Used+$_.Free)/1GB,1)}} | Format-List"],
            capture_output=True, env={**os.environ, "PYTHONIOENCODING": "utf-8"},
        )
        out = r.stdout.decode("utf-8", errors="replace").strip()
        return out if out else "Não consegui verificar o disco."

    # Listar processos rodando
    if any(x in pn for x in ["quais programas", "quais processos", "o que ta rodando",
                               "programas abertos", "processos abertos", "lista os processos",
                               "listar processos"]):
        r = subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             "Get-Process | Select-Object -ExpandProperty Name | Sort-Object -Unique | Where-Object {$_ -notin @('Idle','System')}"],
            capture_output=True, env={**os.environ, "PYTHONIOENCODING": "utf-8"},
        )
        procs = r.stdout.decode("utf-8", errors="replace").strip()
        nomes = [x for x in procs.splitlines() if x.strip()][:30]
        return "Rodando agora: " + ", ".join(nomes) if nomes else "Não consegui listar processos."

    # Listar arquivos do Desktop (qwen alucina listas; Python é mais confiável)
    if any(x in pn for x in ["o que tem na area de trabalho", "o que tem no desktop",
                               "o que tem na minha area", "lista o desktop",
                               "arquivos do desktop", "arquivos na area de trabalho"]):
        desktop = _desktop_path()
        if desktop.exists():
            items = sorted(desktop.iterdir(), key=lambda f: f.stat().st_mtime, reverse=True)
            nomes_arq = [f"[{'pasta' if i.is_dir() else 'arquivo'}] {i.name}" for i in items[:20] if not i.name.startswith(".")]
            return "Desktop:\n" + "\n".join(nomes_arq) if nomes_arq else "Desktop vazio."
        return "Desktop não encontrado."

    # ── Padrão: criar arquivo de texto no Desktop com dados do sistema ──────────
    # Ex: "cria um txt no Desktop chamado processos.txt com a lista de processos rodando"
    if any(x in p for x in ["cria", "criar", "gera", "gerar", "salva", "salvar"]):
        if any(x in p for x in ["txt", "arquivo"]):
            # Extrai nome do arquivo
            m = _re.search(r'(?:chamado|chamada|nome|arquivo)\s+(\S+\.(?:txt|csv|log|md))', pedido, _re.IGNORECASE)
            fname = m.group(1) if m else None

            # Criar arquivo com lista de processos
            if any(x in p for x in ["processo", "processos", "rodando", "aberto", "ativo"]) and fname:
                r = subprocess.run(
                    ["powershell", "-NoProfile", "-Command",
                     "Get-Process | Select-Object -ExpandProperty Name | Sort-Object -Unique"],
                    capture_output=True, env={**os.environ, "PYTHONIOENCODING": "utf-8"},
                )
                conteudo = r.stdout.decode("utf-8", errors="replace").strip()
                desktop = _desktop_path()
                path = desktop / fname
                path.write_text(conteudo, encoding="utf-8")
                return f"Arquivo '{fname}' criado no Desktop com {len(conteudo.splitlines())} processos."

            # Criar arquivo com saída de ipconfig/rede
            if any(x in p for x in ["ip", "rede", "ipconfig", "network"]) and fname:
                r = subprocess.run(
                    ["powershell", "-NoProfile", "-Command", "ipconfig"],
                    capture_output=True, env={**os.environ, "PYTHONIOENCODING": "utf-8"},
                )
                conteudo = r.stdout.decode("utf-8", errors="replace").strip()
                desktop = _desktop_path()
                path = desktop / fname
                path.write_text(conteudo, encoding="utf-8")
                return f"Arquivo '{fname}' criado no Desktop com informações de rede."

    # Apagar/excluir mensagens do bot
    if any(x in p for x in ["apag", "exclu", "delet", "remov"]) and "mensag" in p:
        # Determina usuário alvo (padrão: OWNER)
        usuario = "USER2" if "user2" in p else "OWNER"

        # Descobre o escopo temporal: hoje, ontem, ambos, ou tudo
        hoje     = time.strftime("%d/%m/%Y")
        ontem    = time.strftime("%d/%m/%Y", time.localtime(time.time() - 86400))
        datas_alvo = set()
        if "hoje" in p:
            datas_alvo.add(hoje)
        if "ontem" in p:
            datas_alvo.add(ontem)
        if not datas_alvo:  # pedido genérico: apaga tudo
            datas_alvo = None

        # Busca histórico
        resp = chamar_api_local(f"/history?user={usuario}&limit=500", metodo="GET")
        if not resp or not resp.get("ok"):
            return "Não consegui acessar o histórico de mensagens."

        mensagens = resp.get("mensagens", [])
        if datas_alvo:
            ids = [m["id"] for m in mensagens if m["meu"] and any(d in m["data"] for d in datas_alvo)]
        else:
            ids = [m["id"] for m in mensagens if m["meu"]]

        if not ids:
            return "Nenhuma mensagem minha encontrada no período."

        resultado = chamar_api_local("/delete", {"to": usuario, "ids": ids})
        if not resultado:
            return "Erro ao tentar apagar as mensagens."

        deletadas = resultado.get("deletadas", 0)
        erros     = resultado.get("erros", [])
        resposta  = f"Apaguei {deletadas} mensagem(ns)."
        if erros:
            resposta += f" ({len(erros)} erro(s))"
        log(f"DELETE {usuario}: {deletadas} msgs apagadas, {len(erros)} erros")
        return resposta

    # Listar programas abertos — só se não há intenção de salvar/criar arquivo (deixa pro qwen)
    if (any(x in p for x in ["programa", "aberto", "rodando", "processo", "abertos"])
            and not any(x in p for x in ["cria", "criar", "salva", "salvar", "arquivo", "txt", "escreve"])):
        r = subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             "[Console]::OutputEncoding=[System.Text.Encoding]::UTF8; "
             "Get-Process | Select-Object -ExpandProperty Name | Sort-Object -Unique"],
            capture_output=True,
            env={**os.environ, "PYTHONIOENCODING": "utf-8"},
        )
        nomes = r.stdout.decode("utf-8", errors="replace").strip().splitlines()
        filtro = ["chrome","firefox","msedge","teams","outlook","winword","excel",
                  "powerpnt","notepad","code","python","teamviewer","discord",
                  "spotify","zoom","slack","explorer","windowsterminal","claude","opencode"]
        apps = sorted(set(n for n in nomes if any(f in n.lower() for f in filtro)))
        return "Programas abertos:\n" + ", ".join(apps) if apps else "Nenhum app relevante encontrado."

    # Busca de imagem na web — entrega direto sem LLM
    _quer_imagem = any(x in p for x in ["imagem", "foto", "png", "jpg", "figura", "artwork", "arte", "ilustra"])
    _quer_web    = any(x in p for x in ["busca", "pesquis", "procura", "acha", "web", "internet", "online"])
    if _quer_imagem and _quer_web:
        # extrai o termo: tudo depois de "de " / "do " / "da " no pedido
        m = _re.search(r'(?:de|do|da|por|sobre)\s+(.+)$', pedido, _re.IGNORECASE)
        termo_img = m.group(1).strip().strip('"') if m else pedido
        url_img = buscar_imagem(termo_img)
        if url_img.startswith("http"):
            filename = _normalizar(termo_img).replace(" ", "_") + ".png"
            dl = chamar_api_local("/download", {"url": url_img, "filename": filename})
            if dl and dl.get("ok"):
                caminho = dl["path"]
                send = chamar_api_local("/send-file", {"to": usuario, "file": caminho.replace("\\", "/"), "msg": termo_img})
                if send and send.get("ok"):
                    return f"Imagem de '{termo_img}' enviada!"
                return f"Baixei a imagem mas erro ao enviar: {send}"
            return f"Erro ao baixar imagem: {dl}"
        return url_img  # mensagem de erro do buscar_imagem

    # Ler arquivo
    if any(x in p for x in ["ler", "arquivo", "conteudo", "conteúdo", "trazer", "senha", "credencial"]):
        # Extrai nome do arquivo do pedido
        palavras = pedido.replace(",", " ").replace(".", " ").split()
        candidatos = [w for w in palavras if "." in w and len(w) > 3]

        desktop_paths = [
            Path.home() / "Desktop",
            Path.home() / "OneDrive - MEDSENIOR" / "Área de Trabalho",
            Path.home() / "OneDrive" / "Desktop",
        ]
        for nome_arq in candidatos:
            for base_path in desktop_paths:
                caminho = base_path / nome_arq
                if caminho.exists():
                    return caminho.read_text(encoding="utf-8", errors="replace").strip()
        # busca recursiva
        for nome_arq in candidatos:
            for base_path in desktop_paths:
                if base_path.exists():
                    encontrados = list(base_path.rglob(f"*{nome_arq}*"))
                    if encontrados:
                        return encontrados[0].read_text(encoding="utf-8", errors="replace").strip()
        return f"Arquivo não encontrado para o pedido: {pedido}"

    # Fechar programa
    if any(x in p for x in ["fechar", "feche", "encerrar", "kill", "matar"]):
        palavras = pedido.split()
        for w in palavras:
            try:
                subprocess.run(["taskkill", "/IM", w, "/F"], capture_output=True)
                return f"Processo '{w}' encerrado."
            except Exception:
                pass
        return "Não consegui identificar o processo para encerrar."

    # Abrir programa
    if any(x in p for x in ["abrir", "abra", "abre", "iniciar", "inicie"]):
        mapa = {
            "chrome": "chrome.exe",
            "notepad": "notepad.exe",
            "bloco de notas": "notepad.exe",
            "calculadora": "calc.exe",
            "explorador": "explorer.exe",
            "teams": "ms-teams.exe",
        }
        for nome, exe in mapa.items():
            if nome in p:
                subprocess.Popen([exe], shell=True)
                return f"{nome.capitalize()} aberto."
        return "Não identifiquei qual programa abrir."

    # Pedido genérico — usa LLM para gerar resposta
    return None


def enfileirar_para_claude(pedido: str, usuario: str):
    """Escreve pedido na fila do Claude Code e notifica o usuário no Discord."""
    fila = []
    if CLAUDE_QUEUE.exists():
        try:
            fila = json.loads(CLAUDE_QUEUE.read_text(encoding="utf-8"))
        except Exception:
            fila = []
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    item_id = f"{int(time.time())}_{usuario}"
    fila.append({"ts": ts, "id": item_id, "pedido": pedido, "usuario": usuario})
    CLAUDE_QUEUE.write_text(json.dumps(fila, ensure_ascii=False, indent=2), encoding="utf-8")
    log(f"FILA -> Claude Code: {pedido[:80]}")
    # Notifica usuário imediatamente no Discord
    chamar_api_local("/send", {"to": usuario, "msg": "⚙️ triforce acionada — processando, aguarde..."})


def buscar_internet(query: str) -> str:
    """Busca no DuckDuckGo Instant Answer API (sem JS, sem rate limit agressivo)."""
    try:
        url = f"https://api.duckduckgo.com/?q={urllib.request.quote(query)}&format=json&no_html=1&skip_disambig=1"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"})
        with urllib.request.urlopen(req, timeout=10) as r:
            data = json.loads(r.read())
        abstract = data.get("AbstractText", "").strip()
        answer   = data.get("Answer", "").strip()
        related  = [r["Text"] for r in data.get("RelatedTopics", [])[:3] if "Text" in r]
        if abstract:
            return abstract[:400]
        if answer:
            return answer[:400]
        if related:
            return "\n".join(related)[:400]
        return f"Sem resultado direto para '{query}'. Tente reformular."
    except Exception as e:
        return f"Erro na busca: {e}"


def buscar_imagem(termo: str, wiki: str = "zelda") -> str:
    """Busca URL direta de imagem. Fluxo:
    1. Hyrule Compendium API (BOTW/TOTK) — slug lowercase+underscore
    2. Fandom Zelda pageimages original — imagem principal da página do item
    3. Wikimedia Commons generator=search namespace=6 — fallback genérico
    Retorna URL direta ou mensagem de erro.
    """
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    slug    = termo.lower().replace(" ", "_")
    title   = termo.replace(" ", "_").title()

    # 1. Hyrule Compendium (BOTW/TOTK) — endpoint JSON retorna data.image
    try:
        api = f"https://botw-compendium.herokuapp.com/api/v3/compendium/entry/{urllib.request.quote(slug)}"
        req = urllib.request.Request(api, headers=headers)
        with urllib.request.urlopen(req, timeout=8) as r:
            data = json.loads(r.read())
        img = data.get("data", {}).get("image", "")
        if img and data.get("status") != 404:
            log(f"buscar_imagem: Compendium OK → {img}")
            return img
    except Exception as e:
        log(f"buscar_imagem: Compendium falhou → {e}")

    # 2. Fandom Zelda — pageimages&piprop=original (imagem principal da página, full-size)
    if wiki != "commons":
        try:
            api = (
                f"https://zelda.fandom.com/api.php?action=query"
                f"&titles={urllib.request.quote(title)}&prop=pageimages"
                f"&piprop=original&format=json"
            )
            req = urllib.request.Request(api, headers=headers)
            with urllib.request.urlopen(req, timeout=8) as r:
                data = json.loads(r.read())
            pages = data.get("query", {}).get("pages", {})
            for page in pages.values():
                src = page.get("original", {}).get("source", "")
                if src:
                    log(f"buscar_imagem: Fandom pageimages OK → {src}")
                    return src
        except Exception as e:
            log(f"buscar_imagem: Fandom pageimages falhou → {e}")

        # 2b. Fandom allimages prefix — fallback se página não tem imagem principal
        try:
            prefix = urllib.request.quote(title)
            api = (
                f"https://zelda.fandom.com/api.php?action=query"
                f"&list=allimages&aiprefix={prefix}&aiprop=url&ailimit=8&format=json"
            )
            req = urllib.request.Request(api, headers=headers)
            with urllib.request.urlopen(req, timeout=8) as r:
                data = json.loads(r.read())
            _skip = {"icon", "thumb", "logo", "button", "arrow", "sprite", "map"}
            for img in data.get("query", {}).get("allimages", []):
                name = img.get("name", "").lower()
                if any(x in name for x in _skip):
                    continue
                url = img.get("url", "")
                if url:
                    log(f"buscar_imagem: Fandom allimages OK → {url}")
                    return url
        except Exception as e:
            log(f"buscar_imagem: Fandom allimages falhou → {e}")

    # 3. Wikimedia Commons — generator=search namespace=6 (arquivos/imagens)
    try:
        query = urllib.request.quote(termo)
        api = (
            f"https://commons.wikimedia.org/w/api.php?action=query"
            f"&generator=search&gsrsearch={query}&gsrnamespace=6"
            f"&prop=imageinfo&iiprop=url&gsrlimit=5&format=json"
        )
        req = urllib.request.Request(api, headers=headers)
        with urllib.request.urlopen(req, timeout=8) as r:
            data = json.loads(r.read())
        _img_ext = (".png", ".jpg", ".jpeg", ".webp", ".gif", ".svg")
        for page in data.get("query", {}).get("pages", {}).values():
            for info in page.get("imageinfo", []):
                url = info.get("url", "")
                if url and any(url.lower().endswith(x) for x in _img_ext):
                    log(f"buscar_imagem: Commons OK → {url}")
                    return url
    except Exception as e:
        log(f"buscar_imagem: Commons falhou → {e}")

    return f"Nenhuma imagem encontrada para '{termo}'."


def executar_tool(nome: str, args: dict) -> str:
    """Executa uma tool chamada pelo agente LLM e retorna o resultado."""
    try:
        if nome == "apagar_mensagens":
            usuario   = args.get("usuario", "OWNER")
            data_str  = args.get("data", "hoje").lower()
            hoje  = time.strftime("%d/%m/%Y")
            ontem = time.strftime("%d/%m/%Y", time.localtime(time.time() - 86400))
            datas_alvo = set()
            if "hoje"  in data_str: datas_alvo.add(hoje)
            if "ontem" in data_str: datas_alvo.add(ontem)
            resp = chamar_api_local(f"/history?user={usuario}&limit=500", metodo="GET")
            if not resp or not resp.get("ok"):
                return "Erro ao acessar historico."
            mensagens = resp.get("mensagens", [])
            ids = [m["id"] for m in mensagens if m["meu"] and (not datas_alvo or any(d in m["data"] for d in datas_alvo))]
            if not ids:
                return "Nenhuma mensagem encontrada no periodo."
            resultado = chamar_api_local("/delete", {"to": usuario, "ids": ids})
            deletadas = resultado.get("deletadas", 0) if resultado else 0
            return f"{deletadas} mensagens apagadas."

        elif nome == "buscar_internet":
            return buscar_internet(args.get("query", ""))

        elif nome == "buscar_imagem":
            return buscar_imagem(args.get("termo", ""), args.get("wiki", "zelda"))

        elif nome == "listar_processos":
            r = subprocess.run(
                ["powershell", "-NoProfile", "-Command",
                 "[Console]::OutputEncoding=[System.Text.Encoding]::UTF8; "
                 "Get-Process | Select-Object -ExpandProperty Name | Sort-Object -Unique"],
                capture_output=True, env={**os.environ, "PYTHONIOENCODING": "utf-8"},
            )
            nomes = r.stdout.decode("utf-8", errors="replace").strip().splitlines()
            filtro = ["chrome","firefox","msedge","teams","outlook","winword","excel",
                      "powerpnt","notepad","code","python","discord","spotify","zoom",
                      "slack","explorer","windowsterminal","claude","opencode"]
            apps = sorted(set(n for n in nomes if any(f in n.lower() for f in filtro)))
            return "Processos: " + ", ".join(apps) if apps else "Nenhum app relevante."

        elif nome == "ler_arquivo":
            caminho = Path(args.get("caminho", ""))
            if caminho.exists():
                return caminho.read_text(encoding="utf-8", errors="replace")[:1000]
            return f"Arquivo nao encontrado: {caminho}"

        elif nome == "abrir_programa":
            mapa = {"chrome":"chrome.exe","notepad":"notepad.exe","calculadora":"calc.exe",
                    "bloco de notas":"notepad.exe","explorador":"explorer.exe","teams":"ms-teams.exe"}
            nome_prog = args.get("nome","").lower()
            exe = mapa.get(nome_prog, nome_prog)
            subprocess.Popen([exe], shell=True)
            return f"{nome_prog} aberto."

        elif nome == "fechar_programa":
            proc = args.get("nome","")
            subprocess.run(["taskkill", "/IM", proc, "/F"], capture_output=True)
            return f"{proc} encerrado."

        elif nome == "enviar_mensagem":
            usuario  = args.get("usuario", "OWNER")
            mensagem = args.get("mensagem", "")
            res = chamar_api_local("/send", {"to": usuario, "msg": mensagem})
            return f"Mensagem enviada para {usuario}." if res and res.get("ok") else f"Erro ao enviar: {res}"

        elif nome == "baixar_e_enviar":
            url      = args.get("url","")
            filename = args.get("filename","") or url.split("/")[-1].split("?")[0] or "arquivo"
            usuario  = args.get("usuario","OWNER")
            msg      = args.get("msg","")
            # 1. Baixa o arquivo
            dl = chamar_api_local("/download", {"url": url, "filename": filename})
            if not dl or not dl.get("ok"):
                return f"Erro ao baixar: {dl}"
            caminho = dl.get("path","")
            tamanho = dl.get("tamanho_mb", 0)
            # 2. Envia pelo Discord
            send = chamar_api_local("/send-file", {"to": usuario, "file": caminho, "msg": msg})
            if send and send.get("ok"):
                return f"Arquivo '{filename}' ({tamanho}MB) enviado para {usuario}."
            return f"Arquivo baixado mas erro ao enviar: {send}"

        elif nome == "salvar_no_desktop":
            url      = args.get("url", "")
            filename = args.get("filename", "") or url.split("/")[-1].split("?")[0] or "arquivo"
            profile  = Path(os.environ.get("USERPROFILE", "C:/Users/OWNER"))
            # Tenta Desktop padrão e OneDrive
            for candidate in [
                profile / "Desktop" / filename,
                profile / "OneDrive - MEDSENIOR" / "Área de Trabalho" / filename,
            ]:
                if candidate.parent.exists():
                    desktop = candidate
                    break
            else:
                desktop = profile / "Desktop" / filename
                desktop.parent.mkdir(parents=True, exist_ok=True)
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"})
            with urllib.request.urlopen(req, timeout=30) as r:
                desktop.write_bytes(r.read())
            return f"Arquivo '{filename}' salvo no Desktop."

        elif nome == "executar_comando":
            cmd     = args.get("cmd", "")
            timeout = min(int(args.get("timeout", 15)), 60)
            # Bloqueia comandos Unix que qwen às vezes gera por engano no Windows
            _unix_cmds = ["mkdir -p", "touch ", "rm -rf", "ls -", "cat ", "grep ", "sed ", "awk ",
                          "df -", "find /", "chmod ", "chown ", "echo $"]
            if any(u in cmd for u in _unix_cmds):
                return f"Erro: comando Unix detectado ('{cmd[:40]}...'). Use PowerShell/Windows."
            r = subprocess.run(
                ["powershell", "-NoProfile", "-Command", cmd],
                capture_output=True, timeout=timeout,
                env={**os.environ, "PYTHONIOENCODING": "utf-8"},
            )
            out = r.stdout.decode("utf-8", errors="replace").strip()
            err = r.stderr.decode("utf-8", errors="replace").strip()
            return (out or err or "Comando executado sem output.")[:800]

        elif nome == "escrever_arquivo":
            raw = args.get("caminho", "")
            # Normaliza caminhos relativos ou incompletos para o Desktop real
            _desktops = [
                Path.home() / "OneDrive - MEDSENIOR" / "Área de Trabalho",
                Path.home() / "Desktop",
                Path.home() / "OneDrive" / "Desktop",
            ]
            _desktop = next((d for d in _desktops if d.exists()), Path.home() / "Desktop")
            raw_low = raw.replace("\\", "/").lower()
            # Se o caminho menciona "desktop" mas não é absoluto válido, redireciona
            if ("desktop" in raw_low or raw_low.startswith("/desktop") or raw_low.startswith("\\desktop")) and not Path(raw).exists():
                nome_arq = Path(raw).name
                path = _desktop / nome_arq
            elif raw and Path(raw).is_absolute():
                path = Path(raw)
            else:
                # Caminho relativo: salva no Desktop
                path = _desktop / (Path(raw).name or "arquivo.txt")
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(args.get("conteudo", ""), encoding="utf-8")
            return f"Arquivo '{path.name}' salvo em {path.parent}."

        elif nome == "listar_arquivos":
            p = Path(args.get("caminho", str(Path.home())))
            if not p.exists():
                return f"Pasta não encontrada: {p}"
            items = sorted(p.iterdir(), key=lambda x: (x.is_file(), x.name))
            linhas = [f"{'[D]' if i.is_dir() else '[A]'} {i.name}" for i in items[:50]]
            return "\n".join(linhas) or "Pasta vazia."

        elif nome == "editar_mensagem":
            return (chamar_api_local("/edit", {
                "to": args.get("usuario", "OWNER"),
                "msg_id": args.get("msg_id", ""),
                "novo_conteudo": args.get("novo_conteudo", ""),
            }) or {}).get("ok") and "Mensagem editada." or "Erro ao editar mensagem."

        elif nome == "reagir_mensagem":
            res = chamar_api_local("/react", {
                "to": args.get("usuario", "OWNER"),
                "msg_id": args.get("msg_id", ""),
                "emoji": args.get("emoji", "👍"),
            })
            return "Reação adicionada." if res and res.get("ok") else f"Erro: {res}"

        elif nome == "fixar_mensagem":
            res = chamar_api_local("/pin", {
                "to": args.get("usuario", "OWNER"),
                "msg_id": args.get("msg_id", ""),
            })
            return "Mensagem fixada." if res and res.get("ok") else f"Erro: {res}"

        elif nome == "enviar_arquivo_local":
            caminho = args.get("caminho", "")
            usuario_arq = args.get("usuario", "OWNER")
            msg = args.get("msg", "")
            if not caminho:
                return "Caminho do arquivo não informado."
            p = Path(caminho)
            if not p.exists():
                return f"Arquivo não encontrado: {caminho}"
            payload = {"to": usuario_arq, "file": str(p)}
            if msg:
                payload["msg"] = msg
            res = chamar_api_local("/send-file", payload)
            if res and res.get("ok"):
                return f"Arquivo '{p.name}' enviado."
            if res and res.get("error") == "arquivo_grande":
                mb = res.get("tamanho_mb", "?")
                return f"ERRO_ARQUIVO_GRANDE: {p.name} tem {mb}MB — limite do Discord é 8MB."
            return f"Erro ao enviar: {res}"

        return f"Tool desconhecida: {nome}"
    except Exception as e:
        return f"Erro ao executar {nome}: {e}"


def chamar_agente_tools(pedido: str, usuario: str) -> str | None:
    """
    Chama o LLM com tool calling. Executa as tools chamadas e devolve
    o resultado ao modelo ate gerar resposta final. Max 3 rodadas.
    Retorna a resposta final ou None se falhar/precisar do Claude Code.
    """
    system = (
        "Voce e o agente Hyrule Supervisor, rodando no PC do OWNER.\n"
        "Use as tools disponiveis para resolver o pedido.\n"
        "Se nao conseguir resolver com as tools, responda: ESCALAR_CLAUDE\n"
        "Responda em portugues, de forma breve e direta."
    )
    messages = [
        {"role": "system", "content": system},
        {"role": "user",   "content": pedido},
    ]

    for modelo in MODELOS:
        for key in OPENROUTER_KEYS:
            msgs = list(messages)
            for rodada in range(3):
                payload = json.dumps({
                    "model":       modelo,
                    "messages":    msgs,
                    "tools":       TOOLS_DEFINICAO,
                    "tool_choice": "auto",
                    "max_tokens":  300,
                    "temperature": 0.3,
                }).encode("utf-8")
                req = urllib.request.Request(
                    "https://openrouter.ai/api/v1/chat/completions",
                    data=payload,
                    headers={
                        "Content-Type":  "application/json",
                        "Authorization": f"Bearer {key}",
                        "HTTP-Referer":  "http://localhost",
                    },
                    method="POST",
                )
                try:
                    with urllib.request.urlopen(req, timeout=20) as r:
                        data     = json.loads(r.read())
                    usage = data.get("usage", {})
                    _registrar_tokens(key, modelo, usage.get("prompt_tokens", 0), usage.get("completion_tokens", 0), "chamar_agente_tools")
                    msg      = data["choices"][0]["message"]
                    tool_calls = msg.get("tool_calls", [])

                    if not tool_calls:
                        # Resposta final em texto
                        texto = msg.get("content", "").strip()
                        if "ESCALAR_CLAUDE" in texto or not texto:
                            return None
                        log(f"AGENTE [{modelo.split('/')[-1].split(':')[0]}] resolveu: {pedido[:50]}")
                        return texto

                    # Executa cada tool chamada
                    msgs.append({"role": "assistant", "tool_calls": tool_calls, "content": None})
                    for tc in tool_calls:
                        fn_name = tc["function"]["name"]
                        fn_args = json.loads(tc["function"]["arguments"])
                        resultado_tool = executar_tool(fn_name, fn_args)
                        log(f"TOOL {fn_name}({fn_args}) -> {resultado_tool[:60]}")
                        msgs.append({
                            "role":         "tool",
                            "tool_call_id": tc["id"],
                            "content":      resultado_tool,
                        })
                        # Ação terminal concluída → para imediatamente (evita reenvios)
                        if fn_name in {"enviar_arquivo_local", "enviar_mensagem"} and "Erro" not in resultado_tool:
                            log(f"AGENTE ação terminal concluída: {fn_name}")
                            return resultado_tool

                except urllib.error.HTTPError as e:
                    if e.code in (401, 403, 429):
                        break  # tenta próxima chave/modelo
                except Exception:
                    break
            else:
                continue
            break  # saiu do loop de chaves sem erro — tenta próximo modelo se necessário

    # Fallback Groq — entra quando OpenRouter todo falha (0.3s latência)
    system_groq = (
        "Voce e o agente Hyrule Supervisor, rodando no PC do OWNER.\n"
        "Use as tools disponiveis para resolver o pedido.\n"
        "Responda em portugues, de forma breve e direta."
    )
    content_groq, tool_calls_groq = chamar_groq_tools(pedido, system_groq, TOOLS_DEFINICAO)
    if tool_calls_groq or content_groq:
        if tool_calls_groq:
            for tc in tool_calls_groq:
                fn_name = tc["function"]["name"]
                fn_args = tc["function"].get("arguments", {})
                if isinstance(fn_args, str):
                    fn_args = json.loads(fn_args)
                resultado_tool = executar_tool(fn_name, fn_args)
                log(f"GROQ TOOL {fn_name} -> {resultado_tool[:60]}")
                # Ação terminal concluída → para imediatamente (evita reenvios)
                if fn_name in {"enviar_arquivo_local", "enviar_mensagem"} and "Erro" not in resultado_tool:
                    return resultado_tool
            return resultado_tool
        return content_groq

    # Fallback Ollama → kimi-k2.5:cloud — API nuvem Moonshot roteada pelo Ollama
    # (entra quando OpenRouter e Groq falham)
    if ollama_disponivel():
        log("OpenRouter esgotado — fallback Ollama/qwen (tools)")
        system = (
            "You are a tool-calling agent. You MUST call a tool to resolve the user request.\n"
            "Do NOT explain. Do NOT refuse. Just call the correct tool with the correct arguments."
        )
        msgs_ollama = [
            {"role": "system", "content": system},
            {"role": "user",   "content": pedido},
        ]
        for rodada in range(3):
            content, tool_calls = chamar_ollama_tools(pedido if rodada == 0 else "", system, TOOLS_DEFINICAO)
            if tool_calls:
                msgs_ollama.append({"role": "assistant", "content": content, "tool_calls": tool_calls})
                for tc in tool_calls:
                    fn_name = tc["function"]["name"]
                    fn_args = tc["function"].get("arguments", {})
                    if isinstance(fn_args, str):
                        fn_args = json.loads(fn_args)
                    resultado_tool = executar_tool(fn_name, fn_args)
                    log(f"OLLAMA TOOL {fn_name} -> {resultado_tool[:60]}")
                    msgs_ollama.append({
                        "role":         "tool",
                        "tool_call_id": tc.get("id", "0"),
                        "content":      resultado_tool,
                    })
                # pede resposta final
                payload = json.dumps({"model": OLLAMA_MODEL, "messages": msgs_ollama, "stream": False}).encode()
                req = urllib.request.Request(OLLAMA_URL, data=payload, headers={"Content-Type": "application/json"}, method="POST")
                try:
                    with urllib.request.urlopen(req, timeout=60) as r:
                        data    = json.loads(r.read())
                    content = data.get("message", {}).get("content", "").strip()
                except Exception:
                    content = resultado_tool  # usa resultado da tool direto
            if content:
                log(f"OLLAMA resolveu: {pedido[:50]}")
                return content
            if not tool_calls:
                break

    return None


def responder_pedido(pedido: str, usuario: str, sem_triforce: bool = False):
    log(f"PEDIDO: {pedido}")

    # 1. Execução local simples (sem LLM)
    resultado = executar_pedido(pedido, usuario)
    if resultado:
        enviar_discord(usuario, resultado)
        return

    # 2. Link Discord (qwen local) — ReAct loop, executor principal
    if ollama_disponivel():
        resultado_react = executar_qwen_react(pedido, usuario)
        if resultado_react:
            enviar_discord(usuario, resultado_react)
            return

    # 3. Fallback OpenRouter (se Ollama indisponível)
    resultado_agente = chamar_agente_tools(pedido, usuario)
    if resultado_agente:
        enviar_discord(usuario, resultado_agente)
        return

    # 4. Groq direto
    try:
        tools_g = _selecionar_tools(pedido)
        system_g = "Você é um assistente pessoal. Responda de forma direta em português."
        resp_g, _ = chamar_groq_tools(pedido, system_g, tools_g)
        if resp_g:
            enviar_discord(usuario, resp_g)
            return
    except Exception:
        pass

    if sem_triforce:
        enviar_discord(usuario, "⚠️ não consegui processar agora, tente novamente.")
        return

    # 5. Escala pro Claude Code só se tudo falhar
    enfileirar_para_claude(pedido, usuario)  # já envia notificação ao usuário


# ── Corretor de respostas ruins ───────────────────────────────────────────────

def eh_ruim(texto: str) -> bool:
    t = texto.lower()
    return any(p in t for p in PADROES_RUINS)


def corrigir_resposta(msg_original: str, resposta_ruim: str, usuario: str):
    log(f"RESPOSTA RUIM detectada: {resposta_ruim[:60]}")
    persona = PERSONA_FILE.read_text(encoding="utf-8") if PERSONA_FILE.exists() else ""
    system = (
        f"{persona}\n\n"
        "A resposta anterior foi inadequada — voce recusou o pedido do OWNER.\n"
        "Isso e errado. Gere agora uma resposta CORRETA.\n"
        "Se precisar de acao no PC, use [SHEIKAH_SLATE: descricao da tarefa].\n"
        "NUNCA recuse pedidos do OWNER."
    )
    correcao = chamar_llm(system=system, user=msg_original)
    if correcao:
        enviar_discord(usuario, correcao)


# ── Monitor principal ─────────────────────────────────────────────────────────

PEDIDOS_VISTOS_FILE = BASE / "pedidos_vistos.json"
PEDIDOS_TTL_SEGUNDOS = 600  # 10 minutos — após isso o mesmo pedido pode ser reexecutado


def carregar_pedidos_vistos() -> dict:
    """Carrega pedidos já processados do disco. Formato: {texto: timestamp}."""
    if PEDIDOS_VISTOS_FILE.exists():
        try:
            data = json.loads(PEDIDOS_VISTOS_FILE.read_text(encoding="utf-8"))
            if isinstance(data, list):
                # Compat com formato antigo (lista de strings) — atribui timestamp atual
                return {p: time.time() for p in data}
            if isinstance(data, dict):
                return data
        except Exception:
            pass
    return {}


def salvar_pedidos_vistos(pedidos_vistos: dict):
    """Persiste pedidos vistos no disco, removendo os expirados."""
    agora = time.time()
    limpos = {p: ts for p, ts in pedidos_vistos.items()
              if agora - ts < PEDIDOS_TTL_SEGUNDOS}
    try:
        # Mantém só os 500 mais recentes por timestamp
        entries = sorted(limpos.items(), key=lambda x: x[1])[-500:]
        PEDIDOS_VISTOS_FILE.write_text(json.dumps(dict(entries)), encoding="utf-8")
    except Exception:
        pass


def pedido_ja_visto(pedidos_vistos: dict, pedido: str) -> bool:
    """Retorna True se o pedido foi visto recentemente (dentro do TTL)."""
    ts = pedidos_vistos.get(pedido)
    if ts is None:
        return False
    if time.time() - ts > PEDIDOS_TTL_SEGUNDOS:
        pedidos_vistos.pop(pedido, None)
        return False
    return True


def processar_backlog(pedidos_vistos: set, ultima_msg: dict, janela_minutos: int = 2):
    """Processa pedidos SHEIKAH_SLATE que chegaram nos últimos janela_minutos antes do supervisor subir.
    Marca TODOS os pedidos históricos como vistos para não reprocessar ao reiniciar.
    """
    if not LOG_FILE.exists():
        return

    linhas = LOG_FILE.read_text(encoding="utf-8", errors="replace").splitlines()

    agora = time.time()

    ultimo_usuario = "DISCORD_OWNER_USERNAME"
    pedidos_recentes = []  # (pedido, usuario) dentro da janela

    # Passa uma vez: coleta recentes e rastreia usuário; marca históricos como vistos
    for linha in linhas[-200:]:
        linha = linha.strip()
        if not linha:
            continue

        if "[IN]" in linha and "-> Link:" in linha:
            try:
                usuario = linha.split("[IN] ")[1].split(" ->")[0].strip()
                msg     = linha.split("-> Link: ", 1)[1].strip()
                ultima_msg[usuario] = msg
                ultimo_usuario = usuario
            except Exception:
                pass

        elif "[SYS]" in linha and "[SHEIKAH_SLATE-PEDIDO]" in linha:
            try:
                pedido = linha.split("[SHEIKAH_SLATE-PEDIDO] ")[1].strip()
                ts_str = linha[1:20]
                chave = f"{ts_str}|{pedido}"
                ts_epoch = time.mktime(time.strptime(ts_str, "%Y-%m-%d %H:%M:%S"))
                dentro_janela = (agora - ts_epoch) <= janela_minutos * 60
                if dentro_janela:
                    # Só marca como visto (e executa) se está na janela recente
                    if not pedido_ja_visto(pedidos_vistos, chave):
                        pedidos_recentes.append((pedido, next((u for u in ultima_msg if ultima_msg[u]), ultimo_usuario)))
                    pedidos_vistos[chave] = time.time()
                # Pedidos antigos (fora da janela) NÃO vão para pedidos_vistos
                # → podem ser re-executados se o usuário mandar de novo
            except Exception:
                pass

    salvar_pedidos_vistos(pedidos_vistos)

    # Executa os recentes
    for pedido, usuario in pedidos_recentes:
        try:
            log(f"BACKLOG: {pedido[:80]}")
            responder_pedido(pedido, usuario)
        except Exception as e:
            log(f"Erro no backlog: {e}")


def _bot_online() -> bool:
    """Verifica se o bot Discord está respondendo."""
    try:
        with urllib.request.urlopen("http://localhost:7331/status", timeout=3) as r:
            return r.status == 200
    except Exception:
        return False


def _reiniciar_bot():
    """Mata e reinicia o processo do bot Discord."""
    import subprocess as _sp
    log("WATCHDOG: bot offline — reiniciando...")
    bot_script = BASE / "DISCORD" / "link_discord.py"
    pid_file   = BASE / "DISCORD" / ".bot_pid"
    err_log    = BASE / "DISCORD" / "bot_error.log"

    # Mata processo atual se houver PID salvo
    try:
        pid_txt = pid_file.read_text(encoding="ascii").strip().split()[0]
        _sp.run(["taskkill", "/PID", pid_txt, "/F"], capture_output=True, timeout=5)
    except Exception:
        pass

    # Aguarda porta liberar (máx 5s)
    import socket as _sock
    for _ in range(10):
        with _sock.socket(_sock.AF_INET, _sock.SOCK_STREAM) as s:
            s.settimeout(0.5)
            if s.connect_ex(("127.0.0.1", 7331)) != 0:
                break
        time.sleep(0.5)

    # Sobe novo processo
    log_out = open(err_log, "w", encoding="utf-8")
    proc = _sp.Popen(
        [sys.executable, "-u", str(bot_script)],
        cwd=str(bot_script.parent),
        stdout=log_out, stderr=log_out,
        creationflags=_sp.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
    )
    pid_file.write_text(str(proc.pid), encoding="ascii")

    # Aguarda ficar online (máx 15s)
    for i in range(30):
        time.sleep(0.5)
        if _bot_online():
            log(f"WATCHDOG: bot reiniciado ✓ PID {proc.pid} ({(i+1)*0.5:.1f}s)")
            return
    log(f"WATCHDOG: bot não respondeu após 15s — verifique logs")




def monitorar():
    log(f"Supervisor iniciado. Monitorando {LOG_FILE}")

    last_size = LOG_FILE.stat().st_size if LOG_FILE.exists() else 0
    ultima_msg: dict[str, str] = {}  # usuario -> ultima mensagem recebida
    pedidos_vistos: dict = carregar_pedidos_vistos()  # persiste entre restarts
    _watchdog_ticks = 0  # conta iterações para watchdog periódico

    processar_backlog(pedidos_vistos, ultima_msg)

    while True:
        time.sleep(1)
        _watchdog_ticks += 1

        if _watchdog_ticks >= 30:
            _watchdog_ticks = 0
            if not _bot_online():
                _reiniciar_bot()
        try:
            if not LOG_FILE.exists():
                continue
            size = LOG_FILE.stat().st_size
            if size < last_size:
                # log foi rotacionado/zerado (bot reiniciou) — recomeça do início
                last_size = 0
            if size <= last_size:
                continue

            with open(LOG_FILE, "rb") as f:
                f.seek(last_size)
                novas = f.read().decode("utf-8", errors="replace")
            last_size = size

            for linha in novas.strip().splitlines():
                linha = linha.strip()
                if not linha:
                    continue

                log(f"LOG: {linha}")

                # Registra última mensagem do usuário
                if "[IN]" in linha and "-> Link:" in linha:
                    try:
                        usuario = linha.split("[IN] ")[1].split(" ->")[0].strip()
                        msg     = linha.split("-> Link: ", 1)[1].strip()
                        ultima_msg[usuario] = msg
                    except Exception:
                        pass

                # Executa CLAUDE-PEDIDO
                elif "[SYS]" in linha and "[SHEIKAH_SLATE-PEDIDO]" in linha:
                    try:
                        import re as _re_sup
                        pedido_raw = linha.split("[SHEIKAH_SLATE-PEDIDO] ")[1].strip()
                        pedido = _re_sup.sub(r'\s*\[retry:\d+\]', '', pedido_raw).strip()
                        ts_str = linha[1:20]
                        chave = f"{ts_str}|{pedido}"
                        if pedido_ja_visto(pedidos_vistos, chave):
                            log(f"PEDIDO duplicado, ignorando: {pedido[:60]}")
                        else:
                            with _pedido_lock:
                                pedidos_vistos[chave] = time.time()
                                salvar_pedidos_vistos(pedidos_vistos)
                            usuario = next(
                                (u for u in ultima_msg if ultima_msg[u]),
                                "OWNER"
                            )
                            try:
                                responder_pedido(pedido, usuario)
                            except Exception as e:
                                log(f"Erro ao executar pedido: {e}")
                                with _pedido_lock:
                                    pedidos_vistos.pop(chave, None)
                                    salvar_pedidos_vistos(pedidos_vistos)
                    except Exception as e:
                        log(f"Erro ao processar linha: {e}")

                # Enfileira TRIFORCE → Claude Code
                elif "[SYS]" in linha and "[TRIFORCE-PEDIDO]" in linha:
                    try:
                        pedido_tf = linha.split("[TRIFORCE-PEDIDO] ")[1].strip()
                        ts_tf = linha[1:20]
                        chave_tf = f"{ts_tf}|TRIFORCE|{pedido_tf}"
                        if pedido_ja_visto(pedidos_vistos, chave_tf):
                            log(f"TRIFORCE duplicado, ignorando: {pedido_tf[:60]}")
                        else:
                            with _pedido_lock:
                                pedidos_vistos[chave_tf] = time.time()
                                salvar_pedidos_vistos(pedidos_vistos)
                            usuario_tf = next((u for u in ultima_msg if ultima_msg[u]), "OWNER")
                            log(f"TRIFORCE -> Claude Code: {pedido_tf[:80]}")
                            enfileirar_para_claude(pedido_tf, usuario_tf)
                    except Exception as e:
                        log(f"Erro ao processar TRIFORCE: {e}")

                # Detecta resposta ruim
                elif "[OUT] Link ->" in linha:
                    try:
                        dest    = linha.split("[OUT] Link -> ")[1].split(":")[0].strip()
                        resposta = linha.split(f"-> {dest}: ", 1)[1].strip()
                        if eh_ruim(resposta):
                            msg_orig = ultima_msg.get(dest, "")
                            if msg_orig:
                                corrigir_resposta(msg_orig, resposta, dest)
                    except Exception as e:
                        log(f"Erro ao checar resposta: {e}")

        except Exception as e:
            log(f"Erro geral: {e}")
            time.sleep(3)


if __name__ == "__main__":
    monitorar()
