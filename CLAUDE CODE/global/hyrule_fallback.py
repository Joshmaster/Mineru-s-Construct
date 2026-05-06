#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
╔══════════════════════════════════════════════════════════════╗
║          Hyrule Fallback CLI  —  v1.0                       ║
║  Sistema de fallback: Ollama → OpenRouter / Groq            ║
║                                                              ║
║  Lê configuração de: ~/.claude/HYRULE.md                    ║
║  Salva histórico em: ~/.claude/conversation_history.json    ║
╚══════════════════════════════════════════════════════════════╝
"""

import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

# ─────────────────────────────────────────────────────────────────────────────
# Tenta importar PyYAML; se não tiver, usa parser interno minimalista
# ─────────────────────────────────────────────────────────────────────────────
try:
    import yaml
    _HAS_YAML = True
except ImportError:
    _HAS_YAML = False

# ─────────────────────────────────────────────────────────────────────────────
# Caminhos globais (independentes de projeto)
# ─────────────────────────────────────────────────────────────────────────────
CLAUDE_DIR    = Path.home() / ".claude"
HYRULE_MD     = CLAUDE_DIR / "HYRULE.md"
HISTORY_FILE  = CLAUDE_DIR / "conversation_history.json"


def _find_agents_dir() -> Path | None:
    for p in [Path(__file__).resolve().parent, *Path(__file__).resolve().parents, Path.home() / "Agents"]:
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
# Cores ANSI para o terminal
# ─────────────────────────────────────────────────────────────────────────────
if sys.platform == "win32":
    os.system("color")   # habilita ANSI no Windows

C_GREEN  = "\033[92m"
C_YELLOW = "\033[93m"
C_RED    = "\033[91m"
C_CYAN   = "\033[96m"
C_BLUE   = "\033[94m"
C_BOLD   = "\033[1m"
C_DIM    = "\033[2m"
C_RESET  = "\033[0m"

def col(text: str, *codes: str) -> str:
    return "".join(codes) + str(text) + C_RESET


# ─────────────────────────────────────────────────────────────────────────────
# Parser YAML minimalista (backup quando PyYAML não está instalado)
# ─────────────────────────────────────────────────────────────────────────────

def _indent_level(line: str) -> int:
    return len(line) - len(line.lstrip())


def _mini_yaml_parse(text: str) -> dict:
    """
    Parser YAML simplificado que suporta o subconjunto usado no HYRULE.md:
      - Chaves escalares:  key: value
      - Listas:            - item
      - Blocos aninhados via indentação
    Não suporta: âncoras, tipos complexos, strings multilinha, etc.
    """
    lines = text.splitlines()
    root: dict = {}
    stack: list = [(root, -1)]   # (dict_atual, indent)

    list_stack: list = []        # pilha de listas ativas

    for raw in lines:
        stripped = raw.rstrip()
        if not stripped or stripped.lstrip().startswith("#"):
            continue

        indent = _indent_level(stripped)
        content = stripped.strip()

        # ── Item de lista ─────────────────────────────────────────────
        if content.startswith("- "):
            value = content[2:].strip()
            # Encontra o dicionário do escopo atual para adicionar
            cur_dict, _ = stack[-1]
            # O último key inserido no dicionário é nossa lista
            if list_stack:
                lst, lst_indent = list_stack[-1]
                if indent >= lst_indent:
                    lst.append(value)
                    continue
            # Procura lista existente no escopo
            for key in reversed(list(cur_dict.keys())):
                if isinstance(cur_dict[key], list):
                    cur_dict[key].append(value)
                    break
            continue

        # ── Chave: valor ──────────────────────────────────────────────
        if ":" in content:
            key, _, val = content.partition(":")
            key = key.strip()
            val = val.strip().strip('"').strip("'")

            # Volta na pilha até achar o escopo correto
            while len(stack) > 1 and indent <= stack[-1][1]:
                stack.pop()
                if list_stack and list_stack[-1][1] >= indent:
                    list_stack.pop()

            cur_dict, _ = stack[-1]

            if val == "" or val is None:
                # Bloco aninhado
                new_dict: dict = {}
                cur_dict[key] = new_dict
                stack.append((new_dict, indent))
            elif val == "[]":
                cur_dict[key] = []
                list_stack.append((cur_dict[key], indent))
            else:
                cur_dict[key] = val

    return root


def _parse_yaml_block(yaml_text: str) -> dict:
    if _HAS_YAML:
        return yaml.safe_load(yaml_text) or {}
    return _mini_yaml_parse(yaml_text)


# ─────────────────────────────────────────────────────────────────────────────
# Leitura de configuração do HYRULE.md
# ─────────────────────────────────────────────────────────────────────────────

def _extract_yaml_from_md(md_content: str) -> str | None:
    """
    Localiza o primeiro bloco ```yaml que contenha a chave 'fallback:'
    dentro da seção ## Configuração de Fallback
    """
    # Tenta encontrar especificamente o bloco da seção de fallback
    section_match = re.search(
        r"##\s+Configura[çc][aã]o de Fallback.*?```yaml(.*?)```",
        md_content,
        re.DOTALL | re.IGNORECASE,
    )
    if section_match:
        return section_match.group(1)

    # Fallback: primeiro bloco yaml que contenha "fallback:"
    for block in re.finditer(r"```yaml(.*?)```", md_content, re.DOTALL):
        if "fallback:" in block.group(1):
            return block.group(1)

    return None


def load_config() -> dict:
    """Lê e faz parse da configuração de fallback do HYRULE.md global."""
    if not HYRULE_MD.exists():
        print(col(f"\n⚠  Arquivo não encontrado: {HYRULE_MD}", C_YELLOW))
        print(col("   Crie o arquivo e adicione a seção de configuração de fallback.", C_DIM))
        return {}

    md_content = HYRULE_MD.read_text(encoding="utf-8")
    yaml_text  = _extract_yaml_from_md(md_content)

    if not yaml_text:
        print(col("\n⚠  Seção 'Configuração de Fallback' não encontrada no HYRULE.md.", C_YELLOW))
        print(col("   Veja o arquivo CLAUDE_md_addon.md para saber o que adicionar.", C_DIM))
        return {}

    try:
        data = _parse_yaml_block(yaml_text)
        cfg  = _resolve_config_secrets(data.get("fallback", {}))
        if cfg:
            print(col("✅ Configuração carregada com sucesso.", C_GREEN))
        return cfg
    except Exception as e:
        print(col(f"\n❌ Erro ao interpretar config YAML: {e}", C_RED))
        return {}


# ─────────────────────────────────────────────────────────────────────────────
# System prompt: lido do próprio HYRULE.md (tudo antes da seção de fallback)
# ─────────────────────────────────────────────────────────────────────────────

def load_system_prompt() -> str:
    """
    Lê o HYRULE.md e retorna tudo antes da seção '## Configuração de Fallback'
    como system prompt — preservando a persona e as instruções definidas lá.
    """
    if not HYRULE_MD.exists():
        return "Responda sempre em português do Brasil."

    content = HYRULE_MD.read_text(encoding="utf-8")

    # Remove a seção de fallback (e tudo após ela) — é config, não instrução
    cut_markers = [
        "## Configuração de Fallback",
        "## Configuracao de Fallback",
        "---\n\n## Configuração",
    ]
    for marker in cut_markers:
        idx = content.find(marker)
        if idx != -1:
            content = content[:idx].rstrip()
            break

    return content.strip() or "Responda sempre em português do Brasil."


def _inject_system(messages: list, system_prompt: str) -> list:
    """Retorna cópia das mensagens com o system prompt do HYRULE.md no início."""
    return [{"role": "system", "content": system_prompt}] + messages


# ─────────────────────────────────────────────────────────────────────────────
# Histórico global de conversas
# ─────────────────────────────────────────────────────────────────────────────

def load_history() -> list:
    """Carrega o histórico de conversa global."""
    if not HISTORY_FILE.exists():
        return []
    try:
        raw  = HISTORY_FILE.read_text(encoding="utf-8")
        data = json.loads(raw)
        msgs = data.get("messages", [])
        if not isinstance(msgs, list):
            return []
        return msgs
    except (json.JSONDecodeError, OSError):
        return []


def save_history(messages: list) -> None:
    """Persiste o histórico de conversa no arquivo global."""
    CLAUDE_DIR.mkdir(parents=True, exist_ok=True)
    payload = {
        "updated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "total_messages": len(messages),
        "messages": messages,
    }
    try:
        HISTORY_FILE.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except OSError as e:
        print(col(f"⚠  Não foi possível salvar histórico: {e}", C_YELLOW))


def clear_history() -> None:
    if HISTORY_FILE.exists():
        HISTORY_FILE.unlink()


# ─────────────────────────────────────────────────────────────────────────────
# Chamadas às APIs
# ─────────────────────────────────────────────────────────────────────────────

def _openai_compat_call(
    messages: list,
    endpoint: str,
    api_key: str,
    model: str,
    extra_headers: dict | None = None,
    timeout: int = 120,
) -> str | None:
    """Chamada genérica para APIs compatíveis com OpenAI chat completions."""
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    if extra_headers:
        headers.update(extra_headers)

    payload = {
        "model": model,
        "messages": messages,
    }

    try:
        resp = requests.post(
            endpoint,
            json=payload,
            headers=headers,
            timeout=timeout,
        )
        resp.raise_for_status()
        data = resp.json()
        return data["choices"][0]["message"]["content"]
    except requests.exceptions.Timeout:
        print(col(f"⏱  Timeout ao chamar {endpoint}", C_RED))
    except requests.exceptions.ConnectionError:
        print(col(f"🔌 Falha de conexão com {endpoint}", C_RED))
    except requests.exceptions.HTTPError as e:
        print(col(f"❌ HTTP {e.response.status_code}: {e.response.text[:200]}", C_RED))
    except (KeyError, IndexError, json.JSONDecodeError) as e:
        print(col(f"❌ Resposta inesperada da API: {e}", C_RED))
    except Exception as e:
        print(col(f"❌ Erro inesperado: {e}", C_RED))
    return None


def call_ollama(messages: list, cfg: dict) -> str | None:
    """Chama o Ollama via HTTP API."""
    endpoint = cfg.get("endpoint", "http://localhost:11434/api/chat")
    model    = cfg.get("model",    "kimi-k2.5:cloud")
    timeout  = int(cfg.get("timeout", 60))

    payload = {
        "model":    model,
        "messages": messages,
        "stream":   False,
    }
    try:
        resp = requests.post(endpoint, json=payload, timeout=timeout)
        resp.raise_for_status()
        data = resp.json()
        # Formato da resposta do Ollama: {"message": {"content": "..."}}
        return data["message"]["content"]
    except requests.exceptions.Timeout:
        print(col("⏱  Ollama: timeout atingido.", C_RED))
    except requests.exceptions.ConnectionError:
        print(col("🔌 Ollama: serviço não disponível (localhost:11434).", C_RED))
    except requests.exceptions.HTTPError as e:
        print(col(f"❌ Ollama HTTP {e.response.status_code}: {e.response.text[:200]}", C_RED))
    except (KeyError, json.JSONDecodeError) as e:
        print(col(f"❌ Ollama — resposta inesperada: {e}", C_RED))
    except Exception as e:
        print(col(f"❌ Ollama — erro inesperado: {e}", C_RED))
    return None


def call_openrouter(messages: list, model: str, cfg: dict) -> str | None:
    endpoint = cfg.get("endpoint", "https://openrouter.ai/api/v1/chat/completions")
    api_key  = cfg.get("api_key", "")
    if not api_key:
        print(col("❌ OpenRouter: api_key não configurada no HYRULE.md.", C_RED))
        return None
    extra = {"HTTP-Referer": "https://hyrule-fallback.local", "X-Title": "Hyrule Fallback"}
    return _openai_compat_call(messages, endpoint, api_key, model, extra)


def call_groq(messages: list, model: str, cfg: dict) -> str | None:
    endpoint = cfg.get("endpoint", "https://api.groq.com/openai/v1/chat/completions")
    api_key  = cfg.get("api_key", "")
    if not api_key:
        print(col("❌ Groq: api_key não configurada no HYRULE.md.", C_RED))
        return None
    return _openai_compat_call(messages, endpoint, api_key, model)


# ─────────────────────────────────────────────────────────────────────────────
# Seleção interativa de fallback
# ─────────────────────────────────────────────────────────────────────────────

_API_LABELS = {
    "openrouter": "OpenRouter",
    "groq":       "Groq",
}

_API_CALLERS = {
    "openrouter": call_openrouter,
    "groq":       call_groq,
}


def select_fallback_api(config: dict) -> tuple | None:
    """
    Apresenta menu interativo para escolher API e modelo de fallback.
    Retorna (api_name, model, api_cfg) ou None em caso de cancelamento.
    """
    available = [k for k in _API_LABELS if k in config]

    if not available:
        print(col("❌ Nenhuma API de fallback configurada no HYRULE.md.", C_RED))
        return None

    # ── Escolha da API ────────────────────────────────────────────────────
    print()
    print(col("┌─ Fallback ativado ─────────────────────────────────────────┐", C_CYAN))
    print(col("│  Escolha a API de fallback:                                │", C_CYAN))
    for idx, key in enumerate(available, 1):
        label = _API_LABELS[key]
        print(col(f"│   {idx}. {label:<56}│", C_CYAN))
    print(col("│   0. Cancelar                                              │", C_CYAN))
    print(col("└────────────────────────────────────────────────────────────┘", C_CYAN))

    raw = input(col("   ➤ Opção: ", C_BOLD)).strip()

    if raw == "0" or raw.lower() in ("n", "nao", "não", "cancel"):
        return None

    try:
        api_name = available[int(raw) - 1]
    except (ValueError, IndexError):
        print(col("Opção inválida.", C_RED))
        return None

    api_cfg = config[api_name]
    models  = api_cfg.get("models", [])

    # ── Escolha do modelo ─────────────────────────────────────────────────
    print()
    print(col(f"  Modelos sugeridos para {_API_LABELS[api_name]}:", C_CYAN))
    for i, m in enumerate(models, 1):
        print(col(f"   {i}. ", C_DIM) + m)
    print(col("   (ou digite qualquer nome de modelo diretamente)", C_DIM))

    model_raw = input(col("   ➤ Modelo: ", C_BOLD)).strip()

    # Permite digitar número (índice) ou nome direto
    model = model_raw
    try:
        midx = int(model_raw) - 1
        if 0 <= midx < len(models):
            model = models[midx]
    except ValueError:
        pass   # model_raw já é o nome

    if not model:
        print(col("Modelo inválido.", C_RED))
        return None

    return api_name, model, api_cfg


def call_fallback(messages: list, config: dict) -> str | None:
    """Orquestra a seleção e chamada do fallback."""
    result = select_fallback_api(config)
    if result is None:
        return None

    api_name, model, api_cfg = result
    label = _API_LABELS.get(api_name, api_name)

    print(col(f"\n  ⚡ Conectando via {label} → {model} …\n", C_YELLOW))

    caller = _API_CALLERS.get(api_name)
    if caller:
        return caller(messages, model, api_cfg)

    print(col(f"❌ API '{api_name}' não suportada.", C_RED))
    return None


# ─────────────────────────────────────────────────────────────────────────────
# Exibição de mensagens
# ─────────────────────────────────────────────────────────────────────────────

def print_history_summary(history: list) -> None:
    if not history:
        print(col("  (histórico vazio)", C_DIM))
        return
    for i, msg in enumerate(history, 1):
        role  = msg.get("role", "?")
        body  = msg.get("content", "")
        label = col("OWNER", C_BLUE + C_BOLD) if role == "user" else col("IA", C_GREEN + C_BOLD)
        snippet = body[:120].replace("\n", " ")
        if len(body) > 120:
            snippet += "…"
        print(f"  [{i:02d}] {label}: {snippet}")


def _spinner(msg: str, done_event) -> None:
    """Spinner simples para indicar processamento (roda em thread separada)."""
    frames = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
    i = 0
    while not done_event.is_set():
        sys.stdout.write(col(f"\r  {frames[i % len(frames)]} {msg}", C_YELLOW))
        sys.stdout.flush()
        time.sleep(0.08)
        i += 1
    sys.stdout.write("\r" + " " * (len(msg) + 6) + "\r")
    sys.stdout.flush()


# ─────────────────────────────────────────────────────────────────────────────
# Interface de texto do HYRULE.md com informações de status
# ─────────────────────────────────────────────────────────────────────────────

BANNER = f"""
{C_CYAN}{C_BOLD}
  ╔══════════════════════════════════════════════════════════╗
  ║   🗡  Hyrule Fallback CLI  —  v1.0                      ║
  ║       Ollama principal  →  OpenRouter / Groq fallback   ║
  ╠══════════════════════════════════════════════════════════╣
  ║   Histórico global: ~/.claude/conversation_history.json ║
  ║   Config global  : ~/.claude/HYRULE.md                  ║
  ╚══════════════════════════════════════════════════════════╝
{C_RESET}"""

HELP_TEXT = f"""
{C_CYAN}  Comandos disponíveis:{C_RESET}

  {C_BOLD}/historico{C_RESET}   — exibe resumo das mensagens da sessão atual
  {C_BOLD}/limpar{C_RESET}      — apaga o histórico salvo e inicia nova conversa
  {C_BOLD}/reload{C_RESET}      — recarrega o HYRULE.md sem reiniciar o script
  {C_BOLD}/status{C_RESET}      — exibe configuração e status atual do Ollama
  {C_BOLD}/fallback{C_RESET}    — força o uso do fallback na próxima mensagem
  {C_BOLD}/sair{C_RESET}        — encerra o programa
  {C_BOLD}/ajuda{C_RESET}       — exibe este menu
"""


# ─────────────────────────────────────────────────────────────────────────────
# Verificação rápida de saúde do Ollama
# ─────────────────────────────────────────────────────────────────────────────

def check_ollama_health(cfg: dict) -> bool:
    """Verifica se o Ollama está respondendo com uma requisição leve."""
    base_url = cfg.get("endpoint", "http://localhost:11434/api/chat")
    health_url = base_url.rsplit("/api/", 1)[0] + "/api/tags"
    try:
        resp = requests.get(health_url, timeout=5)
        return resp.status_code == 200
    except Exception:
        return False


# ─────────────────────────────────────────────────────────────────────────────
# Loop principal
# ─────────────────────────────────────────────────────────────────────────────

def run() -> None:
    print(BANNER)

    # ── Carrega configuração ──────────────────────────────────────────────
    config      = load_config()
    ollama_cfg  = config.get("ollama", {})
    system_prompt = load_system_prompt()

    # ── Status do Ollama na inicialização ─────────────────────────────────
    ollama_ok = check_ollama_health(ollama_cfg)
    if ollama_ok:
        model_name = ollama_cfg.get("model", "desconhecido")
        print(col(f"  🟢 Ollama disponível — modelo: {model_name}", C_GREEN))
    else:
        print(col("  🔴 Ollama não encontrado. Fallback será ativado em caso de falha.", C_YELLOW))

    # ── Carrega histórico ─────────────────────────────────────────────────
    history = load_history()

    if history:
        count = len(history)
        print(col(f"\n  📜 Histórico encontrado: {count} mensagens.", C_CYAN))
        choice = input(col("  Continuar conversa anterior? [S/n]: ", C_BOLD)).strip().lower()
        if choice in ("n", "nao", "não"):
            history = []
            save_history(history)
            print(col("  ✅ Histórico limpo. Nova conversa iniciada.\n", C_GREEN))
        else:
            print(col(f"  ✅ Continuando com {count} mensagens no contexto.\n", C_GREEN))
    else:
        print(col("\n  📜 Nenhum histórico anterior. Iniciando nova conversa.\n", C_DIM))

    print(col("  Digite /ajuda para ver os comandos disponíveis.\n", C_DIM))

    # ── Estado de override de fallback ────────────────────────────────────
    force_fallback = False

    # ─────────────────────────────────────────────────────────────────────
    # Loop de entrada
    # ─────────────────────────────────────────────────────────────────────
    while True:
        try:
            prefix = col("⚡ OWNER (fallback): ", C_YELLOW + C_BOLD) if force_fallback else col("🗡  OWNER: ", C_BLUE + C_BOLD)
            user_input = input(prefix).strip()
        except (KeyboardInterrupt, EOFError):
            print(col("\n\n  ⚔️  Missão encerrada. Que Nayru te proteja, aventureiro!\n", C_GREEN))
            break

        if not user_input:
            continue

        # ── Comandos especiais ─────────────────────────────────────────────
        if user_input.startswith("/"):
            cmd = user_input.lower().split()[0]

            if cmd == "/sair":
                print(col("\n  ⚔️  Até a próxima jornada!\n", C_GREEN))
                break

            elif cmd == "/ajuda":
                print(HELP_TEXT)
                continue

            elif cmd == "/historico":
                print(col("\n  📜 Histórico atual:\n", C_CYAN))
                print_history_summary(history)
                print()
                continue

            elif cmd == "/limpar":
                history = []
                clear_history()
                print(col("  ✅ Histórico apagado. Nova conversa iniciada.\n", C_GREEN))
                continue

            elif cmd == "/reload":
                config     = load_config()
                ollama_cfg = config.get("ollama", {})
                print(col("  ✅ Configuração recarregada do HYRULE.md.\n", C_GREEN))
                continue

            elif cmd == "/status":
                print(col("\n  📊 Status atual:\n", C_CYAN))
                ok = check_ollama_health(ollama_cfg)
                emoji = "🟢" if ok else "🔴"
                print(f"    {emoji} Ollama: {'disponível' if ok else 'indisponível'}")
                print(f"    📁 Histórico: {len(history)} mensagens")
                print(f"    📄 Config: {HYRULE_MD}")
                print(f"    💾 Histórico: {HISTORY_FILE}")
                apis_configuradas = [k for k in _API_LABELS if k in config]
                print(f"    🔌 APIs fallback: {', '.join(apis_configuradas) or 'nenhuma'}")
                print(f"    ⚡ Modo fallback forçado: {'sim' if force_fallback else 'não'}")
                print()
                continue

            elif cmd == "/fallback":
                force_fallback = not force_fallback
                estado = "ATIVADO" if force_fallback else "DESATIVADO"
                cor    = C_YELLOW if force_fallback else C_GREEN
                print(col(f"  ⚡ Modo fallback forçado: {estado}\n", cor))
                continue

            else:
                print(col(f"  Comando desconhecido: {user_input}. Digite /ajuda.", C_YELLOW))
                continue

        # ── Adiciona mensagem do usuário ao histórico ──────────────────────
        history.append({"role": "user", "content": user_input})

        # ── Tenta Ollama (a menos que fallback esteja forçado) ─────────────
        response: str | None = None

        if not force_fallback:
            # Tenta com spinner em thread separada
            try:
                import threading
                done_evt = threading.Event()
                spinner_thread = threading.Thread(
                    target=_spinner,
                    args=("Ollama processando…", done_evt),
                    daemon=True,
                )
                spinner_thread.start()
                response = call_ollama(_inject_system(history, system_prompt), ollama_cfg)
            finally:
                done_evt.set()
                spinner_thread.join(timeout=1)

        # ── Fallback se Ollama falhou ou foi forçado ───────────────────────
        if response is None:
            if not force_fallback:
                print(col("\n  ⚠  Ollama não respondeu.", C_YELLOW))
                resposta_fallback = input(col("  Ativar fallback? [S/n]: ", C_BOLD)).strip().lower()
                if resposta_fallback in ("n", "nao", "não"):
                    history.pop()
                    print(col("  Mensagem descartada. Continue digitando.\n", C_YELLOW))
                    continue

            response = call_fallback(_inject_system(history, system_prompt), config)

            if response is None:
                history.pop()
                print(col("  ❌ Fallback também falhou. Verifique as APIs e tente novamente.\n", C_RED))
                continue

        # ── Exibe resposta ─────────────────────────────────────────────────
        print()
        print(col("  🔮 Assistente:", C_GREEN + C_BOLD))
        print()
        # Indenta a resposta para melhor legibilidade
        for line in response.splitlines():
            print(f"    {line}")
        print()

        # ── Salva no histórico ─────────────────────────────────────────────
        history.append({"role": "assistant", "content": response})
        save_history(history)


# ─────────────────────────────────────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    run()
