import discord
import asyncio
import os
import re
import json
import sys
import threading
import aiohttp as aiohttp_client
from datetime import datetime, timedelta, timezone
from aiohttp import web
from zoneinfo import ZoneInfo

_log_lock = threading.Lock()

BRT = timezone(timedelta(hours=-3))

# Força UTF-8 no stdout/stderr (Windows usa cp1252 por padrão — quebra emojis)
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).parent.parent))
try:
    from hyrule_env import DISCORD_TOKEN as TOKEN, OPENROUTER_KEYS, GROQ_KEYS
except ImportError:
    TOKEN = ""
    OPENROUTER_KEYS = []
    GROQ_KEYS = []

try:
    from hyrule_env import DISCORD_REMINDER_CHANNEL_ID as _REMINDER_CH_ID
except ImportError:
    _REMINDER_CH_ID = 0

OLLAMA_URL   = "http://localhost:11434/api/chat"
OLLAMA_MODEL = "qwen3:8b"
MODELOS_FALLBACK = [
    {"url": "https://openrouter.ai/api/v1/chat/completions",   "model": "google/gemma-4-31b-it:free",               "keys": OPENROUTER_KEYS},
    {"url": "https://api.groq.com/openai/v1/chat/completions", "model": "meta-llama/llama-4-scout-17b-16e-instruct","keys": GROQ_KEYS},
    {"url": "https://openrouter.ai/api/v1/chat/completions",   "model": "meta-llama/llama-3.3-70b-instruct:free",   "keys": OPENROUTER_KEYS},
    {"url": "https://openrouter.ai/api/v1/chat/completions",   "model": "nvidia/nemotron-3-super-120b-a12b:free",   "keys": OPENROUTER_KEYS},
]
_fallback_modelo_idx = 0
_fallback_key_idx    = 0

USUARIOS = {
    # Mapeie aqui os nomes amigaveis para IDs Discord (inteiros).
    # Exemplo: "OWNER": 123456789012345678
    # Para pegar seu ID: Discord → Configuracoes → Avancado → Modo desenvolvedor ON
    #                   depois clique com botao direito no usuario → Copiar ID
}

BASE_DIR      = os.path.dirname(os.path.abspath(__file__))
LOG_FILE      = os.path.join(BASE_DIR, "discord.log")
FILES_DIR     = os.path.join(BASE_DIR, "files")
HISTORY_DIR   = os.path.join(BASE_DIR, "history")
REMINDERS_FILE = os.path.join(BASE_DIR, "reminders.json")
RECEIVED_DIR  = os.path.join(BASE_DIR, "received")   # anexos recebidos do Discord, baixados imediatamente
RECEIVED_META = os.path.join(BASE_DIR, "received_files.json")   # metadados persistidos
USER_CTX_FILE = os.path.join(BASE_DIR, "user_context.json")     # contexto por usuário
PERSONA_FILE  = os.path.join(BASE_DIR, "..", "OPENCODE", "roaming", "LINK_PERSONA.md")
BANNER_FILE   = os.path.join(BASE_DIR, "..", "assets", "banner.jpg")
os.makedirs(FILES_DIR, exist_ok=True)
os.makedirs(HISTORY_DIR, exist_ok=True)
os.makedirs(RECEIVED_DIR, exist_ok=True)

buffer = []  # ultimas 100 mensagens em memoria

# Historico de conversa por usuario (para contexto)
historico_ia = {}

# ── Contexto persistente por usuário ─────────────────────────────────────────
# Estrutura: {autor: {last_file: {local_path, nome}, last_pedido: str, last_action: str}}
_user_ctx: dict[str, dict] = {}

LOCAL_TZ = ZoneInfo("America/Sao_Paulo")
_reminders_lock = asyncio.Lock()
_reminder_task: asyncio.Task | None = None

# Lembretes aguardando confirmação por reação: {msg_id: {text, channel_id, next_retry, retry_count}}
_pending_ack: dict[int, dict] = {}
_pending_ack_lock = asyncio.Lock()
REMINDER_RETRY_SECS = 15 * 60

_sys.path.insert(0, os.path.join(os.path.dirname(BASE_DIR), "link-bot"))
try:
    from bot.core.timeparse import (
        parse_time_expression,
        format_timestamp,
        humanize_recurrence,
        next_recurrence,
    )
    from bot.core.reminder_art import (
        plain_reminder_text,
        reminder_caption,
        render_reminder_card,
    )
except Exception:
    parse_time_expression = None
    format_timestamp = None
    humanize_recurrence = None
    next_recurrence = None
    plain_reminder_text = None
    reminder_caption = None
    render_reminder_card = None

try:
    from bot.skills import delirius_dl as delirius_dl
except Exception:
    delirius_dl = None


def _carregar_ctx():
    global _user_ctx
    if os.path.exists(USER_CTX_FILE):
        try:
            _user_ctx = json.load(open(USER_CTX_FILE, encoding="utf-8"))
        except Exception:
            _user_ctx = {}

def _salvar_ctx():
    try:
        json.dump(_user_ctx, open(USER_CTX_FILE, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    except Exception:
        pass

def _set_ctx(autor: str, **kwargs):
    if autor not in _user_ctx:
        _user_ctx[autor] = {}
    _user_ctx[autor].update(kwargs)
    _salvar_ctx()

def _get_ctx(autor: str) -> dict:
    return _user_ctx.get(autor, {})

_carregar_ctx()  # carrega ao iniciar


async def _safe_react(message, emoji: str):
    try:
        await message.add_reaction(emoji)
    except Exception as e:
        print(f"[REACT] falhou {emoji}: {e}", flush=True)


async def _discord_spot(message, autor: str, query: str):
    if delirius_dl is None:
        await message.channel.send("o módulo de música não carregou aqui")
        registrar("OUT", "Link", autor, "o módulo de música não carregou aqui")
        return

    query = (query or "").strip()
    if not query:
        await message.channel.send("manda o nome da música depois do !spot")
        await _safe_react(message, "⚠️")
        registrar("OUT", "Link", autor, "manda o nome da música depois do !spot")
        return

    await _safe_react(message, "⚔️")

    prefer_original = not delirius_dl._allows_alternate_version(query)
    spotify_url = ""
    fallback_query = query
    label = query

    url_match = delirius_dl._RE_SPOTIFY.search(query)
    if url_match:
        spotify_url = url_match.group(0)
    else:
        candidates = delirius_dl._spotify_search_candidates(query)
        result = None
        used_query = ""
        for candidate in candidates:
            result = delirius_dl._spotify_search(candidate, prefer_original=prefer_original)
            if result:
                used_query = candidate
                break
        spotify_url = (result or {}).get("url") or ""
        title = (result or {}).get("title") or (result or {}).get("name") or ""
        artist = (result or {}).get("artist") or (result or {}).get("artists") or ""
        if isinstance(artist, list):
            artist = ", ".join(str(a) for a in artist)
        fallback_query = " ".join(str(x) for x in (title, artist) if x).strip() or used_query or query
        label = f"{title} — {artist}".strip(" —") if title else query
        if used_query:
            print(f"[DISCORD !spot] '{query}' -> '{used_query}' => {label}", flush=True)

    async def _send_audio_from_media(media_url: str, source_text: str) -> bool:
        path = await delirius_dl._baixar(media_url, "mp3")
        if not path:
            return False
        try:
            filename = "spot.mp3"
            await message.channel.send(content=source_text, file=discord.File(path, filename=filename))
            await _safe_react(message, "✅")
            registrar("OUT", "Link", autor, f"[ARQUIVO: {filename}] {source_text}")
            return True
        finally:
            delirius_dl._rm(path)

    if spotify_url:
        data = delirius_dl._get_json("/download/spotifydl", {"url": spotify_url}, timeout=90, attempts=2)
        media_url = delirius_dl._extract_url(data) if isinstance(data, dict) else None
        if media_url:
            title = delirius_dl._extract_title(data) or label
            artist = delirius_dl._extract_artist(data)
            header = f"{title} — {artist}".strip(" —")
            if await _send_audio_from_media(media_url, f"{header}\nSpotify: {spotify_url}"):
                return

    yt = delirius_dl._youtube_search(fallback_query, prefer_original=prefer_original)
    yt_url = (yt or {}).get("url")
    if yt_url:
        data = (
            delirius_dl._get_json("/download/ytmp3", {"url": yt_url}, timeout=45, attempts=2)
            or delirius_dl._get_json("/download/ytmp3v2", {"url": yt_url}, timeout=45, attempts=2)
        )
        media_url = delirius_dl._extract_url(data) if data else None
        if media_url:
            title = delirius_dl._extract_title(data) or (yt or {}).get("title") or fallback_query
            if await _send_audio_from_media(media_url, f"{title}\nYouTube: {yt_url}"):
                return

    await message.channel.send("não consegui baixar essa música agora")
    await _safe_react(message, "⚠️")
    registrar("OUT", "Link", autor, "não consegui baixar essa música agora")


# ── Lembretes Discord ────────────────────────────────────────────────────────
def _carregar_lembretes() -> dict:
    if os.path.exists(REMINDERS_FILE):
        try:
            with open(REMINDERS_FILE, encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                data.setdefault("next_id", 1)
                data.setdefault("items", [])
                return data
        except Exception:
            pass
    return {"next_id": 1, "items": []}


def _salvar_lembretes(data: dict):
    tmp = f"{REMINDERS_FILE}.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, REMINDERS_FILE)


def _limpar_texto_lembrete(args: str) -> str:
    text = args or ""
    patterns = [
        r"daqui\s+\d+\s*(?:minutos?|min|m|horas?|h|dias?|d)\b",
        r"em\s+\d+\s*(?:minutos?|min|m|horas?|h)\b",
        r"todo\s+dia",
        r"todos\s+os\s+dias",
        r"diariamente",
        r"toda\s+(?:segunda|terca|terça|quarta|quinta|sexta|sabado|sábado|domingo)",
        r"amanha",
        r"amanhã",
        r"hoje",
        r"\d{1,2}[h:]\d{2}",
        r"\d{1,2}\s*h(?:oras?)?",
        r"as?\s+\d{1,2}",
        r"^de\s+",
        r"^que\s+",
    ]
    for pat in patterns:
        text = re.sub(pat, "", text, flags=re.IGNORECASE)
    text = re.sub(r"\s+", " ", text).strip(" ,.")
    return text or "(sem descrição)"


async def _adicionar_lembrete_discord(user: discord.User, args: str) -> str:
    if parse_time_expression is None:
        return "não consegui carregar o parser de tempo agora"
    if not args.strip():
        return "marca como? exemplo: `me lembra daqui 30 minutos de beber agua`"

    parsed = parse_time_expression(args)
    if parsed is None:
        return "não entendi quando. tenta `daqui 30 minutos`, `amanhã às 8` ou `todo dia 22h`"

    trigger_at, recurrence = parsed
    text = _limpar_texto_lembrete(args)

    async with _reminders_lock:
        data = _carregar_lembretes()
        rid = int(data.get("next_id", 1))
        data["next_id"] = rid + 1
        data["items"].append({
            "id": rid,
            "user_id": int(user.id),
            "username": user.name,
            "text": text,
            "trigger_at": int(trigger_at),
            "recurrence": recurrence or "",
            "sent": False,
            "created_at": int(datetime.now(LOCAL_TZ).timestamp()),
        })
        _salvar_lembretes(data)

    quando = format_timestamp(trigger_at) if format_timestamp else str(trigger_at)
    extra = ""
    if recurrence and humanize_recurrence:
        extra = f"\nrecorrente: {humanize_recurrence(recurrence)}"
    return f"marcado: {quando}\n{text}\n#{rid}{extra}"


async def _listar_lembretes_discord(user: discord.User) -> str:
    async with _reminders_lock:
        data = _carregar_lembretes()
        items = [
            r for r in data.get("items", [])
            if int(r.get("user_id", 0)) == int(user.id) and not r.get("sent")
        ]
    if not items:
        return "nenhum lembrete marcado"

    linhas = ["teus lembretes:"]
    for r in sorted(items, key=lambda x: int(x.get("trigger_at", 0)))[:20]:
        trigger_at = int(r.get("trigger_at", 0))
        quando = format_timestamp(trigger_at) if format_timestamp else str(trigger_at)
        rec = ""
        if r.get("recurrence") and humanize_recurrence:
            rec = f" - {humanize_recurrence(r['recurrence'])}"
        linhas.append(f"#{r['id']} - {quando}{rec}: {r['text']}")
    return "\n".join(linhas)


async def _cancelar_lembrete_discord(user: discord.User, text: str) -> str:
    m = re.search(r"\d+", text or "")
    if not m:
        return "qual número? exemplo: `cancela lembrete 3`"
    rid = int(m.group(0))
    async with _reminders_lock:
        data = _carregar_lembretes()
        before = len(data.get("items", []))
        data["items"] = [
            r for r in data.get("items", [])
            if not (int(r.get("id", 0)) == rid and int(r.get("user_id", 0)) == int(user.id))
        ]
        removed = before - len(data["items"])
        if removed:
            _salvar_lembretes(data)
    if removed:
        return f"lembrete #{rid} cancelado"
    return f"não achei o lembrete #{rid}"


async def _tratar_lembrete_discord(message: discord.Message, texto_norm: str) -> bool:
    texto = (message.content or "").strip()
    if re.search(r"\b(?:meus lembretes|lista lembretes|lembretes ativos|ver lembretes)\b", texto_norm):
        resposta = await _listar_lembretes_discord(message.author)
    elif re.search(r"\b(?:cancela|cancelar|apaga|apagar|remove|remover)\s+lembrete\b", texto_norm):
        resposta = await _cancelar_lembrete_discord(message.author, texto)
    elif re.match(r"^!?\s*(?:me lembra|lembra de|lembrar|agenda|agendar)\b", texto_norm):
        if re.search(r"\blembra de mim\b|\bse lembra de mim\b", texto_norm):
            return False
        args = re.sub(r"^!?\s*(?:me lembra|lembra de|lembrar|agenda|agendar)\s*", "", texto, flags=re.IGNORECASE).strip()
        resposta = await _adicionar_lembrete_discord(message.author, args)
    else:
        return False

    await message.channel.send(resposta)
    registrar("OUT", "Link", message.author.name, resposta)
    return True


async def _enviar_reminder_discord(r: dict, msg_text: str, retry_count: int = 0) -> int | None:
    """Envia lembrete no canal configurado ou DM. Retorna message ID ou None."""
    reminder_ch = int(_REMINDER_CH_ID) if _REMINDER_CH_ID else 0
    image_path = None
    sent_msg = None
    try:
        if render_reminder_card and reminder_caption and retry_count == 0:
            image_path = render_reminder_card(r)
            content = reminder_caption(r)
        else:
            content = msg_text
            image_path = None

        if reminder_ch:
            channel = client.get_channel(reminder_ch) or await client.fetch_channel(reminder_ch)
            if image_path:
                sent_msg = await channel.send(content=content, file=discord.File(image_path))
            else:
                sent_msg = await channel.send(content)
            registrar("OUT", "Link", f"#canal:{reminder_ch}", content)
        else:
            user = await client.fetch_user(int(r["user_id"]))
            if image_path:
                sent_msg = await user.send(content=content, file=discord.File(image_path))
            else:
                sent_msg = await user.send(content)
            registrar("OUT", "Link", user.name, content)
    except Exception as e:
        print(f"[LEMBRETE] falha enviando #{r.get('id')}: {e}", flush=True)
    finally:
        if image_path:
            try:
                os.remove(image_path)
            except Exception:
                pass
    return sent_msg.id if sent_msg else None


async def _loop_lembretes_discord():
    await client.wait_until_ready()
    while not client.is_closed():
        now_ts = int(datetime.now(LOCAL_TZ).timestamp())

        # ── Lembretes novos ──
        due = []
        async with _reminders_lock:
            data = _carregar_lembretes()
            changed = False
            for r in data.get("items", []):
                if not r.get("sent") and int(r.get("trigger_at", 0)) <= now_ts:
                    due.append(dict(r))
                    recurrence = r.get("recurrence") or ""
                    if recurrence and next_recurrence:
                        nxt = next_recurrence(recurrence)
                        if nxt:
                            r["trigger_at"] = int(nxt)
                        else:
                            r["sent"] = True
                    else:
                        r["sent"] = True
                    changed = True
            if changed:
                _salvar_lembretes(data)

        for r in due:
            base_text = plain_reminder_text(r) if plain_reminder_text else f"lembrete #{r['id']}: {r['text']}"
            msg_id = await _enviar_reminder_discord(r, base_text)
            if msg_id:
                async with _pending_ack_lock:
                    _pending_ack[msg_id] = {
                        'r': r,
                        'text': base_text,
                        'next_retry': now_ts + REMINDER_RETRY_SECS,
                        'retry_count': 0,
                    }

        # ── Retentativas de lembretes sem confirmação ──
        async with _pending_ack_lock:
            to_retry = [
                (mid, info) for mid, info in list(_pending_ack.items())
                if info['next_retry'] <= now_ts
            ]

        for mid, info in to_retry:
            async with _pending_ack_lock:
                _pending_ack.pop(mid, None)
            rc = info['retry_count'] + 1
            retry_text = f"⏰ (sem confirmação — tentativa {rc})\n{info['text']}"
            new_id = await _enviar_reminder_discord(info['r'], retry_text, retry_count=rc)
            if new_id:
                async with _pending_ack_lock:
                    _pending_ack[new_id] = {**info, 'next_retry': now_ts + REMINDER_RETRY_SECS, 'retry_count': rc}

        await asyncio.sleep(15)


# ── Metadados de arquivos recebidos ──────────────────────────────────────────
def _registrar_recebido(autor: str, nome: str, url: str):
    """Salva metadado (URL) do arquivo recebido — download só acontece quando pedido."""
    dados = {}
    if os.path.exists(RECEIVED_META):
        try:
            dados = json.load(open(RECEIVED_META, encoding="utf-8"))
        except Exception:
            pass
    if autor not in dados:
        dados[autor] = []
    dados[autor].append({
        "nome": nome,
        "url":  url,
        "ts":   datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    })
    dados[autor] = dados[autor][-50:]  # mantém últimos 50 por usuário
    json.dump(dados, open(RECEIVED_META, "w", encoding="utf-8"), ensure_ascii=False, indent=2)

def _ultimo_arquivo_recebido(autor: str) -> dict | None:
    """Retorna metadado do último arquivo recebido (JSON persistido — sobrevive restart)."""
    if os.path.exists(RECEIVED_META):
        try:
            dados = json.load(open(RECEIVED_META, encoding="utf-8"))
            arquivos = dados.get(autor, [])
            if arquivos:
                return arquivos[-1]  # {"nome", "url", "ts"}
        except Exception:
            pass
    return None


def _history_file(autor: str) -> str:
    safe = autor.replace("/", "_").replace("\\", "_")
    return os.path.join(HISTORY_DIR, f"{safe}.json")


def carregar_historico(autor: str) -> list:
    path = _history_file(autor)
    if os.path.exists(path):
        try:
            with open(path, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return []


def salvar_historico(autor: str, historico: list):
    path = _history_file(autor)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(historico, f, ensure_ascii=False, indent=2)

# Cache de usuarios que enviaram mensagens (nome -> objeto user)
usuarios_cache = {}

# Arquivo de IDs persistidos
USERS_FILE = os.path.join(BASE_DIR, "usuarios_extra.json")


def salvar_usuario(nome: str, user_id: int):
    dados = {}
    if os.path.exists(USERS_FILE):
        with open(USERS_FILE, encoding="utf-8") as f:
            dados = json.load(f)
    dados[nome.lower()] = user_id
    with open(USERS_FILE, "w", encoding="utf-8") as f:
        json.dump(dados, f, indent=2)


def carregar_usuarios_extra() -> dict:
    if not os.path.exists(USERS_FILE):
        return {}
    with open(USERS_FILE, encoding="utf-8") as f:
        return json.load(f)


from pathlib import Path as _Path
_NAV_STATE_FILE = _Path(BASE_DIR) / ".." / "nav_state.json"

def _carregar_nav_state(autor: str) -> str:
    """Retorna string com pasta atual + conteúdo real para injetar no prompt."""
    try:
        data = json.loads(_NAV_STATE_FILE.read_text(encoding="utf-8"))
        entrada = data.get(autor, None)
        if not entrada:
            return ""
        # Suporte ao formato antigo (string) e novo (dict)
        if isinstance(entrada, str):
            pasta = entrada
            itens: list[str] = []
        else:
            pasta = entrada.get("pasta", "")
            itens = entrada.get("itens", [])
        if not pasta:
            return ""
        bloco = f"\n\n---\n[CONTEXTO DE NAVEGACAO NO PC]\nPasta atual: {pasta}\n"
        if itens:
            bloco += "Conteudo (nomes exatos como aparecem no PC):\n"
            bloco += "\n".join(f"  - {nome}" for nome in itens)
            bloco += "\n"
        bloco += (
            "REGRA CRITICA: Se o usuario mencionar qualquer nome que aparece na lista acima, "
            "use o nome EXATAMENTE como esta listado, sem traduzir, corrigir ortografia ou interpretar. "
            "Trate como pedido de navegacao/envio de arquivo e use [SHEIKAH_SLATE: <acao> <nome_exato>]."
        )
        return bloco
    except Exception:
        pass
    return ""


def carregar_persona(ultima_resposta: str = "", autor: str = "") -> str:
    base = "Voce e Link. Responda em portugues do Brasil de forma natural e descontraida."
    try:
        with open(PERSONA_FILE, encoding="utf-8") as f:
            base = f.read()
    except Exception:
        pass
    if ultima_resposta:
        base += f"\n\n---\nSua ultima resposta foi: \"{ultima_resposta}\"\nNAO comece esta resposta da mesma forma."
    if autor:
        base += _carregar_nav_state(autor)
    return base


def carregar_persona_local() -> str:
    return (
        "Voce e Link, parceiro do OWNER. Responda em portugues do Brasil, curto, "
        "casual e direto. Nao diga que e IA, bot ou sistema. Pense internamente "
        "se precisar, mas entregue apenas a resposta final."
    )


def _nome_display(username: str) -> str:
    """Retorna o nome amigavel do usuario (ex: OWNER, USER2) ou o username Discord."""
    # Busca pelo cache inverso: username Discord -> nome amigavel
    for nome_key, uid in USUARIOS.items():
        cached = usuarios_cache.get(nome_key.lower())
        if cached and cached.name.lower() == username.lower():
            return nome_key
    # Busca nos extras
    extras = carregar_usuarios_extra()
    for nome_extra, uid in extras.items():
        cached = usuarios_cache.get(nome_extra)
        if cached and cached.name.lower() == username.lower():
            return nome_extra.capitalize()
    return username


def _is_discord_owner(user: discord.User) -> bool:
    if not user:
        return False
    uid = int(user.id)
    if uid in {int(v) for v in USUARIOS.values() if str(v).isdigit()}:
        return True
    extras = carregar_usuarios_extra()
    owner_ids = {
        int(v) for k, v in extras.items()
        if str(v).isdigit() and k.lower() in {"owner", "josh", "josh_barbosa"}
    }
    return uid in owner_ids


def _menu_texto(secao: str = "principal", owner: bool = False) -> str:
    if secao == "lembretes":
        return (
            "**⏰ Lembretes**\n"
            "`me lembra daqui 30min de X`\n"
            "`me lembra todo dia 22h de X`\n"
            "`meus lembretes`\n"
            "`cancela lembrete 3`"
        )
    if secao == "midia":
        return (
            "**🎨 Mídia**\n"
            "`busca na web uma foto de X e me manda`\n"
            "`guarda no baú` com mídia\n"
            "`meu baú`\n"
            "`envia este arquivo para mim`"
        )
    if secao == "memoria":
        return (
            "**📜 Memória**\n"
            "`adiciona <missão> na lista`\n"
            "`minhas tarefas`\n"
            "`feito 2`\n"
            "`anota: <texto>`\n"
            "`minhas anotações`"
        )
    if secao == "hyrule":
        return (
            "**🌿 Hyrule**\n"
            "`achei um korok!`\n"
            "`quantos koroks`\n"
            "`frase épica`\n"
            "`citação aleatória`"
        )
    if secao == "admin":
        return (
            "**🔱 Admin**\n"
            "`triforce <pedido>`\n"
            "`majora <pedido>`\n"
            "`mastersword <pedido>`\n"
            "`!link acorda`\n"
            "`!Z <pedido local rápido>`\n"
            "`!zpensa <pedido local com tools>`"
        )
    texto = (
        "**⚔️ Link — Menu de Hyrule**\n"
        "Escolhe uma área pelos botões abaixo.\n\n"
        "**Disponível:** Lembretes, Mídia, Memória e Hyrule."
    )
    if owner:
        texto += "\n**Dono:** Admin."
    return texto


class MenuView(discord.ui.View):
    def __init__(self, owner: bool):
        super().__init__(timeout=180)
        self.owner = owner
        self.add_item(MenuSectionButton("Lembretes", "⏰", "lembretes"))
        self.add_item(MenuSectionButton("Mídia", "🎨", "midia"))
        self.add_item(MenuSectionButton("Memória", "📜", "memoria"))
        self.add_item(MenuSectionButton("Hyrule", "🌿", "hyrule"))
        if owner:
            self.add_item(AdminMenuButton())


class MenuSectionButton(discord.ui.Button):
    def __init__(self, label: str, emoji: str, secao: str):
        super().__init__(label=label, emoji=emoji, style=discord.ButtonStyle.secondary)
        self.secao = secao

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.send_message(_menu_texto(self.secao), view=MenuView(False))


class AdminMenuButton(discord.ui.Button):
    def __init__(self):
        super().__init__(label="Admin", emoji="🔱", style=discord.ButtonStyle.danger)

    async def callback(self, interaction: discord.Interaction):
        if not _is_discord_owner(interaction.user):
            await interaction.response.send_message("🔒 Esse menu é só do dono.")
            return
        await interaction.response.send_message(_menu_texto("admin", owner=True))


async def enviar_menu_discord(message: discord.Message, secao: str = "principal"):
    owner = _is_discord_owner(message.author)
    if secao == "admin" and not owner:
        resposta = "🔒 Esse menu é só do dono."
        await message.channel.send(resposta)
        registrar("OUT", "Link", message.author.name, resposta)
        return

    texto = _menu_texto(secao, owner=owner)
    kwargs = {"content": texto}
    if secao == "principal":
        kwargs["view"] = MenuView(owner)
        if os.path.exists(BANNER_FILE):
            kwargs["file"] = discord.File(BANNER_FILE, filename="hyrule-menu.jpg")
    await message.channel.send(**kwargs)
    registrar("OUT", "Link", message.author.name, f"[MENU:{secao}]")


async def responder_com_ia(autor: str, mensagem: str) -> str:
    """Cloud primeiro (melhor persona), qwen local como último recurso."""
    global _fallback_modelo_idx, _fallback_key_idx

    if autor not in historico_ia:
        historico_ia[autor] = carregar_historico(autor)

    nome_display = _nome_display(autor)
    historico_ia[autor].append({"role": "user", "content": f"[Mensagem de {nome_display}]: {mensagem}"})
    if len(historico_ia[autor]) > 20:
        historico_ia[autor] = historico_ia[autor][-20:]

    ultima_resposta = ""
    for entry in reversed(historico_ia[autor]):
        if entry["role"] == "assistant":
            ultima_resposta = entry["content"][:120]
            break

    system = carregar_persona(ultima_resposta, autor)
    msgs   = [{"role": "system", "content": system}, *historico_ia[autor]]

    # ── 1. Cloud (gemma/llama/groq) — melhor para persona ────────────────────
    tentados = 0
    tentativas_total = sum(len(m["keys"]) for m in MODELOS_FALLBACK)
    while tentados < tentativas_total:
        modelo = MODELOS_FALLBACK[_fallback_modelo_idx % len(MODELOS_FALLBACK)]
        chave  = modelo["keys"][_fallback_key_idx % len(modelo["keys"])]
        try:
            async with aiohttp_client.ClientSession() as session:
                is_groq = "groq.com" in modelo["url"]
                headers = {"Authorization": f"Bearer {chave}", "Content-Type": "application/json"}
                if is_groq:
                    headers.update({"User-Agent": "Mozilla/5.0", "Accept": "application/json",
                                    "Origin": "https://console.groq.com", "Referer": "https://console.groq.com/"})
                async with session.post(
                    modelo["url"], headers=headers,
                    json={"model": modelo["model"], "messages": msgs,
                          "max_tokens": 256, "temperature": 0.85,
                          **({"reasoning": {"enabled": True, "effort": "low", "exclude": True}}
                             if not is_groq else {})},
                    timeout=aiohttp_client.ClientTimeout(total=12)
                ) as resp:
                    if resp.status in (401, 403):
                        _fallback_modelo_idx += 1; _fallback_key_idx = 0
                        tentados += len(modelo["keys"]); continue
                    if resp.status in (429, 503, 529):
                        _fallback_key_idx += 1
                        if _fallback_key_idx % len(modelo["keys"]) == 0:
                            _fallback_modelo_idx += 1
                        tentados += 1; continue
                    data = await resp.json()
                    resposta = data["choices"][0]["message"]["content"].strip()
                    primeira = resposta.split('\n')[0].lower().lstrip('*- ')
                    if any(primeira.startswith(rs) for rs in _REASON_STARTS):
                        print(f"[IA] {modelo['model']} CoT vazou, pulando...", flush=True)
                        _fallback_modelo_idx += 1; _fallback_key_idx = 0
                        tentados += len(modelo["keys"]); continue
                    print(f"[IA] fallback {modelo['model']}: {resposta[:60]}", flush=True)
                    historico_ia[autor].append({"role": "assistant", "content": resposta})
                    salvar_historico(autor, historico_ia[autor])
                    return resposta
        except Exception as e:
            print(f"[IA] fallback {modelo['model']} erro: {e}", flush=True)
            _fallback_key_idx += 1
            if _fallback_key_idx % len(modelo["keys"]) == 0:
                _fallback_modelo_idx += 1
            tentados += 1

    # ── 2. Último recurso: qwen local ────────────────────────────────────────
    # Usa persona compacta + últimas 4 msgs para caber dentro do timeout
    msgs_local = [
        {"role": "system", "content": carregar_persona_local()},
        *historico_ia[autor][-4:],
    ]
    try:
        async with aiohttp_client.ClientSession() as session:
            async with session.post(
                OLLAMA_URL,
                json={"model": OLLAMA_MODEL, "stream": False,
                      "think": False,
                      "options": {"temperature": 0.85, "top_p": 0.9,
                                  "repeat_penalty": 1.1, "num_predict": 80},
                      "messages": msgs_local},
                timeout=aiohttp_client.ClientTimeout(total=90)
            ) as resp:
                data = await resp.json()
                resposta = data.get("message", {}).get("content", "").strip()
                resposta = re.sub(r'<think>.*?</think>', '', resposta, flags=re.DOTALL | re.IGNORECASE).strip()
                if resposta:
                    print(f"[IA] qwen local (fallback final): {resposta[:60]}", flush=True)
                    historico_ia[autor].append({"role": "assistant", "content": resposta})
                    salvar_historico(autor, historico_ia[autor])
                    return resposta
    except Exception as e:
        print(f"[IA] qwen local também falhou: {e}", flush=True)

    return "..."


async def responder_com_ia_local(autor: str, mensagem: str, think: bool = False) -> str:
    """Força conversa direta com o Ollama local, sem OpenRouter/Groq."""
    if autor not in historico_ia:
        historico_ia[autor] = carregar_historico(autor)

    nome_display = _nome_display(autor)
    historico_ia[autor].append({"role": "user", "content": f"[Mensagem de {nome_display}]: {mensagem}"})
    if len(historico_ia[autor]) > 20:
        historico_ia[autor] = historico_ia[autor][-20:]

    ultima_resposta = ""
    for entry in reversed(historico_ia[autor]):
        if entry["role"] == "assistant":
            ultima_resposta = entry["content"][:120]
            break

    system = carregar_persona_local()
    system += (
        "\n\n# Modo local\n"
        "Voce esta respondendo pelo modelo local do OWNER. Pense internamente se precisar, "
        "mas entregue so a resposta final, curta e natural."
    )
    msgs = [{"role": "system", "content": system}, *historico_ia[autor]]

    try:
        async with aiohttp_client.ClientSession() as session:
            async with session.post(
                OLLAMA_URL,
                json={"model": OLLAMA_MODEL, "stream": False,
                      "think": think,
                      "options": {"temperature": 0.8, "top_p": 0.9,
                                  "repeat_penalty": 1.1, "num_predict": 120},
                      "messages": msgs},
                timeout=aiohttp_client.ClientTimeout(total=90)
            ) as resp:
                data = await resp.json()
                resposta = data.get("message", {}).get("content", "").strip()
                resposta = re.sub(r'<think>.*?</think>', '', resposta, flags=re.DOTALL | re.IGNORECASE).strip()
                if resposta:
                    historico_ia[autor].append({"role": "assistant", "content": resposta})
                    salvar_historico(autor, historico_ia[autor])
                    return resposta
    except Exception as e:
        print(f"[IA] qwen local !Z falhou: {e}", flush=True)

    if think:
        return await responder_com_ia_local(autor, mensagem, think=False)

    return "não consegui falar com o local agora"


async def responder_com_ia_local_tools(autor: str, mensagem: str) -> str:
    """Usa o executor local com tools para o !zpensa; cai no chat local se nada resolver."""
    loop = asyncio.get_running_loop()

    def _run_tools():
        import bot_supervisor as supervisor

        p = supervisor._normalizar(mensagem)
        quer_web = any(x in p for x in ["busca", "pesquis", "internet", "google", "procur", "duckduck", "web"])
        quer_img = any(x in p for x in ["imagem", "foto", "png", "jpg", "jpeg", "figura", "ilustracao", "artwork", "arte"])
        acao_img = any(x in p for x in ["busca", "pesquis", "procur", "acha", "encontra", "pega", "manda", "envia", "baixa", "download", "web", "internet"])
        quer_arquivo_url = "http" in p and any(x in p for x in ["manda", "envia", "enviar", "baixa", "baixar", "download", "anexo", "arquivo"])
        if quer_arquivo_url:
            enviado = supervisor.baixar_url_e_enviar(mensagem, autor)
            if enviado:
                return enviado

        if quer_img and acao_img:
            return supervisor.baixar_imagem_e_enviar(mensagem, autor)

        if quer_web and not quer_img:
            return supervisor.buscar_internet(mensagem)

        direto = supervisor.executar_pedido(mensagem, autor)
        if direto:
            return direto

        if supervisor.ollama_disponivel():
            return supervisor.executar_qwen_react(
                mensagem, autor, usar_todas_tools=False, max_rodadas=3
            )
        return None

    try:
        resposta = await loop.run_in_executor(None, _run_tools)
        if resposta:
            if autor not in historico_ia:
                historico_ia[autor] = carregar_historico(autor)
            historico_ia[autor].append({"role": "user", "content": f"[Mensagem de {_nome_display(autor)}]: {mensagem}"})
            historico_ia[autor].append({"role": "assistant", "content": resposta})
            historico_ia[autor] = historico_ia[autor][-20:]
            salvar_historico(autor, historico_ia[autor])
            return resposta
    except Exception as e:
        print(f"[IA] qwen local tools !zpensa falhou: {e}", flush=True)

    return await responder_com_ia_local(autor, mensagem, think=True)

intents = discord.Intents.default()
intents.message_content = True
intents.dm_messages = True
intents.guild_messages = True
intents.reactions = True

client = discord.Client(intents=intents)


_TAG_RE      = re.compile(r'\[SHEIKAH_SLATE[^\]]*\]', re.IGNORECASE)
_TRIFORCE_RE = re.compile(r'\[TRIFORCE:\s*(.*?)\]', re.IGNORECASE | re.DOTALL)
_MAJORA_RE   = re.compile(r'\[MAJORA:\s*(.*?)\]', re.IGNORECASE | re.DOTALL)
_MASTERSWORD_RE = re.compile(r'\[MASTERSWORD:\s*(.*?)\]', re.IGNORECASE | re.DOTALL)
_THINK_RE = re.compile(r'<think>.*?</think>', re.DOTALL | re.IGNORECASE)

# Prefixos que indicam raciocínio interno vazado (modelos de reasoning)

def _pedido_sheikah_executavel(pedido: str) -> bool:
    """Evita executar placeholders ou respostas conversacionais como tarefa do PC."""
    p = (pedido or "").strip()
    if not p:
        return False
    p_norm = p.lower()
    if any(x in p_norm for x in ["{url}", "{nome}", "{filename}", "{caminho}", "{usuario}"]):
        return False
    if re.search(r"\{[^{}]+\}", p):
        return False
    noops = [
        "aguarda", "aguarde", "espera", "espere", "não mande", "nao mande",
        "deixa pra la", "deixa pra lá", "sem ação", "sem acao",
        "instruções sobre o arquivo", "instrucoes sobre o arquivo",
    ]
    if any(x in p_norm for x in noops):
        return False
    acoes = [
        "salva", "salvar", "guardar", "baixar", "baixa", "download",
        "enviar", "envia", "manda", "apagar", "apaga", "deletar", "deleta",
        "ler", "le ", "listar", "lista", "abrir", "abre", "fechar", "fecha",
        "executar", "executa", "rodar", "roda", "escrever", "escreve",
        "mover", "move", "copiar", "copia",
    ]
    return any(a in p_norm for a in acoes)
_REASON_STARTS = (
    "okay,", "ok,", "ok!", "let me", "first,", "first,", "looking at",
    "i need to", "wait,", "alright,", "so,", "now,", "hmm", "well,",
    "let's", "let me unpack", "i must", "i should", "in this case",
    "owner is asking", "the user", "from the", "according to",
    "important:", "note:", "task description", "so i should",
)

def sanitizar(texto: str) -> str:
    """Remove tags internas, think blocks e chain-of-thought vazado."""
    limpo = _THINK_RE.sub('', texto)        # <think>...</think>
    limpo = _TAG_RE.sub('', limpo)          # [SHEIKAH_SLATE: ...]
    limpo = _TRIFORCE_RE.sub('', limpo)     # [TRIFORCE: ...]
    limpo = _MAJORA_RE.sub('', limpo)       # [MAJORA: ...]
    limpo = _MASTERSWORD_RE.sub('', limpo)  # [MASTERSWORD: ...]

    # Se o texto começa com raciocínio, tenta extrair só a resposta real
    primeira = limpo.strip().split('\n')[0].lower().lstrip('*- ')
    if any(primeira.startswith(rs) for rs in _REASON_STARTS):
        # Tenta separar por parágrafo duplo (\n\n)
        paragrafos = [p.strip() for p in limpo.strip().split('\n\n') if p.strip()]
        # Pega o último parágrafo que NÃO começa com CoT e é curto (< 400 chars)
        candidato = None
        for p in reversed(paragrafos):
            p_lower = p.lower().lstrip('*- ')
            if not any(p_lower.startswith(rs) for rs in _REASON_STARTS) and len(p) < 400:
                candidato = p
                break
        if candidato:
            limpo = candidato
        elif paragrafos:
            # Se todos começam com CoT, pega o último que seja curto
            curtos = [p for p in paragrafos if len(p) < 400]
            limpo = curtos[-1] if curtos else paragrafos[-1]

    linhas = [l for l in limpo.splitlines() if l.strip()]
    return '\n'.join(linhas).strip()


def registrar(direcao: str, de: str, para: str, msg: str, anexos: list = None):
    hora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    entry = {
        "time": hora,
        "direction": direcao,
        "from": de,
        "to": para,
        "msg": msg,
        "anexos": anexos or []
    }
    buffer.append(entry)
    if len(buffer) > 100:
        buffer.pop(0)

    linha = f"[{hora}] [{direcao}] {de} -> {para}: {msg}"
    if anexos:
        nomes = ", ".join(a["nome"] for a in anexos)
        linha += f" [ANEXO: {nomes}]"
    linha += "\n"

    with _log_lock:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(linha)
        print(linha, end="", flush=True)


def resolver_usuario(nome: str):
    """Resolve nome para chave do USUARIOS dict ou retorna None."""
    return next((k for k in USUARIOS if k.lower() == nome.lower()), None)


async def buscar_user(nome: str):
    """Busca user object: primeiro em USUARIOS, depois no cache, depois no arquivo persistido."""
    nome_key = resolver_usuario(nome)
    if nome_key:
        return await client.fetch_user(USUARIOS[nome_key])
    cached = usuarios_cache.get(nome.lower())
    if cached:
        return cached
    # Tenta carregar do arquivo persistido
    extras = carregar_usuarios_extra()
    uid = extras.get(nome.lower())
    if uid:
        try:
            user = await client.fetch_user(uid)
            usuarios_cache[nome.lower()] = user
            return user
        except Exception:
            pass
    return None


@client.event
async def on_raw_reaction_add(payload: discord.RawReactionActionEvent):
    """Qualquer reação numa mensagem de lembrete pendente confirma e cancela retry."""
    if payload.user_id == client.user.id:
        return
    async with _pending_ack_lock:
        if payload.message_id in _pending_ack:
            info = _pending_ack.pop(payload.message_id)
            print(f"[LEMBRETE] confirmado por reação após {info['retry_count']} retentativas", flush=True)


@client.event
async def on_ready():
    global _reminder_task
    print(f"\n  Link Discord Online")
    print(f"  Bot: {client.user}")
    print(f"  HTTP: http://localhost:7331")
    print(f"  Log:  {LOG_FILE}")
    print(f"  Files: {FILES_DIR}")
    print(f"  Escutando DMs...\n")
    # Pre-carrega usuarios extras persistidos no cache
    extras = carregar_usuarios_extra()
    for nome, uid in extras.items():
        try:
            user = await client.fetch_user(uid)
            usuarios_cache[nome] = user
            print(f"  [cache] {nome} -> {user.name} ({uid})")
        except Exception:
            pass
    if _reminder_task is None or _reminder_task.done():
        _reminder_task = asyncio.create_task(_loop_lembretes_discord())


@client.event
async def on_message(message):
    if message.author == client.user:
        return

    is_dm = isinstance(message.channel, discord.DMChannel)
    is_guild = message.guild is not None

    if not is_dm and not is_guild:
        return

    # Servidor/grupo: só responde a !comando ou @menção direta
    if is_guild:
        mentioned = client.user in message.mentions
        is_cmd = (message.content or "").strip().startswith("!")
        if not mentioned and not is_cmd:
            return

    autor   = message.author.name
    p_lower = (message.content or "").lower()

    # ── FASE 1: Captura passiva — só metadados, sem download ─────────────────
    # Download só acontece quando o usuário pedir explicitamente ("salva no desktop")
    # Isso evita desperdício de disco e mantém o controle com o usuário
    anexos_meta = []
    for att in message.attachments:
        meta = {
            "nome": att.filename,
            "url":  att.url,
            "tamanho_mb": round(att.size / 1024 / 1024, 2),
            "ts":   datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }
        anexos_meta.append(meta)
        _registrar_recebido(autor, att.filename, att.url)  # persiste só URL
        print(f"[RECEBIDO] {autor}: {att.filename} (metadado salvo)", flush=True)

    registrar("IN", autor, "Link", message.content,
              [{"nome": a["nome"], "url": a["url"]} for a in anexos_meta])
    usuarios_cache[autor.lower()] = message.author
    salvar_usuario(autor, message.author.id)

    # ── Comandos especiais (sem LLM) ─────────────────────────────────────────
    import unicodedata as _ud
    def _norm(t): return ''.join(c for c in _ud.normalize('NFD', t.lower()) if _ud.category(c) != 'Mn')
    _p_norm = _norm(message.content or "")

    if re.search(r'!link\s+acord', _p_norm):
        await message.channel.send("acordando tudo... um segundo")
        registrar("OUT", "Link", autor, "acordando tudo... um segundo")
        registrar("SYS", "Bot", "Claude", "[SHEIKAH_SLATE-PEDIDO] acorde sistema completo")
        return

    # ── TRIFORCE: escalação direta, sem passar pelo LLM ──────────────────────
    _txt = (message.content or "").strip()
    _txt_norm = _p_norm.strip()

    if _txt_norm in {"menu", "ajuda", "help", "comandos", "?"}:
        await enviar_menu_discord(message)
        return

    if _txt_norm in {"menu admin", "menu adm", "ajuda admin", "ajuda adm", "comandos admin"}:
        await enviar_menu_discord(message, secao="admin")
        return

    if await _tratar_lembrete_discord(message, _txt_norm):
        return

    if re.match(r'^!?\s*zpensa\b', _txt_norm):
        pedido_z = re.sub(r'^!?\s*zpensa\s*', '', _txt, flags=re.IGNORECASE).strip()
        if not pedido_z:
            await message.channel.send("manda o texto depois do !zpensa")
            registrar("OUT", "Link", autor, "manda o texto depois do !zpensa")
            return
        async with message.channel.typing():
            resposta_z = await responder_com_ia_local_tools(autor, pedido_z)
        resposta_z = sanitizar(resposta_z)
        if resposta_z:
            await message.channel.send(resposta_z)
            registrar("OUT", "Link", autor, resposta_z)
        return

    if re.match(r'^!?\s*z\b', _txt_norm):
        pedido_z = re.sub(r'^!?\s*z\s*', '', _txt, flags=re.IGNORECASE).strip()
        if not pedido_z:
            await message.channel.send("manda o texto depois do !Z")
            registrar("OUT", "Link", autor, "manda o texto depois do !Z")
            return
        async with message.channel.typing():
            resposta_z = await responder_com_ia_local(autor, pedido_z, think=False)
        resposta_z = sanitizar(resposta_z)
        if resposta_z:
            await message.channel.send(resposta_z)
            registrar("OUT", "Link", autor, resposta_z)
        return

    if re.match(r'^!?\s*(spot|spotify|spoty)\b', _txt_norm):
        pedido_spot = re.sub(r'^!?\s*(spot|spotify|spoty)\s*', '', _txt, flags=re.IGNORECASE).strip()
        async with message.channel.typing():
            await _discord_spot(message, autor, pedido_spot)
        return

    # Pedido natural de imagem/foto: baixa e envia arquivo direto, sem depender da IA.
    _quer_imagem = any(x in _txt_norm for x in ["imagem", "foto", "png", "jpg", "jpeg", "figura", "ilustracao", "artwork", "arte"])
    _acao_imagem = any(x in _txt_norm for x in ["busca", "pesquis", "procur", "acha", "encontra", "pega", "manda", "envia", "baixa", "download", "web", "internet", "google"])
    if _quer_imagem and _acao_imagem:
        async with message.channel.typing():
            import bot_supervisor as supervisor
            resposta_img = await asyncio.get_running_loop().run_in_executor(
                None, supervisor.baixar_imagem_e_enviar, _txt, autor
            )
        resposta_img = sanitizar(resposta_img)
        if resposta_img:
            await message.channel.send(resposta_img)
            registrar("OUT", "Link", autor, resposta_img)
        return

    if re.match(r'^triforce\b', _txt_norm):
        # Extrai o pedido (tudo depois de "TRIFORCE")
        pedido_tf = re.sub(r'^triforce\s*', '', _txt, flags=re.IGNORECASE).strip()
        if not pedido_tf:
            pedido_tf = f"{autor} quer falar com a triforce"
        await message.channel.send("✨ acionando triforce...")
        registrar("OUT", "Link", autor, "acionando triforce...")
        registrar("SYS", "Bot", "Claude", f"[TRIFORCE-PEDIDO] {pedido_tf}")
        return

    # ── MAJORA: escalação direta para Codex CLI, sem passar pelo LLM ─────────
    if re.match(r'^!?\s*(majora|codex)\b', _txt_norm):
        pedido_mx = re.sub(r'^!?\s*(majora|codex)\s*', '', _txt, flags=re.IGNORECASE).strip()
        if _txt_norm.strip() == "codex link":
            pedido_mx = f"{autor} quer retomar contexto"
        elif not pedido_mx:
            pedido_mx = f"{autor} quer falar com a majora"
        await message.channel.send("🌑 acionando majora...")
        registrar("OUT", "Link", autor, "acionando majora...")
        registrar("SYS", "Bot", "Codex", f"[MAJORA-PEDIDO] {pedido_mx}")
        return

    # ── MASTERSWORD: escalação direta para OpenCode, sem passar pelo LLM ─────
    if re.match(r'^!?\s*(mastersword|opencode)\b', _txt_norm):
        pedido_ms = re.sub(r'^!?\s*(mastersword|opencode)\s*', '', _txt, flags=re.IGNORECASE).strip()
        if _txt_norm.strip() == "opencode link":
            pedido_ms = f"{autor} quer retomar contexto"
        elif not pedido_ms:
            pedido_ms = f"{autor} quer falar com a mastersword"
        await message.channel.send("🗡️ acionando mastersword...")
        registrar("OUT", "Link", autor, "acionando mastersword...")
        registrar("SYS", "Bot", "OpenCode", f"[MASTERSWORD-PEDIDO] {pedido_ms}")
        return

    # Atualiza contexto: último arquivo recebido (apenas metadado)
    if anexos_meta:
        _set_ctx(autor, last_file={
            "nome": anexos_meta[-1]["nome"],
            "url":  anexos_meta[-1]["url"],
        })

    # ── Retry — re-executa último pedido de arquivo (keyword confiável) ──────
    _kw_retry = ["tenta novamente", "tenta de novo", "de novo", "again", "retry",
                 "nao funcionou", "não funcionou", "falhou", "faz novamente",
                 "faça novamente", "refaz", "refaça", "novamente", "repete"]
    quer_retry = any(kw in p_lower for kw in _kw_retry)

    if quer_retry and not anexos_meta:
        from datetime import datetime as _dt
        ts = _dt.now().strftime('%H%M%S')
        arquivos_recentes = []
        if os.path.exists(RECEIVED_META):
            try:
                dados_meta = json.load(open(RECEIVED_META, encoding="utf-8"))
                arquivos_recentes = dados_meta.get(autor, [])[-3:]
            except Exception:
                pass
        if arquivos_recentes:
            for a in arquivos_recentes:
                registrar("SYS", "Bot", "Claude",
                          f"[SHEIKAH_SLATE-PEDIDO] salva no desktop URL:{a['url']} nome:{a['nome']} [retry:{ts}]")
            await message.channel.send("tentando de novo...")
            registrar("OUT", "Link", autor, "tentando de novo...")
            return
        ultimo_pedido = _get_ctx(autor).get("last_pedido")
        if ultimo_pedido:
            registrar("SYS", "Bot", "Claude",
                      f"[SHEIKAH_SLATE-PEDIDO] {ultimo_pedido} [retry:{ts}]")
            await message.channel.send("tentando de novo...")
            registrar("OUT", "Link", autor, "tentando de novo...")
            return

    # ── PC → Discord (frase explícita — não ambígua) ──────────────────────────
    _kw_enviar = ["pro discord", "para o discord", "no discord",
                  "manda pro discord", "envia pro discord", "passa pro discord"]
    quer_enviar = any(kw in p_lower for kw in _kw_enviar) and not anexos_meta
    if quer_enviar:
        # Extrai nome do arquivo do pedido (se mencionado)
        nome_match = re.search(
            r'(?:o arquivo|o|a foto|a imagem|o print|arquivo)\s+([\w\-\.]+\.[\w]{2,5})',
            p_lower)
        nome_arq = nome_match.group(1) if nome_match else None
        pedido = f"envia pro discord arquivo:{nome_arq}" if nome_arq else "envia pro discord o ultimo arquivo do Desktop"
        _set_ctx(autor, last_pedido=pedido, last_action="enviar_discord")
        registrar("SYS", "Bot", "Claude", f"[SHEIKAH_SLATE-PEDIDO] {pedido}")
        await message.channel.send("Procurando o arquivo aqui...")
        registrar("OUT", "Link", autor, "Procurando o arquivo aqui...")
        return

    # ── Fluxo normal: LLM responde ────────────────────────────────────────────
    # Inclui info dos anexos na mensagem para o LLM decidir naturalmente
    mensagem_llm = message.content or ""
    if anexos_meta:
        for a in anexos_meta:
            mensagem_llm += f"\n[ARQUIVO: {a['nome']} | URL: {a['url']}]"

    async with message.channel.typing():
        resposta = await responder_com_ia(autor, mensagem_llm)

    claude_match = re.search(r'\[SHEIKAH_SLATE:\s*(.*?)\]', resposta, re.IGNORECASE | re.DOTALL)
    if claude_match:
        pedido = claude_match.group(1).strip()
        if _pedido_sheikah_executavel(pedido):
            _set_ctx(autor, last_pedido=pedido, last_action="llm")
            registrar("SYS", "Bot", "Claude", f"[SHEIKAH_SLATE-PEDIDO] {pedido}")
        else:
            registrar("SYS", "Bot", "Claude", f"[SHEIKAH_SLATE-IGNORADO] {pedido}")

    triforce_match = _TRIFORCE_RE.search(resposta)
    if triforce_match:
        pedido_tf = triforce_match.group(1).strip()
        registrar("SYS", "Bot", "Claude", f"[TRIFORCE-PEDIDO] {pedido_tf}")

    majora_match = _MAJORA_RE.search(resposta)
    if majora_match:
        pedido_mx = majora_match.group(1).strip()
        registrar("SYS", "Bot", "Codex", f"[MAJORA-PEDIDO] {pedido_mx}")

    mastersword_match = _MASTERSWORD_RE.search(resposta)
    if mastersword_match:
        pedido_ms = mastersword_match.group(1).strip()
        registrar("SYS", "Bot", "OpenCode", f"[MASTERSWORD-PEDIDO] {pedido_ms}")

    resposta_limpa = sanitizar(resposta)
    if resposta_limpa:
        await message.channel.send(resposta_limpa)
        registrar("OUT", "Link", autor, resposta_limpa)


# --- HTTP API ---

async def rota_send(request):
    try:
        data = await request.json()
        nome = data.get("to", "").strip()
        msg  = data.get("msg", "").strip()

        if not nome or not msg:
            return web.json_response({"ok": False, "error": "Campos 'to' e 'msg' obrigatorios"}, status=400)

        msg = sanitizar(msg)
        if not msg:
            return web.json_response({"ok": True, "skipped": "mensagem vazia apos strip"})

        # ✨ é exclusivo do /triforce — strip aqui para o LLM não poder fingir
        while msg.startswith("✨"):
            msg = msg.lstrip("✨").strip()
        if not msg:
            return web.json_response({"ok": True, "skipped": "mensagem vazia apos strip"})

        user = await buscar_user(nome)
        if not user:
            return web.json_response({"ok": False, "error": f"Usuario '{nome}' nao encontrado"}, status=404)

        await user.send(msg)
        registrar("OUT", "Link", user.name, msg)
        return web.json_response({"ok": True})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def rota_triforce(request):
    """Igual /send mas garante prefixo ✨ — identifica resposta do agente de código."""
    try:
        data = await request.json()
        nome = data.get("to", "").strip()
        msg  = data.get("msg", "").strip()

        if not nome or not msg:
            return web.json_response({"ok": False, "error": "Campos 'to' e 'msg' obrigatorios"}, status=400)

        if not msg.startswith("✨"):
            msg = f"✨ {msg}"
        msg = sanitizar(msg)

        user = await buscar_user(nome)
        if not user:
            return web.json_response({"ok": False, "error": f"Usuario '{nome}' nao encontrado"}, status=404)

        await user.send(msg)
        registrar("OUT", "Link", user.name, msg)
        return web.json_response({"ok": True})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def rota_send_file(request):
    """
    Envia um arquivo pelo Discord DM.
    Body: {"to": "OWNER", "file": "caminho/absoluto", "msg": "opcional"}
    """
    try:
        data     = await request.json()
        nome     = data.get("to", "").strip()
        filepath = data.get("file", "").strip()
        msg      = data.get("msg", "")
        delete_after = bool(data.get("delete_after"))

        user = await buscar_user(nome)
        if not user:
            return web.json_response({"ok": False, "error": f"Usuario '{nome}' nao encontrado"}, status=404)

        if not os.path.exists(filepath):
            return web.json_response({"ok": False, "error": f"Arquivo nao encontrado: {filepath}"}, status=404)

        tamanho_mb = os.path.getsize(filepath) / 1024 / 1024
        if tamanho_mb > 8:
            return web.json_response({
                "ok": False,
                "error": f"arquivo_grande",
                "tamanho_mb": round(tamanho_mb, 1),
                "limite_mb": 8
            }, status=413)

        await user.send(content=msg or None, file=discord.File(filepath))

        nome_arquivo = os.path.basename(filepath)
        registrar("OUT", "Link", user.name, f"[ARQUIVO: {nome_arquivo}] {msg}".strip())
        if delete_after:
            try:
                os.remove(filepath)
                print(f"[DELETE_AFTER_SEND] {filepath}", flush=True)
            except FileNotFoundError:
                pass
        return web.json_response({"ok": True, "arquivo": nome_arquivo})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def rota_download(request):
    """
    Baixa um arquivo de uma URL do Discord para a pasta files/.
    Body: {"url": "https://...", "filename": "nome.ext"}
    Retorna: {"ok": true, "path": "caminho/local"}
    """
    try:
        data     = await request.json()
        url      = data.get("url", "").strip()
        filename = data.get("filename", "").strip()

        if not url or not filename:
            return web.json_response({"ok": False, "error": "Campos 'url' e 'filename' obrigatorios"}, status=400)

        # Sanitiza nome do arquivo
        filename = os.path.basename(filename)
        dest = os.path.join(FILES_DIR, filename)

        async with aiohttp_client.ClientSession() as session:
            async with session.get(url) as resp:
                if resp.status != 200:
                    return web.json_response({"ok": False, "error": f"Erro ao baixar: HTTP {resp.status}"}, status=500)
                with open(dest, "wb") as f:
                    f.write(await resp.read())

        tamanho = round(os.path.getsize(dest) / 1024 / 1024, 2)
        print(f"[DOWNLOAD] {filename} ({tamanho} MB) -> {dest}\n", flush=True)
        return web.json_response({"ok": True, "path": dest, "tamanho_mb": tamanho})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def rota_chat(request):
    """Console local — processa mensagem e retorna resposta sem enviar ao Discord."""
    try:
        data = await request.json()
        autor = data.get("from", "OWNER").strip()
        msg   = data.get("msg", "").strip()
        if not msg:
            return web.json_response({"ok": False, "error": "msg vazia"}, status=400)
        autor_key = autor.lower().replace(" ", "_")
        registrar("IN", autor, "Link", f"[CONSOLE] {msg}")
        resposta = await responder_com_ia(autor_key, msg)

        # Processa SHEIKAH_SLATE igual ao fluxo do Discord
        claude_match = re.search(r'\[SHEIKAH_SLATE:\s*(.*?)\]', resposta, re.IGNORECASE | re.DOTALL)
        if claude_match:
            pedido = claude_match.group(1).strip()
            _set_ctx(autor_key, last_pedido=pedido, last_action="llm")
            registrar("SYS", "Bot", "Claude", f"[SHEIKAH_SLATE-PEDIDO] {pedido}")

        triforce_match = _TRIFORCE_RE.search(resposta)
        if triforce_match:
            pedido_tf = triforce_match.group(1).strip()
            registrar("SYS", "Bot", "Claude", f"[TRIFORCE-PEDIDO] {pedido_tf}")

        majora_match = _MAJORA_RE.search(resposta)
        if majora_match:
            pedido_mx = majora_match.group(1).strip()
            registrar("SYS", "Bot", "Codex", f"[MAJORA-PEDIDO] {pedido_mx}")

        mastersword_match = _MASTERSWORD_RE.search(resposta)
        if mastersword_match:
            pedido_ms = mastersword_match.group(1).strip()
            registrar("SYS", "Bot", "OpenCode", f"[MASTERSWORD-PEDIDO] {pedido_ms}")

        resposta_limpa = sanitizar(resposta)
        registrar("OUT", "Link", autor, f"[CONSOLE] {resposta_limpa}")
        return web.json_response({"ok": True, "resposta": resposta_limpa})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def rota_messages(request):
    limit = int(request.rel_url.query.get("limit", 20))
    return web.json_response(buffer[-limit:])


async def rota_history(request):
    try:
        nome  = request.rel_url.query.get("user", "")
        limit = int(request.rel_url.query.get("limit", 20))

        nome_key = resolver_usuario(nome)
        if not nome_key:
            return web.json_response({"ok": False, "error": f"Usuario '{nome}' nao encontrado"}, status=404)

        user    = await client.fetch_user(USUARIOS[nome_key])
        channel = await user.create_dm()

        msgs = []
        async for m in channel.history(limit=limit, oldest_first=False):
            anexos = [{"nome": a.filename, "url": a.url, "tamanho_mb": round(a.size / 1024 / 1024, 2)} for a in m.attachments]
            msgs.append({
                "id":      str(m.id),
                "autor":   m.author.name,
                "meu":     m.author == client.user,
                "conteudo": m.content,
                "data":    m.created_at.astimezone(BRT).strftime("%d/%m/%Y %H:%M:%S"),
                "anexos":  anexos
            })

        return web.json_response({"ok": True, "usuario": nome_key, "mensagens": msgs})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def rota_delete(request):
    try:
        data  = await request.json()
        nome  = data.get("to", "").strip()
        count = data.get("count", None)
        ids   = data.get("ids", None)

        user = await buscar_user(nome)
        if not user:
            return web.json_response({"ok": False, "error": f"Usuario '{nome}' nao encontrado"}, status=404)

        channel = await user.create_dm()

        deletadas = 0
        erros = []

        if ids:
            for mid in ids:
                try:
                    msg = await channel.fetch_message(int(mid))
                    if msg.author == client.user:
                        await msg.delete()
                        deletadas += 1
                        await asyncio.sleep(0.5)
                except discord.NotFound:
                    erros.append(f"ID {mid} nao encontrado")
                except discord.Forbidden:
                    erros.append(f"ID {mid} sem permissao")
                except Exception as e:
                    erros.append(f"ID {mid}: {e}")
        elif count:
            async for m in channel.history(limit=None):
                if m.author == client.user:
                    try:
                        await m.delete()
                        deletadas += 1
                        await asyncio.sleep(0.5)
                        if deletadas >= count:
                            break
                    except discord.HTTPException as e:
                        if e.status == 429:
                            await asyncio.sleep(e.retry_after if hasattr(e, "retry_after") else 5)
                        erros.append(str(e))
        else:
            return web.json_response({"ok": False, "error": "Informe 'count' ou 'ids'"}, status=400)

        return web.json_response({"ok": True, "deletadas": deletadas, "erros": erros})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def rota_clear_history(request):
    """Limpa historico em memoria e no disco de um usuario ou de todos."""
    try:
        data = await request.json()
        user = data.get("user", "").strip()
        if user:
            historico_ia.pop(user, None)
            path = _history_file(user)
            if os.path.exists(path):
                os.remove(path)
            return web.json_response({"ok": True, "cleared": user})
        else:
            historico_ia.clear()
            import glob as _glob
            for f in _glob.glob(os.path.join(HISTORY_DIR, "*.json")):
                os.remove(f)
            return web.json_response({"ok": True, "cleared": "all"})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def rota_edit(request):
    """Edita uma mensagem própria do bot. Body: {to, msg_id, novo_conteudo}"""
    try:
        data = await request.json()
        nome = data.get("to", "").strip()
        msg_id = int(data.get("msg_id", 0))
        novo = sanitizar(data.get("novo_conteudo", "").strip())
        if not nome or not msg_id or not novo:
            return web.json_response({"ok": False, "error": "Campos obrigatorios: to, msg_id, novo_conteudo"}, status=400)
        nome_key = resolver_usuario(nome)
        if not nome_key:
            return web.json_response({"ok": False, "error": f"Usuario '{nome}' nao encontrado"}, status=404)
        user = await client.fetch_user(USUARIOS[nome_key])
        channel = await user.create_dm()
        msg = await channel.fetch_message(msg_id)
        if msg.author != client.user:
            return web.json_response({"ok": False, "error": "Nao posso editar mensagens de outros"}, status=403)
        await msg.edit(content=novo)
        registrar("OUT", "Link", user.name, f"[EDITADO] {novo}")
        return web.json_response({"ok": True})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def rota_react(request):
    """Adiciona reacao a uma mensagem. Body: {to, msg_id, emoji}"""
    try:
        data = await request.json()
        nome = data.get("to", "").strip()
        msg_id = int(data.get("msg_id", 0))
        emoji = data.get("emoji", "👍").strip()
        nome_key = resolver_usuario(nome)
        if not nome_key:
            return web.json_response({"ok": False, "error": f"Usuario '{nome}' nao encontrado"}, status=404)
        user = await client.fetch_user(USUARIOS[nome_key])
        channel = await user.create_dm()
        msg = await channel.fetch_message(msg_id)
        await msg.add_reaction(emoji)
        return web.json_response({"ok": True})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def rota_pin(request):
    """Fixa uma mensagem. Body: {to, msg_id}"""
    try:
        data = await request.json()
        nome = data.get("to", "").strip()
        msg_id = int(data.get("msg_id", 0))
        nome_key = resolver_usuario(nome)
        if not nome_key:
            return web.json_response({"ok": False, "error": f"Usuario '{nome}' nao encontrado"}, status=404)
        user = await client.fetch_user(USUARIOS[nome_key])
        channel = await user.create_dm()
        msg = await channel.fetch_message(msg_id)
        await msg.pin()
        return web.json_response({"ok": True})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def rota_status(request):
    return web.json_response({
        "online":              client.is_ready(),
        "bot":                 str(client.user) if client.is_ready() else None,
        "usuarios":            list(USUARIOS.keys()),
        "mensagens_em_buffer": len(buffer),
        "files_dir":           FILES_DIR
    })


async def start_http():
    app = web.Application()
    app.router.add_post("/send",          rota_send)
    app.router.add_post("/triforce",      rota_triforce)
    app.router.add_post("/send-file",     rota_send_file)
    app.router.add_post("/download",      rota_download)
    app.router.add_post("/delete",        rota_delete)
    app.router.add_post("/edit",          rota_edit)
    app.router.add_post("/react",         rota_react)
    app.router.add_post("/pin",           rota_pin)
    app.router.add_post("/chat",           rota_chat)
    app.router.add_get("/messages",       rota_messages)
    app.router.add_get("/history",        rota_history)
    app.router.add_get("/status",         rota_status)
    app.router.add_post("/clear-history", rota_clear_history)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "localhost", 7331)
    await site.start()


async def main():
    await start_http()
    await client.start(TOKEN)


if __name__ == "__main__":
    asyncio.run(main())
