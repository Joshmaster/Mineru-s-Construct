"""
Fallback LLM para mensagens sem skill match.
Hierarquia: OpenRouter → Groq → resposta padrão.
Carrega LINK_PERSONA.md como system prompt.
"""

import json
import urllib.request
import urllib.error
import logging
from pathlib import Path
from typing import Optional

log = logging.getLogger("link-bot.llm")

# ── Chaves e modelos ─────────────────────────────────────────────────────────

import sys as _sys
_sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))
try:
    from hyrule_env import OPENROUTER_KEYS, GROQ_KEYS as _GROQ_KEYS_ENV
    _GROQ_KEYS_FROM_ENV = _GROQ_KEYS_ENV
except ImportError:
    OPENROUTER_KEYS = []
    _GROQ_KEYS_FROM_ENV = []
OPENROUTER_MODELS = [
    "openai/gpt-oss-20b:free",
    "openai/gpt-oss-120b:free",
    "nvidia/nemotron-3-super-120b-a12b:free",
    "meta-llama/llama-3.3-70b-instruct:free",
    "google/gemma-4-31b-it:free",
]

GROQ_KEYS = _GROQ_KEYS_FROM_ENV
GROQ_MODELS = [
    "llama-3.3-70b-versatile",
    "moonshotai/kimi-k2-instruct",
    "llama-3.1-8b-instant",
]
GROQ_HEADERS = {
    "Content-Type": "application/json",
    "User-Agent":   "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept":       "application/json",
    "Origin":       "https://console.groq.com",
    "Referer":      "https://console.groq.com/",
}

# ── Persona ──────────────────────────────────────────────────────────────────

_PERSONA_FILE = (
    Path(__file__).resolve().parents[3]  # Agents/
    / "OPENCODE" / "roaming" / "LINK_PERSONA.md"
)
_PERSONA_WHATSAPP_ADDON = """
# Canal: WhatsApp

Você está no WhatsApp pessoal do OWNER, não no Discord.
- Mesmo estilo: respostas curtas, sem cerimônia
- Não mencione Discord, bots ou sistemas
- Se pedirem algo que não é um comando reconhecido, responda naturalmente como Link
"""

_persona_cache: Optional[str] = None


def _load_persona() -> str:
    global _persona_cache
    if _persona_cache is not None:
        return _persona_cache
    if _PERSONA_FILE.exists():
        text = _PERSONA_FILE.read_text(encoding="utf-8")
        _persona_cache = text + _PERSONA_WHATSAPP_ADDON
    else:
        _persona_cache = (
            "Você é Link, herói de Hyrule. Responda de forma curta e casual, "
            "sem revelar que é um bot." + _PERSONA_WHATSAPP_ADDON
        )
    return _persona_cache


# ── Histórico por usuário ────────────────────────────────────────────────────

_history: dict[str, list] = {}
MAX_HISTORY = 20  # últimas 10 trocas


def _get_history(user: str) -> list:
    return _history.setdefault(user, [])


def _add_to_history(user: str, role: str, content: str):
    h = _get_history(user)
    h.append({"role": role, "content": content})
    if len(h) > MAX_HISTORY:
        _history[user] = h[-MAX_HISTORY:]


# ── HTTP helper ──────────────────────────────────────────────────────────────

def _post(url: str, headers: dict, payload: dict, timeout: int = 20) -> Optional[dict]:
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        log.debug(f"HTTP {url[:40]} falhou: {e}")
        return None


def _extract_text(resp: dict) -> Optional[str]:
    try:
        return resp["choices"][0]["message"]["content"]
    except Exception:
        return None


# ── OpenRouter ───────────────────────────────────────────────────────────────

def _call_openrouter(messages: list) -> Optional[str]:
    for key in OPENROUTER_KEYS:
        for model in OPENROUTER_MODELS:
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {key}",
                "HTTP-Referer": "https://hyrule.local",
                "X-Title": "LinkBot",
            }
            payload = {
                "model": model,
                "messages": messages,
                "temperature": 0.85,
                "max_tokens": 300,
            }
            resp = _post("https://openrouter.ai/api/v1/chat/completions", headers, payload)
            if resp:
                text = _extract_text(resp)
                if text and text.strip():
                    log.debug(f"OpenRouter ok: {model}")
                    return text.strip()
    return None


# ── Groq ─────────────────────────────────────────────────────────────────────

def _call_groq(messages: list) -> Optional[str]:
    for key in GROQ_KEYS:
        for model in GROQ_MODELS:
            headers = {**GROQ_HEADERS, "Authorization": f"Bearer {key}"}
            payload = {
                "model": model,
                "messages": messages,
                "temperature": 0.85,
                "max_tokens": 300,
            }
            resp = _post("https://api.groq.com/openai/v1/chat/completions", headers, payload)
            if resp:
                text = _extract_text(resp)
                if text and text.strip():
                    log.debug(f"Groq ok: {model}")
                    return text.strip()
    return None


# ── Entry point ───────────────────────────────────────────────────────────────

def _is_owner(user_id: str) -> bool:
    try:
        import json
        from pathlib import Path
        cfg_path = Path(__file__).resolve().parents[2] / "config" / "config.json"
        cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
        return str(user_id) == str(cfg.get("OWNER", ""))
    except Exception:
        return False


def chat(user_id: str, user_message: str) -> str:
    """
    Gera resposta LLM com persona Link.
    user_id: número/LID do WhatsApp (string)
    """
    _add_to_history(user_id, "user", user_message)

    system = _load_persona()
    if _is_owner(user_id):
        system += (
            "\n\n# Esta mensagem é do OWNER — o dono e parceiro desse sistema.\n"
            "Ele é quem criou tudo isso, tem acesso total e mando sobre qualquer configuração.\n"
            "Trate-o como parceiro de longa data, sem formalidade."
        )
    messages = [{"role": "system", "content": system}] + _get_history(user_id)

    reply = _call_openrouter(messages) or _call_groq(messages)

    if not reply:
        reply = "🌀"

    _add_to_history(user_id, "assistant", reply)
    return reply
