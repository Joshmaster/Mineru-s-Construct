"""
LLM hub do Link-bot — hierarquia de providers e helpers de IA.

Hierarquia por tier:
  FAST    → Cerebras llama3.1-8b (~0.3s) → OpenRouter → Ollama
  QUALITY → Mistral small → OpenRouter → Ollama
  CHAT    → Cerebras llama3.1-8b → Mistral → OpenRouter → Ollama compact
  EMOJI   → Ollama only (latência não justifica cloud)
"""

import json
import re
import sys as _sys
import threading
import time
import urllib.request
import urllib.error
import logging
from pathlib import Path
from typing import Optional

log = logging.getLogger("link-bot.llm")

# ── Chaves e modelos ─────────────────────────────────────────────────────────

_sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))
try:
    from hyrule_env import (
        OPENROUTER_KEYS,
        CEREBRAS_KEYS as _CEREBRAS_KEYS_ENV,
        MISTRAL_KEYS as _MISTRAL_KEYS_ENV,
    )
except ImportError:
    OPENROUTER_KEYS = []
    _CEREBRAS_KEYS_ENV = []
    _MISTRAL_KEYS_ENV = []

OPENROUTER_KEYS: list
OPENROUTER_MODELS = [
    "openai/gpt-oss-20b:free",
]

CEREBRAS_KEYS = _CEREBRAS_KEYS_ENV
CEREBRAS_MODELS_FAST    = ["llama3.1-8b"]
CEREBRAS_MODELS_QUALITY = ["llama3.3-70b"]

MISTRAL_KEYS = _MISTRAL_KEYS_ENV
MISTRAL_MODELS = ["mistral-small-latest"]

OLLAMA_URL   = "http://localhost:11434/api/chat"
OLLAMA_MODEL = "qwen3:8b"

# ── Persona ──────────────────────────────────────────────────────────────────

_PERSONA_FILE = (
    Path(__file__).resolve().parents[3]
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

# ── Filas de tarefas ─────────────────────────────────────────────────────────

_AGENTS_DIR = Path(__file__).resolve().parents[3]
_WPP_TASKS  = _AGENTS_DIR / "whatsapp_tasks.json"


def _load_persona() -> str:
    global _persona_cache
    if _persona_cache is not None:
        return _persona_cache
    owner_name = _owner_name()
    wpp_owner_rule = (
        f"\n\n# Nome do dono no WhatsApp\n"
        f"O placeholder OWNER significa {owner_name}. Nunca escreva OWNER na resposta final; "
        f"chame ele de {owner_name} ou fale direto com ele.\n"
    )
    if _PERSONA_FILE.exists():
        text = _PERSONA_FILE.read_text(encoding="utf-8")
        _persona_cache = text + _PERSONA_WHATSAPP_ADDON + wpp_owner_rule
    else:
        _persona_cache = (
            "Você é Link, herói de Hyrule. Responda de forma curta e casual, "
            "sem revelar que é um bot." + _PERSONA_WHATSAPP_ADDON + wpp_owner_rule
        )
    return _persona_cache


def _owner_name() -> str:
    try:
        from bot.core import access as access_ctl
        cfg = access_ctl.load_config()
        for key in [cfg.get("OWNER", ""), *(cfg.get("OWNER_IDS", []) or [])]:
            name = access_ctl.display_name(key)
            if name and not name.startswith("usuario "):
                return str(name)
    except Exception:
        pass
    return "Josh"


def _load_local_persona() -> str:
    owner_name = _owner_name()
    return (
        f"Voce e Link, parceiro do {owner_name}. Responda em portugues do Brasil, curto, "
        "casual e direto. Nao diga que e IA, bot ou sistema. Pense internamente "
        "se precisar, mas entregue apenas a resposta final."
        + _PERSONA_WHATSAPP_ADDON
    )


def _finalize_reply(reply: str, user_id: str) -> str:
    """Evita vazar o placeholder OWNER no WhatsApp."""
    if not reply:
        return reply
    name = _owner_name()
    reply = re.sub(r"\bOWNER\b", name, reply)
    return reply.strip()


# ── Catálogo de skills (injetado no system prompt do chat) ───────────────────

_skill_catalog: str = ""


def set_skill_catalog(catalog: str):
    global _skill_catalog
    _skill_catalog = catalog


# ── Histórico por usuário ────────────────────────────────────────────────────

_history: dict[str, list] = {}
MAX_HISTORY = 20


def _get_history(user: str) -> list:
    return _history.setdefault(user, [])


def _add_to_history(user: str, role: str, content: str):
    h = _get_history(user)
    h.append({"role": role, "content": content})
    if len(h) > MAX_HISTORY:
        _history[user] = h[-MAX_HISTORY:]


# ── HTTP helper ──────────────────────────────────────────────────────────────

_cloud_fail:    dict[str, int]   = {}
_cloud_fail_ts: dict[str, float] = {}
_CLOUD_SKIP_SECS      = 180
_CLOUD_FAIL_THRESHOLD = 3

_key_429: dict[str, float] = {}
_KEY_429_COOLDOWN = 60


def _key_id(key: str) -> str:
    return key[-10:] if len(key) >= 10 else key


def _key_available(key: str) -> bool:
    return time.time() - _key_429.get(_key_id(key), 0) >= _KEY_429_COOLDOWN


def _mark_cloud_fail(provider: str):
    _cloud_fail[provider] = _cloud_fail.get(provider, 0) + 1
    _cloud_fail_ts[provider] = time.time()


def _mark_cloud_ok(provider: str):
    _cloud_fail[provider] = 0


def _cloud_blocked(provider: str) -> bool:
    n = _cloud_fail.get(provider, 0)
    if n < _CLOUD_FAIL_THRESHOLD:
        return False
    return time.time() - _cloud_fail_ts.get(provider, 0) < _CLOUD_SKIP_SECS


_AUTH_ERROR   = object()
_RATE_LIMITED = object()


def _post(url: str, headers: dict, payload: dict, timeout: int = 20):
    """POST com hard timeout via thread — urllib não garante timeout total em respostas lentas."""
    result: list = [None]

    def _do():
        data = json.dumps(payload).encode("utf-8")
        req  = urllib.request.Request(url, data=data, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                result[0] = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            if e.code in (401, 403):
                log.warning(f"HTTP {url[:40]} auth error {e.code}")
                result[0] = _AUTH_ERROR
            elif e.code == 429:
                log.debug(f"HTTP {url[:40]} rate limited (429)")
                result[0] = _RATE_LIMITED
            else:
                log.debug(f"HTTP {url[:40]} falhou {e.code}: {e}")
        except Exception as e:
            log.debug(f"HTTP {url[:40]} falhou: {e}")

    t = threading.Thread(target=_do, daemon=True)
    t.start()
    t.join(timeout)
    if t.is_alive():
        log.debug(f"HTTP {url[:40]} hard timeout ({timeout}s)")
    return result[0]


def _extract_text(resp: dict) -> Optional[str]:
    try:
        return resp["choices"][0]["message"]["content"]
    except Exception:
        return None


def _strip_thinking(text: str) -> str:
    return re.sub(r"<think>.*?</think>", "", text or "", flags=re.DOTALL | re.IGNORECASE).strip()


def _json_from_text(text: str) -> dict | None:
    text = _strip_thinking(text or "")
    m = re.search(r"\{.*\}", text, flags=re.DOTALL)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except Exception:
        return None


# ── Provider genérico OpenAI-compat ─────────────────────────────────────────
#
# Centraliza circuit breaker + rotação de chaves + 2-pass (cooldown fallback).
# OpenRouter, Cerebras e Mistral são wrappers finos sobre esta função.

def _call_openai_compat(
    provider: str,
    url: str,
    keys: list,
    models: list,
    messages: list,
    *,
    max_tokens: int = 300,
    temperature: float = 0.85,
    timeout: int = 10,
    extra_headers: dict | None = None,
    extra_payload: dict | None = None,
) -> Optional[str]:
    if _cloud_blocked(provider) or not keys:
        log.debug(f"{provider} bloqueado ou sem chaves")
        return None

    def _try_keys(ks: list) -> Optional[str]:
        for key in ks:
            kid = _key_id(key)
            for model in models:
                headers = {
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {key}",
                    **(extra_headers or {}),
                }
                payload = {
                    "model": model,
                    "messages": messages,
                    "temperature": temperature,
                    "max_tokens": max_tokens,
                    **(extra_payload or {}),
                }
                resp = _post(url, headers, payload, timeout=timeout)
                if resp is _AUTH_ERROR:
                    _mark_cloud_fail(provider)
                    break
                if resp is _RATE_LIMITED:
                    _key_429[kid] = time.time()
                    log.debug(f"{provider} chave ...{kid} limitada (429), rotacionando")
                    break
                if resp:
                    text = _extract_text(resp)
                    if text and text.strip():
                        log.debug(f"{provider} ok: {model} (chave ...{kid})")
                        _mark_cloud_ok(provider)
                        return text.strip()
                _mark_cloud_fail(provider)
        return None

    result = _try_keys([k for k in keys if _key_available(k)])
    if result:
        return result
    cooled = [k for k in keys if not _key_available(k)]
    if cooled:
        log.debug(f"{provider}: chaves disponíveis esgotadas, tentando chaves em cooldown")
        result = _try_keys(cooled)
    return result


# ── Providers cloud ──────────────────────────────────────────────────────────

def _call_openrouter(messages: list, max_tokens: int = 300, temperature: float = 0.85,
                     timeout: int = 10) -> Optional[str]:
    return _call_openai_compat(
        "openrouter",
        "https://openrouter.ai/api/v1/chat/completions",
        OPENROUTER_KEYS, OPENROUTER_MODELS, messages,
        max_tokens=max_tokens, temperature=temperature, timeout=timeout,
        extra_headers={"HTTP-Referer": "https://hyrule.local", "X-Title": "LinkBot"},
        extra_payload={"reasoning": {"enabled": True, "effort": "low", "exclude": True}},
    )


def _call_cerebras(messages: list, max_tokens: int = 80, temperature: float = 0.0,
                   timeout: int = 3, models: list | None = None) -> Optional[str]:
    # Cloudflare bloqueia urllib sem User-Agent de browser
    return _call_openai_compat(
        "cerebras",
        "https://api.cerebras.ai/v1/chat/completions",
        CEREBRAS_KEYS, models or CEREBRAS_MODELS_FAST, messages,
        max_tokens=max_tokens, temperature=temperature, timeout=timeout,
        extra_headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"},
    )


def _call_mistral(messages: list, max_tokens: int = 300, temperature: float = 0.7,
                  timeout: int = 10) -> Optional[str]:
    return _call_openai_compat(
        "mistral",
        "https://api.mistral.ai/v1/chat/completions",
        MISTRAL_KEYS, MISTRAL_MODELS, messages,
        max_tokens=max_tokens, temperature=temperature, timeout=timeout,
    )


# ── Ollama local ─────────────────────────────────────────────────────────────

def _call_ollama(messages: list, think: bool = False, num_predict: int = 100,
                 temperature: float = 0.8, timeout: int = 90) -> Optional[str]:
    payload = {
        "model": OLLAMA_MODEL,
        "messages": messages,
        "stream": False,
        "think": think,
        "options": {
            "temperature": temperature,
            "top_p": 0.9,
            "repeat_penalty": 1.1,
            "num_predict": num_predict,
        },
    }
    resp = _post(OLLAMA_URL, {"Content-Type": "application/json"}, payload, timeout=timeout)
    if not resp:
        return None
    text = (resp.get("message", {}).get("content") or "").strip()
    return _strip_thinking(text) or None


# ── Tiers de qualidade ────────────────────────────────────────────────────────
#
# FAST    → Cerebras 8b (~0.3s) → OpenRouter → Ollama
#           Desiste rápido; Cerebras cobre bem JSON simples e classificação.
#
# QUALITY → Mistral small → OpenRouter → Ollama
#           Mistral é estável e rápido; OpenRouter fica como fallback.
#
# CHAT    → Cerebras 8b → Mistral → OpenRouter → Ollama compact
#           Contexto completo com persona; Ollama recebe versão reduzida.
#
# EMOJI   → Ollama only — latência de cloud não justifica para reação.

def _call_fast(messages: list, *, max_tokens: int = 80, temperature: float = 0.0,
               timeout: int = 5, ollama_timeout: int = 20) -> Optional[str]:
    return (
        _call_cerebras(messages, max_tokens=max_tokens, temperature=temperature, timeout=3)
        or _call_openrouter(messages, max_tokens=max_tokens, temperature=temperature, timeout=timeout)
        or _call_ollama(messages, think=False, num_predict=max_tokens,
                        temperature=temperature, timeout=ollama_timeout)
    )


def _call_quality(messages: list, *, max_tokens: int = 300, temperature: float = 0.7,
                  timeout: int = 12, ollama_timeout: int = 60) -> Optional[str]:
    # Mistral antes do OpenRouter — Mistral ~1s vs OpenRouter 10-90s
    return (
        _call_mistral(messages, max_tokens=max_tokens, temperature=temperature, timeout=8)
        or _call_openrouter(messages, max_tokens=max_tokens, temperature=temperature, timeout=timeout)
        or _call_ollama(messages, think=False, num_predict=max_tokens,
                        temperature=temperature, timeout=ollama_timeout)
    )


# ── Classificação de intent ───────────────────────────────────────────────────

def classify_skill_intent(message: str, skills: list[dict]) -> dict | None:
    """Classifica intenção de skill com IA. Retorna {"skill": nome|None, "args": str}."""
    if not message or not skills:
        return None

    catalog_full = "\n".join(
        f"- {item['name']}: {item.get('description', '')}"
        for item in skills if item.get("name")
    )
    catalog_short = "\n".join(
        f"- {item['name']}"
        for item in skills if item.get("name")
    )
    few_shots = (
        'Exemplos (entrada → saida JSON):\n'
        '"toca uma musica no spotify" → {"skill":"delirius_dl","args":"musica","confidence":0.95}\n'
        '"toca lost woods no youtube" → {"skill":"delirius_dl","args":"lost woods no youtube","confidence":0.96}\n'
        '"toca lost woods" → {"skill":"delirius_dl","args":"lost woods","confidence":0.88}\n'
        '"toca uma do Metallica" → {"skill":"delirius_dl","args":"Metallica","confidence":0.87}\n'
        '"baixa essa musica do youtube: https://youtu.be/abc" → {"skill":"delirius_dl","args":"https://youtu.be/abc","confidence":0.98}\n'
        '"coloca Bohemian Rhapsody" → {"skill":"delirius_dl","args":"Bohemian Rhapsody","confidence":0.89}\n'
        '"me manda uma foto de cachorro" → {"skill":"imagem_buscar","args":"cachorro","confidence":0.92}\n'
        '"gera uma imagem de dragao voando" → {"skill":"img_gerar","args":"dragao voando","confidence":0.95}\n'
        '"quanto ta o dolar?" → {"skill":"cotacao","args":"dolar","confidence":0.93}\n'
        '"traduz pra ingles: ola mundo" → {"skill":"tradutor","args":"pra ingles: ola mundo","confidence":0.97}\n'
        '"me lembra amanha as 9h de ligar pro medico" → {"skill":"lembrete_criar","args":"amanha as 9h ligar pro medico","confidence":0.96}\n'
        '"qual o clima em Sao Paulo?" → {"skill":"clima","args":"Sao Paulo","confidence":0.95}\n'
        '"manda um gif de gato" → {"skill":"delirius_gif","args":"gato","confidence":0.94}\n'
        '"fala isso em voz alta: hello world" → {"skill":"delirius_fala","args":"hello world","confidence":0.96}\n'
        '"encurta esse link: https://..." → {"skill":"encurtar","args":"https://...","confidence":0.95}\n'
        '"oi, tudo bem?" → {"skill":null,"args":"","confidence":0.97}\n'
        '"voce e mesmo o Link?" → {"skill":null,"args":"","confidence":0.95}\n'
    )
    system_full = (
        "Voce e um classificador de intencao para um assistente de WhatsApp chamado Link.\n"
        "O usuario fala em linguagem natural — sem comandos, sem prefixos. Seu trabalho:\n"
        "identificar qual skill executar, extrair os argumentos uteis e estimar confianca.\n\n"
        "REGRAS:\n"
        "- Escolha a skill quando a mensagem pede claramente uma acao (baixar, buscar, gerar, traduzir, lembrar, etc)\n"
        "- Voce pode usar aliases !comando internamente para decidir a skill, mesmo quando o usuario falou natural.\n"
        "- Se a mensagem contem !comando (ex: '!spot zelda'), use esse comando para identificar a skill.\n"
        "- Se tiver mais certeza por alias, pode retornar skill='!comando' ou args iniciando com '!comando'; o sistema resolve internamente.\n"
        "- Use null APENAS para conversa pura, saudacao, pergunta pessoal ou ambiguidade total\n"
        "- 'args': APENAS o conteudo util para a skill — sem @mencoes, sem palavras de ativacao, sem nome da skill\n"
        "- 'confidence': 0.0 a 1.0. Use < 0.7 quando for ambiguo. >= 0.85 quando for claro.\n"
        "Responda apenas JSON valido: {\"skill\": string|null, \"args\": string, \"confidence\": number}.\n\n"
        f"{few_shots}\n"
        f"Skills disponiveis:\n{catalog_full}"
    )
    system_short = (
        "Classificador de intencao para assistente WhatsApp. Usuario fala naturalmente.\n"
        "Retorne APENAS JSON: {\"skill\": string|null, \"args\": string, \"confidence\": number}.\n"
        "confidence >= 0.85 quando claro, < 0.7 quando ambiguo. null so para conversa pura.\n"
        "args = conteudo util para a skill, sem palavras de ativacao.\n\n"
        f"Skills:\n{catalog_short}"
    )
    messages_full = [
        {"role": "system", "content": system_full},
        {"role": "user", "content": message},
    ]
    messages_short = [
        {"role": "system", "content": system_short},
        {"role": "user", "content": message},
    ]
    # Cerebras + OpenRouter recebem prompt completo; Ollama recebe versão compacta (token limit)
    raw = (
        _call_cerebras(messages_full, max_tokens=80, temperature=0.0, timeout=3)
        or _call_openrouter(messages_full, max_tokens=80, temperature=0.0, timeout=5)
        or _call_ollama(messages_short, think=False, num_predict=60, temperature=0.0, timeout=15)
    )
    data = _json_from_text(raw or "")
    if not isinstance(data, dict):
        return None
    skill      = data.get("skill")
    args       = data.get("args", "")
    confidence = float(data.get("confidence", 1.0))
    if skill is not None and not isinstance(skill, str):
        return None
    if skill and confidence < 0.7:
        skill = None
    return {"skill": skill.strip() if isinstance(skill, str) else None, "args": str(args or "").strip()}


# ── Helpers de alto nível ────────────────────────────────────────────────────

_SKILL_PROMPTS_AUTO: dict[str, str] = {
    "spot":   "Sugira uma música aleatória e boa: artista - título.",
    "imagem": "Sugira um tema visual interessante para buscar uma imagem.",
    "img":    "Sugira um tema visual interessante para gerar uma imagem.",
}
_SKILL_FALLBACKS_AUTO: dict[str, str] = {
    "spot":   "Zelda - Main Theme",
    "imagem": "paisagem de Hyrule",
    "img":    "paisagem de Hyrule",
}
_CODE_SKILL_NAMES = {"triforce", "majora", "mastersword"}


def gerar_pergunta_skill(skill: str, msg_original: str, persona: str = "") -> str:
    system = persona or "Voce e Link, assistente casual. Responda em portugues, curto e direto."
    msgs = [
        {"role": "system", "content": system},
        {"role": "user", "content": (
            f"[interno: usuario pediu '{msg_original}' mas nao especificou qual {skill}. "
            "Faz uma pergunta curta e casual pra ele dizer qual quer, "
            "e menciona de forma natural que pode escolher por ele se quiser]"
        )},
    ]
    raw = _call_quality(msgs, max_tokens=80, temperature=0.85, timeout=8)
    return _strip_thinking(raw or "").strip()


def resolver_pendente(skill: str, resposta: str) -> tuple[str, str]:
    """Interpreta resposta do usuário para pedido pendente. Retorna (action, args)."""
    msgs = [
        {"role": "system", "content": (
            f"Voce interpreta a resposta do usuario para a skill '{skill}'.\n"
            f"Skills de codigo (nao podem auto-escolher): {', '.join(_CODE_SKILL_NAMES)}.\n"
            "Se o usuario especificou algo concreto → {\"action\":\"use\",\"args\":\"o que ele disse\"}\n"
            "Se quer que a IA escolha E skill NAO e codigo → {\"action\":\"choose\",\"args\":\"\"}\n"
            "Se quer que a IA escolha E skill E codigo → {\"action\":\"cannot_choose\",\"args\":\"\"}\n"
            "Responda APENAS JSON valido."
        )},
        {"role": "user", "content": resposta},
    ]
    raw  = _call_fast(msgs, max_tokens=60, temperature=0.0, timeout=6)
    data = _json_from_text(raw or "")
    if data and data.get("action") in ("use", "choose", "cannot_choose"):
        return data["action"], str(data.get("args") or "")
    return "use", resposta


def ia_escolher_args(skill: str) -> str:
    prompt = _SKILL_PROMPTS_AUTO.get(skill)
    if not prompt:
        return ""
    msgs = [
        {"role": "system", "content": "Responda APENAS com o nome/termo, sem explicacao."},
        {"role": "user", "content": prompt},
    ]
    raw = _call_fast(msgs, max_tokens=40, temperature=0.9, timeout=6, ollama_timeout=15)
    return _strip_thinking(raw or "").strip() or _SKILL_FALLBACKS_AUTO.get(skill, "")


def extract_image_query(message: str, usuario: str = "") -> str | None:
    if not message or not message.strip():
        return None
    system = (
        "Voce extrai a consulta ideal para buscar uma imagem na web.\n"
        "Contexto: quem responde e Link, heroi de Zelda/Hyrule.\n"
        "Resolva pronomes pelo contexto da conversa: 'sua foto', 'foto de voce', "
        "'foto dele' quando se referir ao bot/personagem = Link, personagem de The Legend of Zelda.\n"
        "Prefira termos visuais especificos. Para retrato/foto do Link, use: Link character portrait.\n"
        "Para objetos, use o nome do objeto sem comandos extras.\n"
        "Nao inclua palavras como buscar, mandar, enviar, web, internet, google.\n"
        "Responda somente JSON valido: {\"query\":\"...\"}."
    )
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": f"Usuario: {usuario or 'desconhecido'}\nPedido: {message}"},
    ]
    raw   = _call_fast(messages, max_tokens=60, temperature=0.0, timeout=6, ollama_timeout=20)
    data  = _json_from_text(raw or "")
    query = str((data or {}).get("query") or "").strip()
    return query[:120] or None


def spotify_search_queries(message: str) -> list[str]:
    """Transforma pedido livre em consultas Spotify. Retorna [] se o LLM falhar."""
    if not message or not message.strip():
        return []
    system = (
        "Voce prepara buscas para encontrar a faixa ORIGINAL no Spotify.\n"
        "Receba o pedido do usuario, corrija erros comuns de digitacao, identifique titulo e artista "
        "quando possivel, e remova palavras de comando como baixar, manda, mp3, spot.\n"
        "IMPORTANTE: se o pedido menciona um jogo, filme, serie ou franquia (ex: 'musica do zelda', "
        "'trilha do mario', 'tema do star wars'), gere queries como 'Legend of Zelda Main Theme', "
        "'Super Mario OST', 'Star Wars Main Theme John Williams' — nao invente artistas populares.\n"
        "Se houver 'Contexto musical anterior:' e o pedido for 'outra famosa', 'mais uma', "
        "'da mesma banda' ou parecido, use o artista/banda/faixa do contexto para escolher outra musica "
        "famosa relacionada. Nao escolha musica aleatoria fora desse contexto.\n"
        "Por padrao sempre priorize a gravacao original/oficial. Evite karaoke, cover, remix, "
        "instrumental, sped up, slowed, live e tribute, a menos que o usuario tenha pedido "
        "explicitamente essa versao alternativa.\n"
        "Monte 1 a 4 consultas curtas em ordem de chance. Prefira 'titulo artista'.\n"
        "Responda somente JSON valido: {\"queries\":[\"...\"]}."
    )
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": message},
    ]
    raw   = _call_quality(messages, max_tokens=120, temperature=0.0, timeout=10, ollama_timeout=30)
    data  = _json_from_text(raw or "")
    items = (data or {}).get("queries")
    if not isinstance(items, list):
        return []

    seen: set[str] = set()
    queries: list[str] = []
    for item in items:
        q = re.sub(r"\s+", " ", str(item or "")).strip()
        if not q or len(q) > 120:
            continue
        key = q.casefold()
        if key in seen:
            continue
        seen.add(key)
        queries.append(q)
        if len(queries) >= 4:
            break
    return queries


def choose_reaction_emoji(
    message: str,
    *,
    usuario: str = "",
    skill_name: str = "",
    skill_category: str = "",
    has_media: bool = False,
    media_type: str = "",
    is_admin: bool = False,
) -> str | None:
    if not message and not has_media:
        return None
    system = (
        "Voce escolhe UMA reacao emoji para uma mensagem no WhatsApp.\n"
        "Interprete o contexto real da mensagem, intencao, tom, midia anexada e skill acionada.\n"
        "Contexto: este WhatsApp e um assistente chamado Link/Hyrule. 'menu' significa menu de comandos, nunca comida; nao use 🍔 nesse caso.\n"
        "Nao responda texto, explicacao, markdown ou JSON. Responda somente UM emoji.\n"
        "Escolha emojis comuns que funcionem bem como reacao do WhatsApp.\n"
        "Evite repetir sempre o mesmo emoji; varie conforme o sentido.\n"
        "Se for impossivel inferir, use ⚔️."
    )
    user = (
        f"Usuario: {usuario or 'desconhecido'}\n"
        f"Mensagem: {message or '[sem texto]'}\n"
        f"Skill: {skill_name or 'nenhuma'}\n"
        f"Categoria: {skill_category or 'nenhuma'}\n"
        f"Tem midia: {'sim' if has_media else 'nao'}\n"
        f"Tipo da midia: {media_type or 'nenhum'}\n"
        f"Admin: {'sim' if is_admin else 'nao'}"
    )
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]
    # Emoji não justifica latência de cloud — Ollama local é suficiente
    raw  = _call_ollama(messages, think=False, num_predict=8, temperature=0.2, timeout=4)
    text = _strip_thinking(raw or "").strip()
    if not text:
        return None

    text  = re.sub(r"[\s`\"'.,;:!?()\[\]{}<>]+", "", text)
    emoji = text[:2] if len(text) >= 2 and text[1] in ("️", "⃣") else text[:1]

    # Nunca usar emojis negativos como reação — usuário não precisa saber de estados internos
    _BLOCKED = {"⛔", "🚫", "❌", "🔴", "📵", "🔇", "⚠️", "🛑", "💔", "👎", "🤬", "😡"}
    if emoji in _BLOCKED:
        return None

    return emoji or None


# ── Submissão de tarefas e processamento de tags ─────────────────────────────

def _submeter_tarefa_wpp(pedido: str, usuario: str, sender_id: str, tipo: str = "sheikah"):
    fila: list = []
    if _WPP_TASKS.exists():
        try:
            fila = json.loads(_WPP_TASKS.read_text(encoding="utf-8"))
        except Exception:
            fila = []
    fila.append({
        "ts":        time.strftime("%Y-%m-%d %H:%M:%S"),
        "pedido":    pedido,
        "usuario":   usuario,
        "sender_id": sender_id,
        "canal":     "whatsapp",
        "tipo":      tipo,
    })
    _WPP_TASKS.write_text(json.dumps(fila, ensure_ascii=False, indent=2), encoding="utf-8")
    log.debug(f"WPP task ({tipo}): {pedido[:80]}")


def _processar_tags(reply: str, user_id: str, usuario: str) -> tuple[str, str]:
    """Extrai e enfileira tags SHEIKAH_SLATE/TRIFORCE/MAJORA/MASTERSWORD do reply do LLM."""
    _TAGS = {
        "SHEIKAH_SLATE": "sheikah",
        "TRIFORCE":      "triforce",
        "MAJORA":        "majora",
        "MASTERSWORD":   "mastersword",
    }
    for tag, tipo in _TAGS.items():
        tarefas = re.findall(rf'\[{tag}:\s*(.+?)\]', reply, re.IGNORECASE | re.DOTALL)
        if tarefas:
            for t in tarefas:
                _submeter_tarefa_wpp(t.strip(), usuario, user_id, tipo=tipo)
            reply = re.sub(rf'\[{tag}:\s*.+?\]', '', reply, flags=re.IGNORECASE | re.DOTALL).strip()
    return reply, ""


def _is_owner(user_id: str) -> bool:
    try:
        from bot.core import access as access_ctl
        return access_ctl.is_admin(user_id)
    except Exception:
        return False


def _system_owner_block(owner: bool, usuario: str) -> str:
    owner_name = _owner_name()
    if owner:
        return (
            f"\n\n# Esta mensagem é do {owner_name} — o dono e parceiro desse sistema.\n"
            f"O nome real dele é {owner_name}. Nunca chame ele de OWNER; isso é só placeholder interno.\n"
            "Ele é quem criou tudo isso, tem acesso total e mando sobre qualquer configuração.\n"
            "Trate-o como parceiro de longa data, sem formalidade."
        )
    return (
        f"\n\n# Esta mensagem é de {usuario}, um usuário comum autorizado.\n"
        "Não trate essa pessoa como OWNER e não diga que ela é dona do sistema."
    )


# ── Entry points ─────────────────────────────────────────────────────────────

def rewrite_for_tts(text: str) -> str:
    """Reescreve texto para TTS: mais natural, abreviações expandidas. Retorna original se falhar."""
    messages = [
        {"role": "system", "content": (
            "Você é um editor de texto para síntese de voz (TTS). "
            "Receba o texto e reescreva-o de forma mais natural, fluida e agradável ao ouvido, "
            "corrigindo gramática, expandindo abreviações e melhorando o fluxo da frase. "
            "Mantenha o idioma original. Retorne APENAS o texto reescrito, sem explicações."
        )},
        {"role": "user", "content": text},
    ]
    result = _call_quality(messages, max_tokens=300, temperature=0.7)
    return result.strip() if result and result.strip() else text


def chat(user_id: str, user_message: str, usuario: str = "OWNER") -> str:
    """
    Gera resposta LLM com persona Link.
    Tags SHEIKAH_SLATE/TRIFORCE/MAJORA/MASTERSWORD são processadas e removidas do reply.
    """
    _add_to_history(user_id, "user", user_message)

    system = _load_persona() + _system_owner_block(_is_owner(user_id), usuario)
    if _skill_catalog:
        system += f"\n\n# Comandos disponíveis neste bot\n{_skill_catalog}"

    messages = [{"role": "system", "content": system}] + _get_history(user_id)

    # Cerebras 8b (~0.5s) → Mistral (~1s) → OpenRouter (lento, último recurso) → Ollama
    raw_reply = (
        _call_cerebras(messages, max_tokens=300, temperature=0.85, timeout=6)
        or _call_mistral(messages, max_tokens=300, temperature=0.85, timeout=10)
        or _call_openrouter(messages, max_tokens=300, temperature=0.85, timeout=10)
    )
    if not raw_reply:
        owner_name = _owner_name()
        sys_local  = (
            f"Voce e Link, parceiro do {owner_name}. Responda em portugues, curto e direto. "
            "Nunca se identifique como IA ou bot." + _PERSONA_WHATSAPP_ADDON
        )
        msgs_local = [{"role": "system", "content": sys_local}] + _get_history(user_id)[-4:]
        raw_reply  = _call_ollama(msgs_local, think=False, num_predict=80, timeout=60)

    reply, feedback = _processar_tags(raw_reply or "🌀", user_id, usuario)
    reply = (feedback + "\n" + reply).strip() if feedback else reply
    reply = _finalize_reply(reply or "🌀", user_id)

    _add_to_history(user_id, "assistant", reply)
    return reply


def chat_local(user_id: str, user_message: str, usuario: str = "OWNER", think: bool = False) -> str:
    """Força conversa direta com Ollama local, sem providers cloud."""
    _add_to_history(user_id, "user", user_message)

    system = (
        _load_local_persona()
        + "\n\n# Modo local\n"
        + f"Voce esta respondendo pelo modelo local do {_owner_name()}. Pense internamente se precisar, "
        + "mas entregue so a resposta final, curta e natural."
        + _system_owner_block(_is_owner(user_id), usuario)
    )

    messages  = [{"role": "system", "content": system}] + _get_history(user_id)
    raw_reply = _call_ollama(messages, think=think)
    if think and not raw_reply:
        raw_reply = _call_ollama(messages, think=False)

    reply, feedback = _processar_tags(raw_reply or "não consegui falar com o local agora", user_id, usuario)
    reply = (feedback + "\n" + reply).strip() if feedback else reply
    reply = _finalize_reply(reply or "🌀", user_id)

    _add_to_history(user_id, "assistant", reply)
    return reply


def chat_local_tools(user_id: str, user_message: str, usuario: str = "OWNER") -> str:
    """Usa executor local com tools para !zpensa; cai no chat_local puro se nada resolver."""
    try:
        import bot_supervisor as supervisor

        p        = supervisor._normalizar(user_message)
        quer_web = any(x in p for x in ["busca", "pesquis", "internet", "google", "procur", "duckduck", "web"])
        quer_img = any(x in p for x in ["imagem", "foto", "png", "jpg", "figura", "ilustracao", "artwork", "arte"])
        if quer_web and not quer_img:
            raw_reply = supervisor.buscar_internet(user_message)
            if raw_reply:
                _add_to_history(user_id, "user", user_message)
                _add_to_history(user_id, "assistant", raw_reply)
                return raw_reply

        if supervisor.ollama_disponivel():
            raw_reply = supervisor.executar_qwen_react(
                user_message, usuario, usar_todas_tools=False, max_rodadas=3
            )
            if raw_reply:
                reply, feedback = _processar_tags(raw_reply, user_id, usuario)
                reply = (feedback + "\n" + reply).strip() if feedback else reply
                reply = _finalize_reply(reply or "🌀", user_id)
                _add_to_history(user_id, "user", user_message)
                _add_to_history(user_id, "assistant", reply)
                return reply
    except Exception as e:
        log.warning(f"chat_local_tools falhou: {e}")

    return chat_local(user_id, user_message, usuario, think=True)
