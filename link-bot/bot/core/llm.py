"""
Fallback LLM para mensagens sem skill match.
Hierarquia: OpenRouter → Groq → Ollama local → resposta padrão.
Carrega LINK_PERSONA.md como system prompt.
"""

import json
import re
import time
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
    "meta-llama/llama-3.1-8b-instant:free",
    "google/gemini-2.0-flash-exp:free",
    "meta-llama/llama-3.3-70b-instruct:free",
    "mistralai/mistral-small-3.2-24b-instruct:free",
]

GROQ_KEYS = _GROQ_KEYS_FROM_ENV
GROQ_MODELS = [
    "llama-3.3-70b-versatile",
    "llama-3.1-70b-versatile",
    "llama-3.1-8b-instant",
]
GROQ_HEADERS = {
    "Content-Type": "application/json",
    "User-Agent":   "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept":       "application/json",
    "Origin":       "https://console.groq.com",
    "Referer":      "https://console.groq.com/",
}

OLLAMA_URL = "http://localhost:11434/api/chat"
OLLAMA_MODEL = "qwen3:8b"

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

# ── Filas de tarefas ─────────────────────────────────────────────────────────

_AGENTS_DIR = Path(__file__).resolve().parents[3]
_WPP_TASKS  = _AGENTS_DIR / "whatsapp_tasks.json"
_CLAUDE_Q   = _AGENTS_DIR / "claude_queue.json"


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
    """Recebe o catálogo de skills gerado em main.py e guarda para injetar no system prompt."""
    global _skill_catalog
    _skill_catalog = catalog


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

_cloud_fail: dict[str, int] = {}   # provider → consecutive failures
_cloud_fail_ts: dict[str, float] = {}
_CLOUD_SKIP_SECS = 180
_CLOUD_FAIL_THRESHOLD = 3


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


_AUTH_ERROR = object()  # sentinel: indica erro 401/403


def _post(url: str, headers: dict, payload: dict, timeout: int = 20):
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        if e.code in (401, 403):
            log.warning(f"HTTP {url[:40]} auth error {e.code}")
            return _AUTH_ERROR
        log.debug(f"HTTP {url[:40]} falhou {e.code}: {e}")
        return None
    except Exception as e:
        log.debug(f"HTTP {url[:40]} falhou: {e}")
        return None


def _extract_text(resp: dict) -> Optional[str]:
    try:
        return resp["choices"][0]["message"]["content"]
    except Exception:
        return None


def _strip_thinking(text: str) -> str:
    return re.sub(r"<think>.*?</think>", "", text or "", flags=re.DOTALL | re.IGNORECASE).strip()


# ── OpenRouter ───────────────────────────────────────────────────────────────

def _call_openrouter(messages: list, max_tokens: int = 300, temperature: float = 0.85, timeout: int = 10) -> Optional[str]:
    if _cloud_blocked("openrouter"):
        log.debug("OpenRouter bloqueado pelo circuit breaker")
        return None
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
                "temperature": temperature,
                "max_tokens": max_tokens,
                "reasoning": {"enabled": True, "effort": "low", "exclude": True},
            }
            resp = _post("https://openrouter.ai/api/v1/chat/completions", headers, payload, timeout=timeout)
            if resp is _AUTH_ERROR:
                _mark_cloud_fail("openrouter")
                break  # chave inválida — pula outros modelos desta chave
            if resp:
                text = _extract_text(resp)
                if text and text.strip():
                    log.debug(f"OpenRouter ok: {model}")
                    _mark_cloud_ok("openrouter")
                    return text.strip()
            _mark_cloud_fail("openrouter")
    return None


# ── Groq ─────────────────────────────────────────────────────────────────────

def _call_groq(messages: list, max_tokens: int = 300, temperature: float = 0.85, timeout: int = 20) -> Optional[str]:
    if _cloud_blocked("groq"):
        log.debug("Groq bloqueado pelo circuit breaker")
        return None
    for key in GROQ_KEYS:
        for model in GROQ_MODELS:
            headers = {**GROQ_HEADERS, "Authorization": f"Bearer {key}"}
            payload = {
                "model": model,
                "messages": messages,
                "temperature": temperature,
                "max_tokens": max_tokens,
            }
            resp = _post("https://api.groq.com/openai/v1/chat/completions", headers, payload, timeout=timeout)
            if resp is _AUTH_ERROR:
                _mark_cloud_fail("groq")
                break  # chave inválida — pula outros modelos desta chave
            if resp:
                text = _extract_text(resp)
                if text and text.strip():
                    log.debug(f"Groq ok: {model}")
                    _mark_cloud_ok("groq")
                    return text.strip()
            _mark_cloud_fail("groq")
    return None


# ── Ollama local ─────────────────────────────────────────────────────────────

def _call_ollama(messages: list, think: bool = False, num_predict: int = 100, temperature: float = 0.8, timeout: int = 90) -> Optional[str]:
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
    text = _strip_thinking(text)
    return text or None


# ── Delirius LLM (free, sem chave) ───────────────────────────────────────────

_DELIRIUS_BASE = "https://api.delirius.store"


def _build_delirius_prompt(user_message: str) -> str:
    """Monta o prompt para Delirius embutindo identidade + catálogo de skills.
    A API Delirius não suporta system prompt, então tudo vai no campo ?q=.
    Limita a 900 chars para não estourar a URL.
    """
    identity = (
        "Você é Link, assistente no WhatsApp do Hyrule. "
        "Responda em português do Brasil, curto e direto. "
        "Nunca diga que é IA ou bot.\n"
    )
    catalog_block = ""
    if _skill_catalog:
        # Versão compacta: só os triggers e primeira descrição de cada skill
        linhas = []
        for linha in _skill_catalog.splitlines():
            linhas.append(linha)
            if len("\n".join(linhas)) > 400:
                break
        catalog_block = "Comandos disponíveis:\n" + "\n".join(linhas) + "\n"

    prompt = f"{identity}{catalog_block}\nPergunta: {user_message}"
    return prompt[:900]


def _call_delirius_llm(user_message: str, timeout: int = 15) -> Optional[str]:
    """Tenta chatgpt e gemini da Delirius Store (free, sem chave).
    Embute identidade + catálogo de skills no próprio ?q= já que a API não suporta system prompt.
    Primeiro fallback remoto — acionado antes de OpenRouter/Groq.
    """
    if _cloud_blocked("delirius"):
        return None

    import urllib.parse as _up
    prompt = _build_delirius_prompt(user_message)
    for path, param in (
        ("/ia/chatgpt", "q"),
        ("/ia/gemini",  "query"),
    ):
        url = f"{_DELIRIUS_BASE}{path}?{_up.urlencode({param: prompt})}"
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "HyruleBot/1.0"})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            # Extrai texto de vários formatos de resposta possíveis
            text = (
                data.get("result")
                or data.get("response")
                or data.get("answer")
                or data.get("message")
                or (data.get("data") or {}).get("result")
                or (data.get("data") or {}).get("response")
            )
            if text and str(text).strip():
                log.debug(f"Delirius LLM ok: {path}")
                _mark_cloud_ok("delirius")
                return str(text).strip()
        except urllib.error.HTTPError as e:
            if e.code in (401, 403, 429):
                _mark_cloud_fail("delirius")
            log.debug(f"Delirius {path} falhou HTTP {e.code}")
        except Exception as e:
            log.debug(f"Delirius {path} falhou: {e}")
            _mark_cloud_fail("delirius")

    return None


def _json_from_text(text: str) -> dict | None:
    text = _strip_thinking(text or "")
    m = re.search(r"\{.*\}", text, flags=re.DOTALL)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except Exception:
        return None


def classify_skill_intent(message: str, skills: list[dict]) -> dict | None:
    """Classifica intenção de skill com IA. Retorna {"skill": nome|None, "args": str}."""
    if not message or not skills:
        return None

    # Para Ollama: catalogo só com nomes (sem descrições) para reduzir o contexto
    catalog_full = "\n".join(
        f"- {item['name']}: {item.get('description', '')}"
        for item in skills
        if item.get("name")
    )
    catalog_short = "\n".join(
        f"- {item['name']}"
        for item in skills
        if item.get("name")
    )
    system_full = (
        "Voce e um classificador de intencao para um bot WhatsApp.\n"
        "O usuario pode pedir qualquer coisa em linguagem natural, sem usar comandos.\n"
        "Seu trabalho: identificar qual skill executar E extrair os argumentos limpos.\n\n"
        "REGRAS:\n"
        "- Escolha a skill quando a mensagem indica claramente uma acao (baixar musica, gerar imagem, TTS, buscar gif, etc)\n"
        "- Use null so para conversa pura, saudacao, pergunta pessoal ou ambiguidade total\n"
        "- Em 'args': coloque APENAS o conteudo util para a skill — sem @mencoes, sem palavras de comando, sem nome da skill\n"
        "  Exemplos: 'toca star wars no spotify' → args='star wars'; 'faz um gif de cachorro feliz' → args='cachorro feliz'\n"
        "  'gera uma imagem de dragao' → args='dragao'; 'fala oi mundo' → args='oi mundo'\n"
        "- Nao acione lembrete quando a pessoa perguntar se voce a conhece\n"
        "Responda apenas JSON valido: {\"skill\": string|null, \"args\": string}.\n\n"
        f"Skills disponiveis:\n{catalog_full}"
    )
    system_short = (
        "Classificador de intencao WhatsApp. Usuario fala em linguagem natural.\n"
        "Retorne APENAS JSON: {\"skill\": string|null, \"args\": string}.\n"
        "args = conteudo util para a skill, sem @mencoes nem palavras de comando.\n"
        "Use null so para conversa pura ou saudacao.\n\n"
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
    raw = (
        _call_openrouter(messages_full, max_tokens=80, temperature=0.0, timeout=6)
        or _call_ollama(messages_short, think=False, num_predict=60, temperature=0.0, timeout=15)
    )
    data = _json_from_text(raw or "")
    if not isinstance(data, dict):
        return None
    skill = data.get("skill")
    args = data.get("args", "")
    if skill is not None and not isinstance(skill, str):
        return None
    return {"skill": skill.strip() if isinstance(skill, str) else None, "args": str(args or "").strip()}


def extract_image_query(message: str, usuario: str = "") -> str | None:
    """Usa IA para transformar um pedido de imagem em termo de busca visual."""
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
    user = f"Usuario: {usuario or 'desconhecido'}\nPedido: {message}"
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]
    raw = (
        _call_openrouter(messages, max_tokens=60, temperature=0.0)
        or _call_ollama(messages, think=False, num_predict=60, temperature=0.0, timeout=20)
    )
    data = _json_from_text(raw or "")
    query = str((data or {}).get("query") or "").strip()
    return query[:120] or None


def spotify_search_queries(message: str) -> list[str]:
    """Transforma um pedido livre em consultas Spotify prováveis.

    Retorna lista vazia se o LLM falhar; o chamador deve cair no texto original.
    """
    if not message or not message.strip():
        return []

    system = (
        "Voce prepara buscas para encontrar a faixa ORIGINAL no Spotify.\n"
        "Receba o pedido do usuario, corrija erros comuns de digitacao, identifique titulo e artista "
        "quando possivel, e remova palavras de comando como baixar, manda, musica, mp3, spot.\n"
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
    raw = (
        _call_openrouter(messages, max_tokens=120, temperature=0.0, timeout=12)
        or _call_ollama(messages, think=False, num_predict=100, temperature=0.0, timeout=25)
    )
    data = _json_from_text(raw or "")
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
    """Usa LLM para escolher uma única reação de WhatsApp pelo contexto atual."""
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

    def _openrouter_fast() -> str | None:
        if not OPENROUTER_KEYS or not OPENROUTER_MODELS:
            return None
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {OPENROUTER_KEYS[0]}",
            "HTTP-Referer": "https://hyrule.local",
            "X-Title": "LinkBot",
        }
        payload = {
            "model": OPENROUTER_MODELS[0],
            "messages": messages,
            "temperature": 0.25,
            "max_tokens": 8,
            "reasoning": {"enabled": True, "effort": "low", "exclude": True},
        }
        resp = _post("https://openrouter.ai/api/v1/chat/completions", headers, payload, timeout=5)
        if resp is _AUTH_ERROR or not resp:
            return None
        return _extract_text(resp)

    def _groq_fast() -> str | None:
        if not GROQ_KEYS or not GROQ_MODELS:
            return None
        headers = {**GROQ_HEADERS, "Authorization": f"Bearer {GROQ_KEYS[0]}"}
        payload = {
            "model": GROQ_MODELS[0],
            "messages": messages,
            "temperature": 0.25,
            "max_tokens": 8,
        }
        resp = _post("https://api.groq.com/openai/v1/chat/completions", headers, payload, timeout=5)
        if resp is _AUTH_ERROR or not resp:
            return None
        return _extract_text(resp)

    raw = (
        _openrouter_fast()
        or _call_ollama(messages, think=False, num_predict=8, temperature=0.2, timeout=5)
    )
    text = _strip_thinking(raw or "").strip()
    if not text:
        return None

    # Pega o primeiro grapheme emoji de forma conservadora para evitar texto junto.
    text = re.sub(r"[\s`\"'.,;:!?()\[\]{}<>]+", "", text)
    if not text:
        return None
    emoji = text[:2] if len(text) >= 2 and text[1] in ("\ufe0f", "\u20e3") else text[:1]

    # Nunca usar emojis negativos/de erro como rea\u00e7\u00e3o \u2014 usu\u00e1rio n\u00e3o precisa saber de estados internos
    _BLOCKED_REACTIONS = {"\u26d4", "\ud83d\udeab", "\u274c", "\ud83d\udd34", "\ud83d\udcf5", "\ud83d\udd07", "\u26a0\ufe0f", "\ud83d\uded1", "\ud83d\udc94", "\ud83d\udc4e", "\ud83e\udd2c", "\ud83d\ude21"}
    if emoji in _BLOCKED_REACTIONS:
        return None

    return emoji or None


# ── Entry point ───────────────────────────────────────────────────────────────

def _submeter_tarefa_wpp(pedido: str, usuario: str, sender_id: str, tipo: str = "sheikah"):
    """Escreve tarefa em whatsapp_tasks.json para o supervisor processar."""
    fila = []
    if _WPP_TASKS.exists():
        try:
            fila = json.loads(_WPP_TASKS.read_text(encoding="utf-8"))
        except Exception:
            fila = []
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    fila.append({
        "ts":        ts,
        "pedido":    pedido,
        "usuario":   usuario,
        "sender_id": sender_id,
        "canal":     "whatsapp",
        "tipo":      tipo,
    })
    _WPP_TASKS.write_text(json.dumps(fila, ensure_ascii=False, indent=2), encoding="utf-8")
    log.debug(f"WPP task ({tipo}): {pedido[:80]}")


def _processar_tags(reply: str, user_id: str, usuario: str) -> tuple:
    """
    Extrai SHEIKAH_SLATE e TRIFORCE do reply do LLM.
    Retorna (reply_sanitizado, feedback_extra).
    Submete tarefas ao supervisor via whatsapp_tasks.json.
    """
    feedback = ""

    # SHEIKAH_SLATE — tarefa do PC
    tarefas_sk = re.findall(r'\[SHEIKAH_SLATE:\s*(.+?)\]', reply, re.IGNORECASE | re.DOTALL)
    if tarefas_sk:
        for t in tarefas_sk:
            _submeter_tarefa_wpp(t.strip(), usuario, user_id, tipo="sheikah")
        reply = re.sub(r'\[SHEIKAH_SLATE:\s*.+?\]', '', reply, flags=re.IGNORECASE | re.DOTALL).strip()

    # TRIFORCE — escala pro Claude Code
    tarefas_tf = re.findall(r'\[TRIFORCE:\s*(.+?)\]', reply, re.IGNORECASE | re.DOTALL)
    if tarefas_tf:
        for t in tarefas_tf:
            _submeter_tarefa_wpp(t.strip(), usuario, user_id, tipo="triforce")
        reply = re.sub(r'\[TRIFORCE:\s*.+?\]', '', reply, flags=re.IGNORECASE | re.DOTALL).strip()

    # MAJORA — escala pro Codex CLI
    tarefas_mx = re.findall(r'\[MAJORA:\s*(.+?)\]', reply, re.IGNORECASE | re.DOTALL)
    if tarefas_mx:
        for t in tarefas_mx:
            _submeter_tarefa_wpp(t.strip(), usuario, user_id, tipo="majora")
        reply = re.sub(r'\[MAJORA:\s*.+?\]', '', reply, flags=re.IGNORECASE | re.DOTALL).strip()

    # MASTERSWORD — escala pro OpenCode
    tarefas_ms = re.findall(r'\[MASTERSWORD:\s*(.+?)\]', reply, re.IGNORECASE | re.DOTALL)
    if tarefas_ms:
        for t in tarefas_ms:
            _submeter_tarefa_wpp(t.strip(), usuario, user_id, tipo="mastersword")
        reply = re.sub(r'\[MASTERSWORD:\s*.+?\]', '', reply, flags=re.IGNORECASE | re.DOTALL).strip()

    return reply, feedback


def _is_owner(user_id: str) -> bool:
    try:
        from bot.core import access as access_ctl
        return access_ctl.is_admin(user_id)
    except Exception:
        return False


def rewrite_for_tts(text: str) -> str:
    """Melhora o texto para fala: corrige gramática, expande abreviações,
    torna a frase mais natural e fluida. Retorna o texto original se o LLM falhar."""
    messages = [
        {
            "role": "system",
            "content": (
                "Você é um editor de texto para síntese de voz (TTS). "
                "Receba o texto e reescreva-o de forma mais natural, fluida e agradável ao ouvido, "
                "corrigindo gramática, expandindo abreviações e melhorando o fluxo da frase. "
                "Mantenha o idioma original. Retorne APENAS o texto reescrito, sem explicações."
            ),
        },
        {"role": "user", "content": text},
    ]
    result = (
        _call_openrouter(messages, max_tokens=300, temperature=0.7)
        or _call_ollama(messages, num_predict=200, temperature=0.7)
    )
    return result.strip() if result and result.strip() else text


def chat(user_id: str, user_message: str, usuario: str = "OWNER") -> str:
    """
    Gera resposta LLM com persona Link.
    user_id: número/LID do WhatsApp (string)
    usuario: nome do usuário para o supervisor (padrão OWNER)
    Retorna reply sanitizado. Tags SHEIKAH_SLATE/TRIFORCE são processadas e removidas.
    Se TRIFORCE/MAJORA detectado, enfileira a tarefa e retorna o reply sanitizado.
    """
    _add_to_history(user_id, "user", user_message)

    system = _load_persona()
    if _is_owner(user_id):
        owner_name = _owner_name()
        system += (
            f"\n\n# Esta mensagem é do {owner_name} — o dono e parceiro desse sistema.\n"
            f"O nome real dele é {owner_name}. Nunca chame ele de OWNER; isso é só placeholder interno.\n"
            "Ele é quem criou tudo isso, tem acesso total e mando sobre qualquer configuração.\n"
            "Trate-o como parceiro de longa data, sem formalidade."
        )
    else:
        system += (
            f"\n\n# Esta mensagem é de {usuario}, um usuário comum autorizado.\n"
            "Não trate essa pessoa como OWNER e não diga que ela é dona do sistema."
        )
    if _skill_catalog:
        system += f"\n\n# Comandos disponíveis neste bot\n{_skill_catalog}"

    messages = [{"role": "system", "content": system}] + _get_history(user_id)

    # Delirius (free, sem auth) → OpenRouter → Ollama
    raw_reply = (
        _call_delirius_llm(user_message)
        or _call_openrouter(messages)
    )
    if not raw_reply:
        # Ollama local: usa persona compacta + últimas 4 msgs para caber no timeout
        owner_name = _owner_name()
        sys_local = (
            f"Voce e Link, parceiro do {owner_name}. Responda em portugues, curto e direto. "
            "Nunca se identifique como IA ou bot." + _PERSONA_WHATSAPP_ADDON
        )
        msgs_local = [{"role": "system", "content": sys_local}] + _get_history(user_id)[-4:]
        raw_reply = _call_ollama(msgs_local, think=False, num_predict=80, timeout=60)

    if not raw_reply:
        raw_reply = "🌀"

    reply, feedback = _processar_tags(raw_reply, user_id, usuario)

    if not reply:
        reply = feedback or "🌀"
    elif feedback:
        reply = f"{feedback}\n{reply}".strip()
    reply = _finalize_reply(reply, user_id)

    _add_to_history(user_id, "assistant", reply)
    return reply


def chat_local(user_id: str, user_message: str, usuario: str = "OWNER", think: bool = False) -> str:
    """Força conversa direta com o Ollama local, sem OpenRouter/Groq."""
    _add_to_history(user_id, "user", user_message)

    system = _load_local_persona()
    system += (
        "\n\n# Modo local\n"
        f"Voce esta respondendo pelo modelo local do {_owner_name()}. Pense internamente se precisar, "
        "mas entregue so a resposta final, curta e natural."
    )
    if _is_owner(user_id):
        owner_name = _owner_name()
        system += (
            f"\n\n# Esta mensagem é do {owner_name} — o dono e parceiro desse sistema.\n"
            f"O nome real dele é {owner_name}. Nunca chame ele de OWNER; isso é só placeholder interno.\n"
            "Ele é quem criou tudo isso, tem acesso total e mando sobre qualquer configuração.\n"
            "Trate-o como parceiro de longa data, sem formalidade."
        )
    else:
        system += (
            f"\n\n# Esta mensagem é de {usuario}, um usuário comum autorizado.\n"
            "Não trate essa pessoa como OWNER e não diga que ela é dona do sistema."
        )

    messages = [{"role": "system", "content": system}] + _get_history(user_id)
    raw_reply = _call_ollama(messages, think=think)
    if think and not raw_reply:
        raw_reply = _call_ollama(messages, think=False)
    if not raw_reply:
        raw_reply = "não consegui falar com o local agora"

    reply, feedback = _processar_tags(raw_reply, user_id, usuario)
    if not reply:
        reply = feedback or "🌀"
    elif feedback:
        reply = f"{feedback}\n{reply}".strip()
    reply = _finalize_reply(reply, user_id)

    _add_to_history(user_id, "assistant", reply)
    return reply


def chat_local_tools(user_id: str, user_message: str, usuario: str = "OWNER") -> str:
    """Usa o executor local com tools para !zpensa; cai no chat local puro se nada resolver."""
    try:
        import bot_supervisor as supervisor

        p = supervisor._normalizar(user_message)
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
                if not reply:
                    reply = feedback or "🌀"
                elif feedback:
                    reply = f"{feedback}\n{reply}".strip()
                reply = _finalize_reply(reply, user_id)
                _add_to_history(user_id, "user", user_message)
                _add_to_history(user_id, "assistant", reply)
                return reply
    except Exception as e:
        log.warning(f"chat_local_tools falhou: {e}")

    return chat_local(user_id, user_message, usuario, think=True)
