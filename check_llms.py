#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Valida em tempo real se as LLMs estão respondendo.
Roda automaticamente no SessionStart do Claude Code.
Saída: JSON com systemMessage para exibir no Claude Code.
"""
import json
import sys
import shutil
import subprocess
import urllib.request
import urllib.error

# ── Chaves ────────────────────────────────────────────────────────────────────
try:
    from hyrule_env import (
        OPENROUTER_KEYS,
        CEREBRAS_KEYS,
        MISTRAL_KEYS,
    )
except ImportError:
    OPENROUTER_KEYS = []
    CEREBRAS_KEYS = []
    MISTRAL_KEYS = []


# ── Helpers ───────────────────────────────────────────────────────────────────
def _post(url, payload, headers, timeout=10):
    req = urllib.request.Request(url, data=payload, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, None
    except urllib.error.HTTPError as e:
        return e.code, e.read(200).decode("utf-8", errors="replace")
    except Exception as e:
        return None, str(e)


# ── Checks ────────────────────────────────────────────────────────────────────
def check_ollama():
    try:
        with urllib.request.urlopen("http://localhost:11434/api/tags", timeout=5) as r:
            data = json.loads(r.read())
            models = [m["name"] for m in data.get("models", [])]
            detail = f"modelos: {', '.join(models)}" if models else "online (sem modelos)"
            return True, detail
    except Exception as e:
        return False, str(e)


def check_proxy():
    try:
        with urllib.request.urlopen("http://localhost:8765/v1/models", timeout=5) as r:
            return True, f"HTTP {r.status}"
    except urllib.error.HTTPError as e:
        if e.code in (400, 404, 405):
            return True, f"HTTP {e.code} (respondendo)"
        return False, f"HTTP {e.code}"
    except Exception as e:
        return False, str(e)


def check_discord():
    try:
        with urllib.request.urlopen("http://localhost:7331/status", timeout=5) as r:
            data = json.loads(r.read())
            online = data.get("online", False)
            bot = data.get("bot_name", "?")
            return online, bot if online else "bot offline"
    except urllib.error.HTTPError as e:
        if e.code in (404, 405):
            return True, "daemon respondendo"
        return False, f"HTTP {e.code}"
    except Exception as e:
        return False, str(e)


def check_opencode():
    exe = shutil.which("opencode")
    if not exe:
        return False, "opencode não encontrado"
    try:
        r = subprocess.run(
            [exe, "--version"],
            capture_output=True, text=True, timeout=10,
            encoding="utf-8", errors="replace",
        )
        version = (r.stdout or r.stderr or "").strip()
        return r.returncode == 0, version or f"rc={r.returncode}"
    except Exception as e:
        return False, str(e)


def check_openrouter():
    """Testa cada chave — basta uma funcionar. 429 = chave válida, provider rate-limited."""
    payload = json.dumps({
        "model": "openai/gpt-oss-20b:free",
        "messages": [{"role": "user", "content": "ping"}],
        "max_tokens": 5,
    }).encode("utf-8")

    for idx, key in enumerate(OPENROUTER_KEYS, start=1):
        status, err = _post(
            "https://openrouter.ai/api/v1/chat/completions",
            payload,
            {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {key}",
                "HTTP-Referer": "http://localhost",
                "X-Title": "hyrule-check",
            },
        )
        if status == 200:
            return True, f"OK — chave {idx}"
        if status == 429:
            return True, f"chave {idx} valida, rate-limit"
        if status == 401:
            continue  # chave inválida, tenta próxima
    return False, "todas as chaves invalidas ou sem acesso"


def check_cerebras():
    """Cerebras é o provider primário rápido do WhatsApp/link-bot."""
    payload = json.dumps({
        "model": "llama3.1-8b",
        "messages": [{"role": "user", "content": "ping"}],
        "max_tokens": 5,
    }).encode("utf-8")

    for idx, key in enumerate(CEREBRAS_KEYS, start=1):
        status, err = _post(
            "https://api.cerebras.ai/v1/chat/completions",
            payload,
            {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {key}",
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            },
            timeout=6,
        )
        if status == 200:
            return True, f"OK — chave {idx}"
        if status == 429:
            return True, f"chave {idx} valida, rate-limit"
        if status == 401:
            continue
    return False, "todas as chaves invalidas ou sem acesso"


def check_mistral():
    """Mistral é o provider quality/conversa antes do OpenRouter."""
    payload = json.dumps({
        "model": "mistral-small-latest",
        "messages": [{"role": "user", "content": "ping"}],
        "max_tokens": 5,
    }).encode("utf-8")

    for idx, key in enumerate(MISTRAL_KEYS, start=1):
        status, err = _post(
            "https://api.mistral.ai/v1/chat/completions",
            payload,
            {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {key}",
            },
            timeout=8,
        )
        if status == 200:
            return True, f"OK — chave {idx}"
        if status == 429:
            return True, f"chave {idx} valida, rate-limit"
        if status == 401:
            continue
    return False, "todas as chaves invalidas ou sem acesso"


# ── Main ──────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import os
    if os.environ.get("TRIFORCE_DAEMON"):
        sys.exit(0)

    checks = [
        ("Discord Bot   :7331", check_discord),
        ("Hyrule Proxy  :8765", check_proxy),
        ("Ollama        :11434", check_ollama),
        ("OpenCode      (MASTERSWORD)", check_opencode),
        ("Cerebras      (fast)", check_cerebras),
        ("Mistral       (quality/chat)", check_mistral),
        ("OpenRouter    (fallback)", check_openrouter),
    ]

    linhas = ["── Status das LLMs ──────────────────────"]
    falhas = []

    for nome, fn in checks:
        ok, detalhe = fn()
        icone = "✅" if ok else "❌"
        linhas.append(f"  {icone} {nome} — {detalhe}")
        if not ok:
            falhas.append(nome.split()[0])

    linhas.append("─────────────────────────────────────────")
    if falhas:
        linhas.append(f"  ⚠ Com problema: {', '.join(falhas)}")
    else:
        linhas.append("  Todos os serviços respondendo.")

    msg = "\n".join(linhas)

    # Saída como systemMessage para o Claude Code exibir
    print(json.dumps({"systemMessage": msg}))
    sys.exit(0)
