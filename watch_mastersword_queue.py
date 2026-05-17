#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Watcher MASTERSWORD — processa pedidos do OpenCode.
Lê mastersword_queue.json, roda `opencode run`, envia resposta via HTTP API.
"""
import json
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

BASE = Path(__file__).parent
QUEUE_FILE = BASE / "mastersword_queue.json"
LOCK_FILE  = BASE / ".mastersword_processing.lock"
PERSONA_FILE = BASE / "OPENCODE" / "roaming" / "LINK_PERSONA.md"
MASTERSWORD_INSTRUCTIONS = BASE / "OPENCODE" / "roaming" / "MASTERSWORD_INSTRUCTIONS.md"
CONFIG_TEMPLATE = BASE / "OPENCODE" / "mastersword.opencode.json"
CONFIG_FILE = Path.home() / ".config" / "opencode" / "opencode.json"
POLL_SECS = 2
STALE_LOCK_SECS = 15 * 60
TIMEOUT_SECS = 240

DEFAULT_MODELS = [
    "openrouter/openai/gpt-5.1",                   # 1. melhor OpenRouter (Claude bloqueado por credito)
    "mistral/mistral-large-latest",                 # 2. melhor Mistral (direto)
    "cerebras/qwen-3-235b-a22b-instruct-2507",     # 3. melhor Cerebras (direto)
    "openrouter/deepseek/deepseek-r1-0528",        # 4. DeepSeek R1 raciocinio
    "openrouter/openai/gpt-oss-120b:free",         # 5. fallback gratuito
]
OPENROUTER_MODELS = {
    "anthropic/claude-opus-4.7":   {"name": "Claude Opus 4.7"},
    "anthropic/claude-sonnet-4.6": {"name": "Claude Sonnet 4.6"},
    "openai/gpt-5.1":              {"name": "GPT-5.1"},
    "google/gemini-2.5-pro":       {"name": "Gemini 2.5 Pro"},
    "deepseek/deepseek-r1-0528":   {"name": "DeepSeek R1"},
    "openai/gpt-oss-120b:free":    {"name": "GPT OSS 120B (free)"},
    "openai/gpt-oss-20b:free":     {"name": "GPT OSS 20B (free)"},
}
MISTRAL_MODELS = {
    "mistral-large-latest":    {"name": "Mistral Large"},
    "devstral-medium-latest":  {"name": "Devstral Medium (codigo)"},
    "magistral-medium-latest": {"name": "Magistral Medium (raciocinio)"},
}
CEREBRAS_MODELS = {
    "qwen-3-235b-a22b-instruct-2507": {"name": "Qwen3 235B (Cerebras turbo)"},
}
ANSI_RE = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")


def _ler_e_limpar() -> list:
    if not QUEUE_FILE.exists():
        return []
    try:
        itens = json.loads(QUEUE_FILE.read_text(encoding="utf-8"))
        if itens:
            QUEUE_FILE.write_text("[]", encoding="utf-8")
        return itens
    except Exception:
        return []


def _reenfileirar(item: dict):
    try:
        itens = json.loads(QUEUE_FILE.read_text(encoding="utf-8")) if QUEUE_FILE.exists() else []
        if not isinstance(itens, list):
            itens = []
    except Exception:
        itens = []
    QUEUE_FILE.write_text(json.dumps([item, *itens], ensure_ascii=False, indent=2), encoding="utf-8")


def _pid_ativo(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except (ProcessLookupError, ValueError):
        return False
    except PermissionError:
        return True


def _lock_stale() -> bool:
    try:
        data = json.loads(LOCK_FILE.read_text(encoding="utf-8"))
        pid = int(data.get("pid", 0))
        ts = float(data.get("ts", 0))
        return (not _pid_ativo(pid)) or (time.time() - ts > STALE_LOCK_SECS)
    except Exception:
        return True


def _adquirir_lock() -> bool:
    if LOCK_FILE.exists() and _lock_stale():
        LOCK_FILE.unlink(missing_ok=True)
    payload = json.dumps({"pid": os.getpid(), "ts": time.time()})
    try:
        fd = os.open(str(LOCK_FILE), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(payload)
        return True
    except FileExistsError:
        return False


def _liberar_lock():
    try:
        data = json.loads(LOCK_FILE.read_text(encoding="utf-8"))
        if int(data.get("pid", 0)) == os.getpid():
            LOCK_FILE.unlink(missing_ok=True)
    except Exception:
        pass


def _enviar(usuario: str, msg: str, canal: str = "discord"):
    porta = 7332 if canal == "whatsapp" else 7331
    payload = json.dumps({"to": usuario, "msg": msg}).encode("utf-8")
    req = urllib.request.Request(
        f"http://localhost:{porta}/send", data=payload,
        headers={"Content-Type": "application/json"}, method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=15):
            pass
        print(f"ENVIADO ({canal}:{porta}) -> {usuario}: {msg[:60]}", flush=True)
    except Exception as e:
        print(f"Erro enviar ({canal}): {e}", flush=True)


def _env_opencode() -> dict:
    env = os.environ.copy()
    try:
        from hyrule_env import OPENROUTER_KEYS, MISTRAL_KEYS, CEREBRAS_KEYS
    except ImportError:
        OPENROUTER_KEYS = MISTRAL_KEYS = CEREBRAS_KEYS = []
    if OPENROUTER_KEYS:
        env.setdefault("OPENROUTER_API_KEY", OPENROUTER_KEYS[0])
    if MISTRAL_KEYS:
        env.setdefault("MISTRAL_API_KEY", MISTRAL_KEYS[0])
    if CEREBRAS_KEYS:
        env.setdefault("CEREBRAS_API_KEY", CEREBRAS_KEYS[0])
    env.setdefault("OPENCODE_EXPERIMENTAL_OUTPUT_TOKEN_MAX", os.environ.get("MASTERSWORD_OUTPUT_TOKEN_MAX", "2048"))
    return env


def _ensure_config():
    if not CONFIG_TEMPLATE.exists():
        return

    CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
    if not CONFIG_FILE.exists():
        shutil.copyfile(CONFIG_TEMPLATE, CONFIG_FILE)

    required = [
        str(MASTERSWORD_INSTRUCTIONS),
        str(PERSONA_FILE),
    ]
    try:
        config = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
    except Exception:
        shutil.copyfile(CONFIG_TEMPLATE, CONFIG_FILE)
        return

    instructions = required
    config["provider"] = {
        "openrouter": {
            "api": "https://openrouter.ai/api/v1",
            "env": ["OPENROUTER_API_KEY"],
            "models": OPENROUTER_MODELS,
        },
        "mistral": {
            "api": "https://api.mistral.ai/v1",
            "env": ["MISTRAL_API_KEY"],
            "models": MISTRAL_MODELS,
        },
        "cerebras": {
            "api": "https://api.cerebras.ai/v1",
            "env": ["CEREBRAS_API_KEY"],
            "models": CEREBRAS_MODELS,
        },
    }
    config["model"] = DEFAULT_MODELS[0]
    config["small_model"] = "cerebras/qwen-3-235b-a22b-instruct-2507"
    config["instructions"] = instructions
    CONFIG_FILE.write_text(json.dumps(config, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _modelos() -> list[str]:
    raw = os.environ.get("MASTERSWORD_MODELS", "").strip()
    if raw:
        return [m.strip() for m in raw.split(",") if m.strip()]
    return DEFAULT_MODELS


def _prompt(pedido: str, canal: str) -> str:
    return (
        f"[MASTERSWORD via {canal.upper()}] OWNER pediu:\n{pedido}\n\n"
        "Siga a persona e a instrucao operacional do MASTERSWORD carregadas na config. "
        "Se isto for uma retomada de contexto, leia as memorias do Hyrule antes de responder. "
        "Se executar alguma acao, diga apenas o resultado real."
    )


def _limpar_output(texto: str) -> str:
    texto = ANSI_RE.sub("", texto)
    linhas = []
    for linha in texto.splitlines():
        clean = linha.strip()
        if not clean:
            continue
        if clean.startswith("> build ·"):
            continue
        linhas.append(clean)
    return "\n".join(linhas).strip()


def _rodar_opencode(pedido: str, canal: str) -> tuple[str, str | None]:
    opencode = shutil.which("opencode")
    if not opencode:
        return "MASTERSWORD nao encontrou `opencode` no PATH. Instale com `npm i -g opencode-ai`.", None

    _ensure_config()
    env = _env_opencode()
    prompt = _prompt(pedido, canal)
    erros = []
    for model in _modelos():
        cmd = [
            opencode,
            "run",
            prompt,
            "--model", model,
            "--format", "default",
            "--dangerously-skip-permissions",
            "--dir", str(BASE),
        ]
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=TIMEOUT_SECS,
                cwd=str(BASE),
                env=env,
            )
            output = _limpar_output(result.stdout or "")
            err = (result.stderr or "").strip()
            if result.returncode == 0 and output:
                return output, model
            erros.append(f"{model}: rc={result.returncode} {err[:160]}")
        except subprocess.TimeoutExpired:
            erros.append(f"{model}: timeout {TIMEOUT_SECS}s")
        except Exception as e:
            erros.append(f"{model}: {e}")
    return "MASTERSWORD falhou em todos os modelos:\n" + "\n".join(erros[-3:]), None


def _processar(item: dict):
    pedido  = item.get("pedido", "").strip()
    usuario = item.get("usuario", "OWNER")
    canal   = item.get("canal", "discord")

    if not pedido:
        return

    if not _adquirir_lock():
        _reenfileirar(item)
        print("MASTERSWORD ocupada; pedido mantido na fila.", flush=True)
        return

    print(f"MASTERSWORD processando: {pedido[:80]}", flush=True)
    try:
        resposta, model = _rodar_opencode(pedido, canal)
        prefixo = "🗡️ "
        if model:
            print(f"MASTERSWORD ok: {model}", flush=True)
        _enviar(usuario, f"{prefixo}{resposta}"[:2000], canal)
    finally:
        _liberar_lock()


if __name__ == "__main__":
    print(f"🗡️ MASTERSWORD watcher iniciado. Monitorando {QUEUE_FILE}", flush=True)
    while True:
        time.sleep(POLL_SECS)
        if LOCK_FILE.exists() and not _lock_stale():
            continue
        itens = _ler_e_limpar()
        for item in itens:
            try:
                _processar(item)
            except Exception as e:
                print(f"Erro item MASTERSWORD: {e}", flush=True)
