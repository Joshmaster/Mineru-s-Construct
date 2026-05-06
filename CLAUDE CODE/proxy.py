#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
╔══════════════════════════════════════════════════════════════╗
║          Hyrule Proxy  —  v2.0                              ║
║                                                              ║
║  Intercepta o agent e redireciona para:                     ║
║    1. Ollama (principal)                                     ║
║    2. OpenRouter ou Groq (com seleção prévia de provider)   ║
║                                                              ║
║  Novidades v2.0:                                            ║
║    - Seleção de provider/modelo no startup                  ║
║    - Suporte completo a tool_use (bash, str_replace, etc.)  ║
║    - Endpoint /select para trocar sem reiniciar             ║
╚══════════════════════════════════════════════════════════════╝
"""

import json
import os
import re
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

# Força UTF-8 no terminal Windows
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

import requests
from flask import Flask, Response, jsonify, request

# ─────────────────────────────────────────────────────────────────────────────
# Configuração
# ─────────────────────────────────────────────────────────────────────────────

PROXY_PORT = 8765
HYRULE_MD  = Path(__file__).parent / "HYRULE.md"


def _find_agents_dir() -> Path | None:
    for p in [Path(__file__).resolve().parent, *Path(__file__).resolve().parents]:
        if (p / "hyrule_env.py").exists():
            return p
    return None


def _runtime_keys() -> tuple[list[str], list[str]]:
    agents_dir = _find_agents_dir()
    if agents_dir and str(agents_dir) not in sys.path:
        sys.path.insert(0, str(agents_dir))
    try:
        from hyrule_env import OPENROUTER_KEYS, GROQ_KEYS
    except ImportError:
        OPENROUTER_KEYS = []
        GROQ_KEYS = []
    return list(OPENROUTER_KEYS), list(GROQ_KEYS)


def _resolve_api_key(provider: str, value: str) -> str:
    if value and not value.startswith("${"):
        return value
    openrouter_keys, groq_keys = _runtime_keys()
    env_name = "OPENROUTER_KEY" if provider == "openrouter" else "GROQ_KEY"
    keys = openrouter_keys if provider == "openrouter" else groq_keys
    return os.environ.get(env_name) or (keys[0] if keys else "")


def _resolve_config_secrets(config: dict) -> dict:
    for provider in ("openrouter", "groq"):
        cfg = config.get(provider)
        if isinstance(cfg, dict):
            cfg["api_key"] = _resolve_api_key(provider, cfg.get("api_key", ""))
    return config

# ─────────────────────────────────────────────────────────────────────────────
# Cores ANSI
# ─────────────────────────────────────────────────────────────────────────────

if sys.platform == "win32":
    os.system("color")

C_GREEN  = "\033[92m"
C_YELLOW = "\033[93m"
C_RED    = "\033[91m"
C_CYAN   = "\033[96m"
C_BLUE   = "\033[94m"
C_BOLD   = "\033[1m"
C_DIM    = "\033[2m"
C_RESET  = "\033[0m"

def col(text, *codes):
    return "".join(codes) + str(text) + C_RESET

def log(msg, color=C_DIM):
    ts = datetime.now().strftime("%H:%M:%S")
    print(col(f"[{ts}] {msg}", color))


# ─────────────────────────────────────────────────────────────────────────────
# Parser YAML minimalista (backup sem PyYAML)
# ─────────────────────────────────────────────────────────────────────────────

try:
    import yaml
    _HAS_YAML = True
except ImportError:
    _HAS_YAML = False


def _indent_level(line):
    return len(line) - len(line.lstrip())


def _mini_yaml_parse(text):
    lines  = text.splitlines()
    root   = {}
    stack  = [(root, -1)]
    last_list_key = [None]

    for raw in lines:
        stripped = raw.rstrip()
        if not stripped or stripped.lstrip().startswith("#"):
            continue
        indent  = _indent_level(stripped)
        content = stripped.strip()

        if content.startswith("- "):
            value = content[2:].strip()
            cur_dict, _ = stack[-1]
            if last_list_key[0] and last_list_key[0] in cur_dict:
                if isinstance(cur_dict[last_list_key[0]], list):
                    cur_dict[last_list_key[0]].append(value)
            continue

        if ":" in content:
            key, _, val = content.partition(":")
            key = key.strip()
            val = val.strip().strip('"').strip("'")

            while len(stack) > 1 and indent <= stack[-1][1]:
                stack.pop()

            cur_dict, _ = stack[-1]

            if val == "":
                new_dict = {}
                cur_dict[key] = new_dict
                stack.append((new_dict, indent))
                last_list_key[0] = None
            elif val == "[]":
                cur_dict[key] = []
                last_list_key[0] = key
            else:
                cur_dict[key] = val
                last_list_key[0] = None

    return root


def _parse_yaml(text):
    if _HAS_YAML:
        return yaml.safe_load(text) or {}
    return _mini_yaml_parse(text)


# ─────────────────────────────────────────────────────────────────────────────
# Leitura do HYRULE.md
# ─────────────────────────────────────────────────────────────────────────────

def _extract_yaml_block(md):
    match = re.search(
        r"##\s+Configura[çc][aã]o de Fallback.*?```yaml(.*?)```",
        md, re.DOTALL | re.IGNORECASE,
    )
    if match:
        return match.group(1)
    for block in re.finditer(r"```yaml(.*?)```", md, re.DOTALL):
        if "fallback:" in block.group(1):
            return block.group(1)
    return None


def load_config():
    if not HYRULE_MD.exists():
        log(f"HYRULE.md não encontrado: {HYRULE_MD}", C_RED)
        return {}
    md = HYRULE_MD.read_text(encoding="utf-8")
    yaml_text = _extract_yaml_block(md)
    if not yaml_text:
        log("Seção 'Configuração de Fallback' não encontrada no HYRULE.md.", C_YELLOW)
        return {}
    try:
        data = _parse_yaml(yaml_text)
        return _resolve_config_secrets(data.get("fallback", {}))
    except Exception as e:
        log(f"Erro ao parsear config: {e}", C_RED)
        return {}


def load_system_prompt():
    if not HYRULE_MD.exists():
        return "Responda sempre em português do Brasil."
    content = HYRULE_MD.read_text(encoding="utf-8")
    for marker in ["## Configuração de Fallback", "## Configuracao de Fallback", "---\n\n##"]:
        idx = content.find(marker)
        if idx != -1:
            content = content[:idx].rstrip()
            break
    return content.strip() or "Responda sempre em português do Brasil."


# ─────────────────────────────────────────────────────────────────────────────
# Conversão de formatos: Anthropic ↔ OpenAI
# ─────────────────────────────────────────────────────────────────────────────

def _content_to_str(content):
    """Converte content do formato Anthropic (str ou lista de blocos) para string."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, dict):
                if block.get("type") == "text":
                    parts.append(block.get("text", ""))
                elif block.get("type") == "tool_result":
                    result = block.get("content", "")
                    if isinstance(result, list):
                        result = "\n".join(b.get("text", "") for b in result if isinstance(b, dict))
                    parts.append(str(result))
            elif isinstance(block, str):
                parts.append(block)
        return "\n".join(parts)
    return str(content)


def anthropic_tools_to_openai(tools: list) -> list:
    """
    Converte tool definitions do formato Anthropic para OpenAI.

    Anthropic:
        {"name": "bash", "description": "...", "input_schema": {...}}
    OpenAI:
        {"type": "function", "function": {"name": "bash", "description": "...", "parameters": {...}}}
    """
    result = []
    for t in tools:
        if not isinstance(t, dict):
            continue
        result.append({
            "type": "function",
            "function": {
                "name": t.get("name", ""),
                "description": t.get("description", ""),
                "parameters": t.get("input_schema", {"type": "object", "properties": {}}),
            },
        })
    return result


def openai_tool_calls_to_anthropic(tool_calls: list) -> list:
    """
    Converte tool_calls do formato OpenAI para tool_use blocks Anthropic.

    OpenAI:
        [{"id": "call_xxx", "type": "function", "function": {"name": "bash", "arguments": "{...}"}}]
    Anthropic:
        [{"type": "tool_use", "id": "toolu_xxx", "name": "bash", "input": {...}}]
    """
    blocks = []
    for tc in tool_calls:
        fn = tc.get("function", {})
        try:
            inp = json.loads(fn.get("arguments", "{}"))
        except (json.JSONDecodeError, TypeError):
            inp = {"_raw": fn.get("arguments", "")}
        blocks.append({
            "type": "tool_use",
            "id": tc.get("id", f"toolu_{uuid.uuid4().hex[:12]}"),
            "name": fn.get("name", ""),
            "input": inp,
        })
    return blocks


def anthropic_to_openai(body: dict, system_prompt: str) -> tuple:
    """
    Converte mensagens + tools do formato Anthropic para OpenAI/Ollama.
    Retorna (messages_openai, tools_openai).

    Handles:
      - Mensagens com text blocks simples
      - Mensagens de assistente com tool_use blocks
      - Mensagens de usuário com tool_result blocks
    """
    messages = []

    # System prompt: combina o do HYRULE.md com o que o agent enviou
    systems = [system_prompt]
    if body.get("system"):
        sys_content = _content_to_str(body["system"])
        if sys_content.strip():
            systems.append(sys_content)
    messages.append({"role": "system", "content": "\n\n---\n\n".join(systems)})

    for msg in body.get("messages", []):
        role    = msg.get("role", "user")
        content = msg.get("content", "")

        if isinstance(content, list):
            tool_use_blocks    = [b for b in content if isinstance(b, dict) and b.get("type") == "tool_use"]
            tool_result_blocks = [b for b in content if isinstance(b, dict) and b.get("type") == "tool_result"]
            text_blocks        = [b for b in content if isinstance(b, dict) and b.get("type") == "text"]

            if tool_result_blocks:
                # Usuário retornando resultados de ferramentas → OpenAI "tool" role
                for tr in tool_result_blocks:
                    result_content = tr.get("content", "")
                    if isinstance(result_content, list):
                        result_content = "\n".join(
                            b.get("text", "") for b in result_content if isinstance(b, dict)
                        )
                    messages.append({
                        "role":         "tool",
                        "tool_call_id": tr.get("tool_use_id", ""),
                        "content":      str(result_content),
                    })
                # Texto adicional junto ao tool_result (raro mas possível)
                if text_blocks:
                    text = "\n".join(b.get("text", "") for b in text_blocks)
                    if text.strip():
                        messages.append({"role": "user", "content": text})

            elif tool_use_blocks:
                # Assistente pedindo uso de ferramenta → OpenAI assistant com tool_calls
                text_content = "\n".join(b.get("text", "") for b in text_blocks)
                tool_calls = []
                for tu in tool_use_blocks:
                    tool_calls.append({
                        "id":   tu.get("id", f"call_{uuid.uuid4().hex[:12]}"),
                        "type": "function",
                        "function": {
                            "name":      tu.get("name", ""),
                            "arguments": json.dumps(tu.get("input", {}), ensure_ascii=False),
                        },
                    })
                assistant_msg = {"role": "assistant", "tool_calls": tool_calls}
                if text_content.strip():
                    assistant_msg["content"] = text_content
                messages.append(assistant_msg)

            else:
                # Mensagem comum com text blocks
                text = _content_to_str(content)
                messages.append({"role": role, "content": text})
        else:
            messages.append({"role": role, "content": _content_to_str(content)})

    # Converte tool definitions
    openai_tools = []
    if body.get("tools"):
        openai_tools = anthropic_tools_to_openai(body["tools"])

    return messages, openai_tools


# ─────────────────────────────────────────────────────────────────────────────
# Geração de resposta no formato Anthropic (SSE streaming + JSON)
# ─────────────────────────────────────────────────────────────────────────────

def _make_message_id():
    return f"msg_{uuid.uuid4().hex[:24]}"


def _stop_reason_for_blocks(content_blocks: list) -> str:
    """Determina o stop_reason baseado nos blocos de conteúdo."""
    has_tool = any(b.get("type") == "tool_use" for b in content_blocks)
    return "tool_use" if has_tool else "end_turn"


def build_sse_stream(content_blocks: list, model: str):
    """
    Gerador SSE que emite content_blocks no formato Anthropic streaming.
    Suporta blocos de texto e tool_use.
    """
    msg_id      = _make_message_id()
    stop_reason = _stop_reason_for_blocks(content_blocks)

    def emit(event, data):
        return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"

    yield emit("message_start", {
        "type": "message_start",
        "message": {
            "id":            msg_id,
            "type":          "message",
            "role":          "assistant",
            "content":       [],
            "model":         model,
            "stop_reason":   None,
            "stop_sequence": None,
            "usage":         {"input_tokens": 0, "output_tokens": 0},
        },
    })

    yield emit("ping", {"type": "ping"})

    for idx, block in enumerate(content_blocks):
        btype = block.get("type", "text")

        if btype == "text":
            text = block.get("text", "")

            yield emit("content_block_start", {
                "type":          "content_block_start",
                "index":         idx,
                "content_block": {"type": "text", "text": ""},
            })

            chunk_size = 15
            for i in range(0, len(text), chunk_size):
                yield emit("content_block_delta", {
                    "type":  "content_block_delta",
                    "index": idx,
                    "delta": {"type": "text_delta", "text": text[i:i + chunk_size]},
                })

            yield emit("content_block_stop", {
                "type":  "content_block_stop",
                "index": idx,
            })

        elif btype == "tool_use":
            tool_id   = block.get("id",    f"toolu_{uuid.uuid4().hex[:12]}")
            tool_name = block.get("name",  "")
            tool_inp  = block.get("input", {})

            yield emit("content_block_start", {
                "type":  "content_block_start",
                "index": idx,
                "content_block": {
                    "type":  "tool_use",
                    "id":    tool_id,
                    "name":  tool_name,
                    "input": {},
                },
            })

            # Envia o input como JSON incremental
            partial = json.dumps(tool_inp, ensure_ascii=False)
            chunk_size = 20
            for i in range(0, len(partial), chunk_size):
                yield emit("content_block_delta", {
                    "type":  "content_block_delta",
                    "index": idx,
                    "delta": {
                        "type":         "input_json_delta",
                        "partial_json": partial[i:i + chunk_size],
                    },
                })

            yield emit("content_block_stop", {
                "type":  "content_block_stop",
                "index": idx,
            })

    total_output = sum(len(b.get("text", "") or json.dumps(b.get("input", {}))) for b in content_blocks)

    yield emit("message_delta", {
        "type":  "message_delta",
        "delta": {"stop_reason": stop_reason, "stop_sequence": None},
        "usage": {"output_tokens": max(1, total_output // 4)},
    })

    yield emit("message_stop", {"type": "message_stop"})


def build_json_response(content_blocks: list, model: str) -> dict:
    """Resposta Anthropic não-streaming com suporte a múltiplos blocos."""
    stop_reason = _stop_reason_for_blocks(content_blocks)
    total_output = sum(len(b.get("text", "") or json.dumps(b.get("input", {}))) for b in content_blocks)

    return {
        "id":            _make_message_id(),
        "type":          "message",
        "role":          "assistant",
        "content":       content_blocks,
        "model":         model,
        "stop_reason":   stop_reason,
        "stop_sequence": None,
        "usage":         {"input_tokens": 0, "output_tokens": max(1, total_output // 4)},
    }


# ─────────────────────────────────────────────────────────────────────────────
# Chamadas às APIs
# ─────────────────────────────────────────────────────────────────────────────

def call_ollama(messages: list, cfg: dict, tools: list = None) -> tuple:
    """
    Chama o Ollama. Retorna (content_blocks, model_name) ou (None, model_name).
    content_blocks é lista de blocos Anthropic (text e/ou tool_use).
    """
    endpoint = cfg.get("endpoint", "http://localhost:11434/api/chat")
    model    = cfg.get("model",    "qwen2.5:7b")
    timeout  = int(cfg.get("timeout", 60))

    payload = {"model": model, "messages": messages, "stream": False}
    if tools:
        payload["tools"] = tools  # Ollama >= 0.3 suporta tools natively

    try:
        resp = requests.post(endpoint, json=payload, timeout=timeout)
        resp.raise_for_status()
        data = resp.json()
        msg  = data.get("message", {})

        # Resposta com tool_calls (Ollama >= 0.3)
        if msg.get("tool_calls"):
            blocks = openai_tool_calls_to_anthropic(msg["tool_calls"])
            # Adiciona texto se houver
            if msg.get("content", "").strip():
                blocks = [{"type": "text", "text": msg["content"]}] + blocks
            return blocks, model

        # Resposta texto normal
        text = msg.get("content", "")
        if text:
            return [{"type": "text", "text": text}], model

        log("Ollama: resposta vazia.", C_YELLOW)
        return None, model

    except requests.exceptions.Timeout:
        log("Ollama: timeout.", C_RED)
    except requests.exceptions.ConnectionError:
        log("Ollama: sem conexão (localhost:11434).", C_RED)
    except Exception as e:
        log(f"Ollama: {e}", C_RED)
    return None, model


def _openai_call(messages, endpoint, api_key, model, extra_headers=None, tools=None) -> tuple:
    """
    Chamada genérica para APIs compatíveis com OpenAI.
    Retorna (content_blocks, model_name) — sempre normalizado para Anthropic.
    """
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type":  "application/json",
    }
    if extra_headers:
        headers.update(extra_headers)

    payload = {"model": model, "messages": messages}
    if tools:
        payload["tools"] = tools

    try:
        resp = requests.post(endpoint, json=payload, headers=headers, timeout=120)
        resp.raise_for_status()
        choice = resp.json()["choices"][0]["message"]

        blocks = []

        # Texto (pode vir junto com tool_calls)
        if choice.get("content") and choice["content"].strip():
            blocks.append({"type": "text", "text": choice["content"]})

        # Tool calls
        if choice.get("tool_calls"):
            blocks.extend(openai_tool_calls_to_anthropic(choice["tool_calls"]))

        if not blocks:
            log(f"API ({model}): resposta vazia.", C_YELLOW)
            return None, model

        return blocks, model

    except requests.exceptions.HTTPError as e:
        log(f"HTTP {e.response.status_code}: {e.response.text[:300]}", C_RED)
    except Exception as e:
        log(f"Erro API: {e}", C_RED)
    return None, model


def call_openrouter(messages, model, cfg, tools=None) -> tuple:
    return _openai_call(
        messages,
        cfg.get("endpoint", "https://openrouter.ai/api/v1/chat/completions"),
        cfg.get("api_key", ""),
        model,
        extra_headers={"HTTP-Referer": "https://hyrule-proxy.local", "X-Title": "Hyrule Proxy"},
        tools=tools,
    )


def call_groq(messages, model, cfg, tools=None) -> tuple:
    return _openai_call(
        messages,
        cfg.get("endpoint", "https://api.groq.com/openai/v1/chat/completions"),
        cfg.get("api_key", ""),
        model,
        tools=tools,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Seleção de provider/modelo
# ─────────────────────────────────────────────────────────────────────────────

_API_CALLERS = {
    "openrouter": call_openrouter,
    "groq":       call_groq,
}

_API_LABELS = {
    "openrouter": "OpenRouter",
    "groq":       "Groq",
}


def _classify_models(models: list) -> tuple:
    """Separa modelos em free e pagos pelo sufixo ':free'."""
    free = [m for m in models if ":free" in m.lower()]
    paid = [m for m in models if ":free" not in m.lower()]
    return free, paid


def _model_supports_tools(model: str, no_tool_use: list) -> bool:
    """Retorna False se o modelo estiver na lista de sem suporte a tools."""
    return model not in no_tool_use


def _tool_warning_tag(model: str, no_tool_use: list) -> str:
    """Retorna tag de aviso visual se o modelo não suportar tools."""
    if not _model_supports_tools(model, no_tool_use):
        return col("  ⚠ sem tools", C_RED)
    return ""


def _pick_provider_menu(config: dict) -> tuple:
    """
    Menu interativo para escolher provider e modelo.
    Retorna (provider_key, model, cfg, no_tool_use) ou (None, None, None, []) para cancelar.
    """
    available = [k for k in _API_LABELS if k in config]
    if not available:
        log("Nenhuma API de fallback configurada no HYRULE.md.", C_RED)
        return None, None, None, []

    print()
    print(col("┌─ Escolha o Provider ──────────────────────────────────────┐", C_CYAN + C_BOLD))
    for i, key in enumerate(available, 1):
        print(col(f"│   {i}. {_API_LABELS[key]:<56}│", C_CYAN))
    print(col("│   0. Cancelar                                             │", C_CYAN))
    print(col("└────────────────────────────────────────────────────────────┘", C_CYAN))

    raw = input(col("   ➤ Provider: ", C_BOLD)).strip()
    if raw == "0" or raw.lower() in ("n", "nao", "não"):
        return None, None, None, []

    try:
        provider = available[int(raw) - 1]
    except (ValueError, IndexError):
        log("Opção inválida.", C_RED)
        return None, None, None, []

    api_cfg      = config[provider]
    all_models   = api_cfg.get("models", [])
    no_tool_use  = api_cfg.get("no_tool_use", [])
    free_models, paid_models = _classify_models(all_models)

    print()
    print(col(f"  Modelos disponíveis — {_API_LABELS[provider]}:", C_CYAN + C_BOLD))
    if no_tool_use:
        print(col("  (⚠ = sem suporte a tools/ferramentas)", C_RED))

    counter   = 1
    index_map = {}

    if free_models:
        print(col("  [ GRATUITOS ]", C_GREEN))
        for m in free_models:
            tag = _tool_warning_tag(m, no_tool_use)
            print(f"   {col(str(counter), C_GREEN + C_BOLD)}. {m}{tag}")
            index_map[counter] = m
            counter += 1

    if paid_models:
        print(col("  [ PAGOS / LIMITADOS ]", C_YELLOW))
        for m in paid_models:
            tag = _tool_warning_tag(m, no_tool_use)
            print(f"   {col(str(counter), C_YELLOW + C_BOLD)}. {m}{tag}")
            index_map[counter] = m
            counter += 1

    print(col("  (ou digite o nome completo de qualquer modelo)", C_DIM))

    model_raw = input(col("   ➤ Modelo: ", C_BOLD)).strip()

    try:
        model = index_map[int(model_raw)]
    except (ValueError, KeyError):
        model = model_raw

    if not model:
        log("Modelo inválido.", C_RED)
        return None, None, None, []

    return provider, model, api_cfg, no_tool_use


def select_startup_provider(config: dict) -> tuple:
    """
    Menu de seleção exibido na inicialização do proxy.
    Permite escolher Ollama (padrão) ou um provider alternativo para a sessão.
    Retorna (provider_key, model, cfg, no_tool_use).
    """
    ollama_cfg   = config.get("ollama", {})
    ollama_model = ollama_cfg.get("model", "qwen2.5:7b")

    print()
    print(col("┌─ Seleção de Provider ─────────────────────────────────────┐", C_CYAN + C_BOLD))
    print(col(f"│   1. Ollama (padrão) — {ollama_model:<35}│", C_CYAN))

    fallback_keys = [k for k in _API_LABELS if k in config]
    for i, key in enumerate(fallback_keys, 2):
        print(col(f"│   {i}. {_API_LABELS[key]:<56}│", C_CYAN))

    print(col("└────────────────────────────────────────────────────────────┘", C_CYAN))
    raw = input(col("   ➤ Provider [1]: ", C_BOLD)).strip()

    if raw == "" or raw == "1":
        return "ollama", ollama_model, ollama_cfg, []

    try:
        idx = int(raw) - 2
        if 0 <= idx < len(fallback_keys):
            provider    = fallback_keys[idx]
            api_cfg     = config[provider]
            all_models  = api_cfg.get("models", [])
            no_tool_use = api_cfg.get("no_tool_use", [])
            free_models, paid_models = _classify_models(all_models)

            print()
            print(col(f"  Modelos — {_API_LABELS[provider]}:", C_CYAN + C_BOLD))
            if no_tool_use:
                print(col("  (⚠ = sem suporte a tools/ferramentas)", C_RED))

            counter   = 1
            index_map = {}

            if free_models:
                print(col("  [ GRATUITOS ]", C_GREEN))
                for m in free_models:
                    tag = _tool_warning_tag(m, no_tool_use)
                    print(f"   {col(str(counter), C_GREEN + C_BOLD)}. {m}{tag}")
                    index_map[counter] = m
                    counter += 1

            if paid_models:
                print(col("  [ PAGOS / LIMITADOS ]", C_YELLOW))
                for m in paid_models:
                    tag = _tool_warning_tag(m, no_tool_use)
                    print(f"   {col(str(counter), C_YELLOW + C_BOLD)}. {m}{tag}")
                    index_map[counter] = m
                    counter += 1

            print(col("  (ou digite o nome completo de qualquer modelo)", C_DIM))
            model_raw = input(col("   ➤ Modelo: ", C_BOLD)).strip()

            try:
                model = index_map[int(model_raw)]
            except (ValueError, KeyError):
                model = model_raw

            if not model:
                log("Modelo inválido. Usando Ollama.", C_YELLOW)
                return "ollama", ollama_model, ollama_cfg, []

            return provider, model, api_cfg, no_tool_use
    except (ValueError, IndexError):
        pass

    log("Opção inválida. Usando Ollama.", C_YELLOW)
    return "ollama", ollama_model, ollama_cfg, []


def interactive_fallback(messages: list, config: dict, tools: list = None) -> tuple:
    """
    Exibe menu interativo quando o provider atual falha.
    Retorna (content_blocks, model_used) ou (None, None).
    """
    provider, model, api_cfg, no_tool_use = _pick_provider_menu(config)
    if provider is None:
        return None, None

    # Avisa e remove tools se o modelo não suportar
    effective_tools = tools
    if tools and not _model_supports_tools(model, no_tool_use):
        log(f"⚠  {model} não suporta tools — enviando sem ferramentas.", C_YELLOW)
        effective_tools = None

    log(f"Usando {_API_LABELS[provider]} → {model} …", C_YELLOW)
    caller = _API_CALLERS[provider]
    blocks, model_used = caller(messages, model, api_cfg, tools=effective_tools)
    return blocks, model_used


# ─────────────────────────────────────────────────────────────────────────────
# Flask — servidor proxy
# ─────────────────────────────────────────────────────────────────────────────

app = Flask(__name__)
app.config["JSON_AS_ASCII"] = False

# Estado global da sessão
_config           = {}
_system_prompt    = ""
_session_provider = "ollama"
_session_model    = ""
_session_cfg      = {}
_session_no_tool_use: list = []   # modelos sem suporte a tools neste provider


def _reload_config():
    global _config, _system_prompt
    _config        = load_config()
    _system_prompt = load_system_prompt()


def _call_session(messages: list, tools: list = None) -> tuple:
    """
    Chama o provider/modelo da sessão atual.
    Remove tools automaticamente se o modelo não suportar, com aviso no terminal.
    Retorna (content_blocks, model_used).
    """
    global _session_provider, _session_model, _session_cfg, _session_no_tool_use

    effective_tools = tools
    if tools and not _model_supports_tools(_session_model, _session_no_tool_use):
        log(
            f"⚠  {_session_model} está na lista no_tool_use — "
            f"tools removidas desta requisição.",
            C_YELLOW,
        )
        effective_tools = None

    if _session_provider == "ollama":
        return call_ollama(messages, _session_cfg, tools=effective_tools)
    elif _session_provider in _API_CALLERS:
        caller = _API_CALLERS[_session_provider]
        return caller(messages, _session_model, _session_cfg, tools=effective_tools)
    else:
        return None, "unknown"


@app.route("/v1/models", methods=["GET"])
def list_models():
    """Endpoint consultado pelo agent para verificar modelos disponíveis."""
    return jsonify({
        "data": [
            {
                "id":         "hyrule-proxy",
                "object":     "model",
                "created":    1700000000,
                "owned_by":   "hyrule-proxy",
            }
        ],
        "object": "list",
    })


@app.route("/v1/messages", methods=["POST"])
def messages():
    """Endpoint principal: intercepta chamadas do agent."""
    body   = request.get_json(force=True, silent=True) or {}
    stream = body.get("stream", False)

    n_msgs = len(body.get("messages", []))
    n_tools = len(body.get("tools", []))
    log(
        f"← Agent  stream={stream}  msgs={n_msgs}  tools={n_tools}"
        f"  provider={_session_provider}/{_session_model}",
        C_BLUE,
    )

    # Converte para OpenAI format (com tools)
    converted, openai_tools = anthropic_to_openai(body, _system_prompt)

    # Chama o provider da sessão
    content_blocks, model_used = _call_session(converted, tools=openai_tools or None)

    # Fallback interativo se o provider atual falhou
    if content_blocks is None:
        log(f"{_session_provider.capitalize()} falhou → abrindo menu de fallback.", C_YELLOW)
        print()
        content_blocks, model_used = interactive_fallback(converted, _config, tools=openai_tools or None)

    # Nenhuma API respondeu
    if content_blocks is None:
        log("Nenhuma API respondeu. Retornando erro ao agent.", C_RED)
        return jsonify({
            "type": "error",
            "error": {
                "type":    "overloaded_error",
                "message": "Provider indisponível e nenhum fallback foi selecionado.",
            },
        }), 529

    log(f"→ {len(content_blocks)} bloco(s) de conteúdo ({model_used})", C_GREEN)

    # Retorna no formato correto
    if stream:
        return Response(
            build_sse_stream(content_blocks, model_used or "proxy-model"),
            content_type="text/event-stream",
            headers={
                "Cache-Control":    "no-cache",
                "X-Accel-Buffering": "no",
            },
        )
    else:
        return jsonify(build_json_response(content_blocks, model_used or "proxy-model"))


@app.route("/select", methods=["POST"])
def select_endpoint():
    """
    Troca o provider/modelo da sessão sem reiniciar o proxy.
    Exibe menu interativo no terminal do proxy.
    """
    global _session_provider, _session_model, _session_cfg, _session_no_tool_use

    print()
    print(col("┌─ /select — Troca de Provider ─────────────────────────────┐", C_CYAN + C_BOLD))
    print(col("│  Escolha novo provider para a sessão:                     │", C_CYAN))
    print(col("└────────────────────────────────────────────────────────────┘", C_CYAN))

    provider, model, cfg, no_tool_use = select_startup_provider(_config)
    _session_provider    = provider
    _session_model       = model
    _session_cfg         = cfg
    _session_no_tool_use = no_tool_use

    supports = _model_supports_tools(model, no_tool_use)
    log(f"Provider alterado → {provider}/{model}  tools={'✅' if supports else '⚠ sem suporte'}", C_GREEN)
    return jsonify({"status": "ok", "provider": provider, "model": model, "tool_use": supports})


@app.route("/reload", methods=["POST"])
def reload_endpoint():
    """Recarrega o HYRULE.md sem reiniciar o proxy."""
    _reload_config()
    log("Configuração recarregada via /reload", C_GREEN)
    return jsonify({"status": "ok"})


@app.route("/status", methods=["GET"])
def status():
    """Retorna status atual do proxy."""
    ollama_cfg = _config.get("ollama", {})
    try:
        base       = ollama_cfg.get("endpoint", "http://localhost:11434/api/chat")
        health_url = base.rsplit("/api/", 1)[0] + "/api/tags"
        ok = requests.get(health_url, timeout=3).status_code == 200
    except Exception:
        ok = False

    return jsonify({
        "ollama":           "up" if ok else "down",
        "session_provider": _session_provider,
        "session_model":    _session_model,
        "session_tool_use": _model_supports_tools(_session_model, _session_no_tool_use),
        "fallbacks":        [k for k in _API_CALLERS if k in _config],
        "proxy_port":       PROXY_PORT,
    })


# ─────────────────────────────────────────────────────────────────────────────
# Inicialização
# ─────────────────────────────────────────────────────────────────────────────

BANNER = f"""
{C_CYAN}{C_BOLD}
  ╔══════════════════════════════════════════════════════════╗
  ║   🗡  Hyrule Proxy  —  v2.0                             ║
  ║       Ollama  →  OpenRouter / Groq (fallback)           ║
  ╠══════════════════════════════════════════════════════════╣
  ║   Porta : {PROXY_PORT:<47}║
  ║   Config: ~/.claude/HYRULE.md                           ║
  ╚══════════════════════════════════════════════════════════╝
{C_RESET}"""


# ─────────────────────────────────────────────────────────────────────────────
# Arquivo de sessão — compartilha a escolha entre --select e --serve
# ─────────────────────────────────────────────────────────────────────────────

SESSION_FILE = Path(__file__).parent / ".proxy_session.json"


def save_session(provider: str, model: str):
    SESSION_FILE.write_text(
        json.dumps({"provider": provider, "model": model}, ensure_ascii=False),
        encoding="utf-8",
    )


def load_session() -> tuple:
    """Lê a seleção salva por --select. Retorna (provider, model) ou (None, None)."""
    try:
        data = json.loads(SESSION_FILE.read_text(encoding="utf-8"))
        return data.get("provider"), data.get("model")
    except Exception:
        return None, None


# ─────────────────────────────────────────────────────────────────────────────
# Modo --select: exibe menu, salva escolha em .proxy_session.json e sai
# ─────────────────────────────────────────────────────────────────────────────

def run_select():
    print(BANNER)
    _reload_config()

    ollama_cfg = _config.get("ollama", {})
    try:
        base       = ollama_cfg.get("endpoint", "http://localhost:11434/api/chat")
        health_url = base.rsplit("/api/", 1)[0] + "/api/tags"
        ok = requests.get(health_url, timeout=3).status_code == 200
        if ok:
            log(f"Ollama disponível — modelo: {ollama_cfg.get('model', '?')}", C_GREEN)
        else:
            log("Ollama não encontrado.", C_YELLOW)
    except Exception:
        log("Ollama não encontrado.", C_YELLOW)

    fallbacks = [k for k in _API_CALLERS if k in _config]
    if fallbacks:
        log(f"APIs de fallback: {', '.join(fallbacks)}", C_GREEN)

    print()
    provider, model, cfg, no_tool_use = select_startup_provider(_config)

    supports = _model_supports_tools(model, no_tool_use)
    label    = _API_LABELS.get(provider, "Ollama")
    tool_tag = col("  ✅ tools OK", C_GREEN) if supports else col("  ⚠ sem tool use", C_YELLOW)
    log(f"Sessão: {label} → {model}{tool_tag}", C_GREEN + C_BOLD)

    save_session(provider, model)
    log("Seleção salva. Iniciando servidor...", C_DIM)


# ─────────────────────────────────────────────────────────────────────────────
# Modo --serve: lê sessão salva, sobe Flask em background do terminal
# ─────────────────────────────────────────────────────────────────────────────

def run_serve():
    global _session_provider, _session_model, _session_cfg, _session_no_tool_use

    _reload_config()

    provider, model = load_session()
    if not provider or not model:
        log("Sessão não encontrada. Execute sem --serve para selecionar provider.", C_RED)
        sys.exit(1)

    # Reconstrói cfg e no_tool_use a partir do HYRULE.md
    if provider == "ollama":
        cfg         = _config.get("ollama", {})
        no_tool_use = []
    else:
        cfg         = _config.get(provider, {})
        no_tool_use = cfg.get("no_tool_use", [])

    _session_provider    = provider
    _session_model       = model
    _session_cfg         = cfg
    _session_no_tool_use = no_tool_use

    supports = _model_supports_tools(model, no_tool_use)
    label    = _API_LABELS.get(provider, "Ollama")
    tool_tag = col("✅ tools OK", C_GREEN) if supports else col("⚠ sem tool use", C_YELLOW)

    log(f"Proxy: {label} → {model}  {tool_tag}", C_GREEN + C_BOLD)
    log(f"Escutando em http://localhost:{PROXY_PORT} — Ctrl+C para encerrar", C_DIM)

    # threaded=False é essencial para input() funcionar nos handlers
    app.run(
        host="127.0.0.1",
        port=PROXY_PORT,
        debug=False,
        threaded=False,
        use_reloader=False,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else ""

    if mode == "--select":
        run_select()

    elif mode == "--serve":
        run_serve()

    else:
        # Modo legado: seleção + servidor no mesmo processo (janela separada)
        print(BANNER)
        _reload_config()

        ollama_cfg = _config.get("ollama", {})
        try:
            base       = ollama_cfg.get("endpoint", "http://localhost:11434/api/chat")
            health_url = base.rsplit("/api/", 1)[0] + "/api/tags"
            ok = requests.get(health_url, timeout=3).status_code == 200
            log(f"Ollama {'disponível' if ok else 'não encontrado'}.", C_GREEN if ok else C_YELLOW)
        except Exception:
            log("Ollama não encontrado.", C_YELLOW)

        fallbacks = [k for k in _API_CALLERS if k in _config]
        if fallbacks:
            log(f"APIs de fallback: {', '.join(fallbacks)}", C_GREEN)

        print()
        provider, model, cfg, no_tool_use = select_startup_provider(_config)
        _session_provider    = provider
        _session_model       = model
        _session_cfg         = cfg
        _session_no_tool_use = no_tool_use

        supports = _model_supports_tools(model, no_tool_use)
        label    = _API_LABELS.get(provider, "Ollama")
        tool_tag = col("✅ tools OK", C_GREEN) if supports else col("⚠ sem tool use", C_YELLOW)
        log(f"Sessão: {label} → {model}  {tool_tag}", C_GREEN + C_BOLD)
        log(f"Escutando em http://localhost:{PROXY_PORT} — Ctrl+C para encerrar", C_DIM)

        app.run(
            host="127.0.0.1",
            port=PROXY_PORT,
            debug=False,
            threaded=False,
            use_reloader=False,
        )
