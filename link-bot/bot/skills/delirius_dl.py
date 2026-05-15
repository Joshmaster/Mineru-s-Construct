"""Downloads via Delirius Store API.

Suporta: YouTube (MP3/MP4), Spotify, Instagram, Twitter/X.
Ativa por comando explícito (!yt, !spot, !ig, !x, !baixa)
ou por detecção automática de URL no texto (main.py injeta antes do router).
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import subprocess
import tempfile
import time
import urllib.parse
import urllib.request
from pathlib import Path

import httpx

from bot.core.router import Skill
from bot.core.context import MessageContext
from bot.core import llm as _llm

BASE = "https://api.delirius.store"
TIMEOUT_API = 45   # timeout da chamada à API Delirius
TIMEOUT_DL  = 90   # timeout do download do arquivo
log = logging.getLogger("delirius_dl")

# Regex de URLs suportadas — usados tanto aqui quanto em main.py via detect_url()
_RE_YT      = re.compile(r"https?://(?:www\.)?(?:youtube\.com/(?:watch\?[^\s]*v=|shorts/)|youtu\.be/)[\w\-]+(?:[^\s]*)?")
_RE_SPOTIFY = re.compile(r"https?://open\.spotify\.com/(?:track|album|playlist)/[\w]+")
_RE_IG      = re.compile(r"https?://(?:www\.)?instagram\.com/(?:p|reel|reels)/[\w\-]+")
_RE_TW      = re.compile(r"https?://(?:www\.)?(?:twitter\.com|x\.com)/\w+/status/\d+")


# ── Helpers ───────────────────────────────────────────────────────────────────

def _get_json(path: str, params: dict, timeout: int = TIMEOUT_API, attempts: int = 2) -> dict | None:
    """Faz GET na Delirius API e retorna o JSON. Retorna None se falhar."""
    url = f"{BASE}{path}?" + urllib.parse.urlencode(params)
    headers = {
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/125 Safari/537.36",
        "Accept": "application/json,text/plain,*/*",
    }
    for attempt in range(1, attempts + 1):
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.loads(r.read().decode("utf-8"))
        except Exception as e:
            log.warning(f"Delirius {path} falhou tentativa {attempt}/{attempts}: {e}")
            if attempt < attempts:
                time.sleep(1)
    return None


def _extract_url(data) -> str | None:
    """Percorre recursivamente a resposta Delirius procurando a primeira URL de mídia.
    A API pode retornar a URL em campos diferentes dependendo do endpoint.
    """
    if isinstance(data, str) and data.startswith("http"):
        return data
    if isinstance(data, list):
        for item in data:
            found = _extract_url(item)
            if found:
                return found
        return None
    if not isinstance(data, dict):
        return None
    for key in ("url", "link", "download", "audio", "video", "media", "result", "mp3", "mp4"):
        val = data.get(key)
        if isinstance(val, str) and val.startswith("http"):
            return val
    for key in ("data", "result", "info"):
        nested = data.get(key)
        if nested:
            found = _extract_url(nested)
            if found:
                return found
    return None


def _extract_title(data: dict) -> str:
    """Extrai o título da mídia da resposta Delirius (procura nas chaves comuns e em dicts aninhados)."""
    if not isinstance(data, dict):
        return ""
    for key in ("title", "titulo", "name"):
        val = data.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip()
    for key in ("data", "result", "info"):
        nested = data.get(key)
        if isinstance(nested, dict):
            t = _extract_title(nested)
            if t:
                return t
    return ""


def _extract_artist(data: dict) -> str:
    """Extrai artista/autor da resposta Delirius, incluindo dicts aninhados."""
    if not isinstance(data, dict):
        return ""
    for key in ("artist", "artists", "author", "uploader"):
        val = data.get(key)
        if isinstance(val, list):
            val = ", ".join(str(a) for a in val)
        if isinstance(val, str) and val.strip():
            return val.strip()
    for key in ("data", "result", "info"):
        nested = data.get(key)
        if isinstance(nested, dict):
            artist = _extract_artist(nested)
            if artist:
                return artist
    return ""


def _spotify_clean_query(query: str) -> str:
    query = re.sub(r"^(?:link|musica|música|baixar|baixa|manda|mp3)\s+", "", query.strip(), flags=re.IGNORECASE)
    query = re.sub(r"[._-]+", " ", query)
    replacements = {
        r"\bbluesky\b": "blue sky",
        r"\beletric\b": "electric",
        r"\belectic\b": "electric",
        r"\blith\b": "light",
    }
    for pattern, repl in replacements.items():
        query = re.sub(pattern, repl, query, flags=re.IGNORECASE)
    return re.sub(r"\s+", " ", query).strip()


def _is_contextual_music_query(query: str) -> bool:
    low = (query or "").casefold()
    return "contexto musical anterior:" in low and any(x in low for x in (
        "outra famosa", "outro famoso", "mais famosa", "mais famoso",
        "outra musica", "outra música", "mais uma", "mesma banda",
        "desse artista", "dessa banda", "mais outra", "outra dela",
        "outra dele", "do mesmo artista", "do mesmo estilo",
    ))


def _artist_from_music_context(text: str) -> str:
    m = re.search(r"🎵\s*.+?\s+[—-]\s*([^\n]+)", text or "")
    if m:
        return re.sub(r"\s+", " ", m.group(1)).strip()
    return ""


def _youtube_clean_query(query: str) -> str:
    """Remove palavras de comando antes da busca no YouTube."""
    query = re.sub(r"^\s*(?:link|ei\s+link|ô\s+link|o\s+link)[,:\s-]*", "", query.strip(), flags=re.IGNORECASE)
    query = re.sub(r"!\w+", " ", query)
    query = re.sub(
        r"^(?:(?:link|youtube|yutube|youtu|yt|ytmp3|ytmp4|video|vídeo|musica|música|baixar|baixa|toca|tocar|manda|mp3|mp4)\s+)+",
        "",
        query,
        flags=re.IGNORECASE,
    )
    query = re.sub(r"\b(?:via|no|na|pelo|pela|do|da)\s+(?:youtube|yutube|youtu|yt)\b", " ", query, flags=re.IGNORECASE)
    query = re.sub(r"\b(?:youtube|yutube|youtu|yt)\b", " ", query, flags=re.IGNORECASE)
    return re.sub(r"\s+", " ", query).strip()


def _is_youtube_intent(raw_text: str, norm_text: str) -> bool:
    raw = (raw_text or "").strip().lower()
    youtube_commands = ("!yt", "!ytmp3", "!ytv", "!ytmp4")
    return (
        raw in youtube_commands
        or raw.startswith(tuple(f"{cmd}{sep}" for cmd in youtube_commands for sep in (" ", ":")))
        or any(w in norm_text for w in ("youtube", "yutube", "youtu", "ytmp", " yt "))
    )


def _spotify_item_text(item: dict) -> str:
    if not isinstance(item, dict):
        return ""
    parts: list[str] = []
    for key in ("title", "name", "artist", "artists", "author"):
        val = item.get(key)
        if isinstance(val, list):
            val = " ".join(str(v) for v in val)
        if isinstance(val, str) and val.strip():
            parts.append(val)
    return " ".join(parts).casefold()


def _allows_alternate_version(query: str) -> bool:
    return bool(re.search(
        r"\b(cover|karaoke|remix|instrumental|sped\s*up|slowed|nightcore|live|ao vivo|acustic[ao]|acoustic|tribute|vers[aã]o)\b",
        query,
        re.IGNORECASE,
    ))


def _looks_non_original(item: dict) -> bool:
    text = _spotify_item_text(item)
    bad_words = (
        "cover", "karaoke", "tribute", "remix", "sped up", "slowed",
        "nightcore", "instrumental", "live", "ao vivo", "version",
        "versao", "versão", "reimagined",
    )
    return any(word in text for word in bad_words)


def _youtube_search(query: str, *, prefer_original: bool = True) -> dict | None:
    query = re.sub(r"\s+", " ", str(query or "")).strip()
    if not query:
        return None
    data = _get_json("/search/ytsearch", {"q": query}, timeout=30, attempts=2)
    items = (data or {}).get("data")
    if not isinstance(items, list) or not items:
        return None
    candidates = [item for item in items if isinstance(item, dict) and item.get("url")]
    if not candidates:
        return None
    if prefer_original:
        for item in candidates:
            if not _looks_non_original(item):
                return item
    return candidates[0]


def _spotify_search(query: str, *, prefer_original: bool = True) -> dict | None:
    """Busca uma faixa no Spotify via Delirius e retorna o melhor resultado."""
    query = _spotify_clean_query(query)
    if not query:
        return None
    data = _get_json("/search/spotify", {"q": query, "limit": 6}, timeout=30, attempts=2)
    items = (data or {}).get("data")
    if not isinstance(items, list) or not items:
        return None
    candidates = [item for item in items if isinstance(item, dict)]
    if not candidates:
        return None
    if prefer_original:
        for item in candidates:
            if not _looks_non_original(item):
                return item
    return candidates[0]


def _spotify_search_candidates(query: str, *, context: str = "") -> list[str]:
    """Gera consultas candidatas para achar melhor a musica que o usuario quis.

    context: texto original do usuario (antes do strip pelo classify) — dá mais
    informação ao LLM de query rewriting (ex: sabe que 'zelda' é jogo, não artista).
    """
    clean = _spotify_clean_query(query)
    contextual = _is_contextual_music_query(query) or _is_contextual_music_query(context)
    artist = _artist_from_music_context(query) or _artist_from_music_context(context)
    # Usa o contexto original quando disponível; cai no query limpo caso contrário
    llm_input = context.strip() if context and context.strip() != query else query
    candidates: list[str] = []
    try:
        candidates.extend(_llm.spotify_search_queries(llm_input))
    except Exception as e:
        log.debug(f"LLM spotify_search_queries falhou: {e}")
    if contextual and artist:
        candidates.extend([f"{artist} popular songs", f"{artist} greatest hits"])
    elif clean and clean.casefold() not in {c.casefold() for c in candidates}:
        candidates.append(clean)

    seen: set[str] = set()
    out: list[str] = []
    for item in candidates:
        q = _spotify_clean_query(item)
        key = q.casefold()
        if not q or key in seen:
            continue
        seen.add(key)
        out.append(q)
        if len(out) >= 5:
            break
    return out


async def _spotify_youtube_fallback(ctx: MessageContext, query: str, *, prefer_original: bool = True) -> bool:
    """Tenta enviar via YouTube quando o download do Spotify falha."""
    result = _youtube_search(query, prefer_original=prefer_original)
    url = (result or {}).get("url")
    if not url:
        return False
    title = (result or {}).get("title") or query
    log.info(f"Spotify fallback YouTube '{query}' => {title} ({url})")
    await _yt(ctx, url, "mp3", caption_extra=f"YouTube: {url}")
    return True


async def _youtube_query(ctx: MessageContext, query: str, modo: str = "mp3", *, prefer_original: bool = True) -> bool:
    """Busca no YouTube por texto e baixa o primeiro resultado adequado."""
    clean = _youtube_clean_query(query)
    if not clean:
        return False
    result = _youtube_search(clean, prefer_original=prefer_original)
    url = (result or {}).get("url")
    if not url:
        await ctx.reply("não achei isso no YouTube")
        return True
    title = (result or {}).get("title") or clean
    log.info(f"YouTube busca '{query}' -> {title} ({url})")
    await _yt(ctx, url, modo, caption_extra=f"YouTube: {url}")
    return True


async def _baixar(url: str, ext: str) -> str | None:
    """Baixa o arquivo da URL para um arquivo temporário e retorna o caminho local.
    Retorna None se o download falhar ou o servidor responder com erro.
    """
    out = Path(tempfile.gettempdir()) / f"hyrule_dl_{int(time.time())}.{ext}"
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT_DL, follow_redirects=True) as client:
            r = await client.get(url)
            if r.status_code == 200:
                out.write_bytes(r.content)
                return str(out)
    except Exception:
        pass
    return None


def _rm(path: str | None):
    """Remove o arquivo temporário após envio. Silencia FileNotFoundError (já apagado)."""
    if path:
        try:
            os.unlink(path)
        except FileNotFoundError:
            pass


async def _to_whatsapp_ogg(path: str) -> str | None:
    """Converte áudio para OGG/Opus estéreo, sem capa/metadata, aceito pelo WhatsApp."""
    out = Path(tempfile.gettempdir()) / f"hyrule_audio_{int(time.time())}.ogg"
    cmd = [
        "ffmpeg", "-y",
        "-i", path,
        "-vn",
        "-map_metadata", "-1",
        "-ac", "2",
        "-ar", "48000",
        "-c:a", "libopus",
        "-b:a", "64k",
        str(out),
    ]
    try:
        proc = await asyncio.to_thread(
            subprocess.run,
            cmd,
            capture_output=True,
            text=True,
            timeout=90,
        )
        if proc.returncode == 0 and out.exists() and out.stat().st_size > 0:
            return str(out)
        log.warning(f"ffmpeg opus falhou: {proc.stderr[-500:]}")
    except Exception as e:
        log.warning(f"ffmpeg opus erro: {e}")
    return None


async def _send_audio_track(ctx: MessageContext, path: str, caption: str = ""):
    """Envia música como áudio normal, preservando o MP3 quando possível."""
    if ctx.client is not None and hasattr(ctx.client, "send_audio"):
        resp = await ctx.client.send_audio(ctx.chat_jid, path, ptt=False)
        if hasattr(ctx, "remember_sent_music"):
            ctx.remember_sent_music(getattr(resp, "ID", "") or getattr(resp, "ServerID", ""), caption)
        if caption:
            text_resp = await ctx.client.send_message(
                ctx.chat_jid,
                caption,
                quoted_id=ctx.message_id or "",
                quoted_sender=ctx._sender_str() if ctx.is_group else "",
            )
            if hasattr(ctx, "remember_sent_music"):
                ctx.remember_sent_music(getattr(text_resp, "ID", "") or getattr(text_resp, "ServerID", ""), caption)
        return
    await ctx.reply_media(path, caption=caption)


# ── Handlers por plataforma ───────────────────────────────────────────────────

async def _yt(ctx: MessageContext, url: str, modo: str, caption_extra: str = ""):
    """Baixa áudio (MP3) ou vídeo (MP4) de um link do YouTube via Delirius.
    Tenta o endpoint v1 e cai no v2 se o primeiro falhar.
    O modo é detectado pelo handle() com base nas palavras da mensagem.
    """
    if modo == "mp4":
        data = (
            _get_json("/download/ytmp4", {"url": url, "format": "360p"})
            or _get_json("/download/ytmp4v2", {"url": url, "format": "360"})
        )
        ext, caption = "mp4", "📹 vídeo do YouTube"
    else:
        data = (
            _get_json("/download/ytmp3", {"url": url})
            or _get_json("/download/ytmp3v2", {"url": url})
        )
        ext, caption = "mp3", "🎵 áudio do YouTube"

    if not data:
        await ctx.reply("API fora agora, tenta de novo daqui a pouco")
        return

    media_url = _extract_url(data)
    if not media_url:
        await ctx.reply(f"não achei o arquivo na resposta 🌀\n`{str(data)[:200]}`")
        return

    title = _extract_title(data)
    if title:
        caption = f"{caption}\n_{title}_"
    if caption_extra:
        caption = f"{caption}\n{caption_extra}"

    path = await _baixar(media_url, ext)
    if not path:
        await ctx.reply("baixei o link mas não consegui salvar o arquivo")
        return
    try:
        if ext == "mp3":
            await _send_audio_track(ctx, path, caption=caption)
        else:
            await ctx.reply_media(path, caption=caption)
    finally:
        _rm(path)


async def _spotify(ctx: MessageContext, url: str, *, fallback_query: str = "", prefer_original: bool = True):
    """Baixa a faixa de um link do Spotify como MP3 via Delirius.
    Monta a legenda com título e artista se a API retornar esses dados.
    """
    data = _get_json("/download/spotifydl", {"url": url}, timeout=90, attempts=2)
    if not isinstance(data, dict):
        if fallback_query and await _spotify_youtube_fallback(ctx, fallback_query, prefer_original=prefer_original):
            return
        await ctx.reply("API fora agora")
        return

    media_url = _extract_url(data)
    if not media_url:
        if fallback_query and await _spotify_youtube_fallback(ctx, fallback_query, prefer_original=prefer_original):
            return
        await ctx.reply(f"resposta inesperada 🌀\n`{str(data)[:200]}`")
        return

    title  = _extract_title(data)
    artist = _extract_artist(data)
    header = f"🎵 {title} — {artist}".strip(" —") if title else "🎵 Spotify"
    caption = f"{header}\nSpotify: {url}"

    path = await _baixar(media_url, "mp3")
    if not path:
        if fallback_query and await _spotify_youtube_fallback(ctx, fallback_query, prefer_original=prefer_original):
            return
        await ctx.reply("não consegui baixar o arquivo")
        return
    try:
        await _send_audio_track(ctx, path, caption=caption)
    finally:
        _rm(path)


async def _spotify_query(ctx: MessageContext, query: str, *, context: str = ""):
    """Busca a faixa pelo texto, refinando a consulta com LLM quando possivel.

    context: mensagem original do usuário — passada ao LLM de query rewriting
    para gerar buscas mais precisas sem depender só dos args stripados.
    """
    prefer_original = not _allows_alternate_version(query)
    candidates = _spotify_search_candidates(query, context=context)
    result = None
    used_query = ""
    for candidate in candidates:
        result = _spotify_search(candidate, prefer_original=prefer_original)
        if result:
            used_query = candidate
            break
    url = (result or {}).get("url")
    if not url:
        await ctx.reply("não achei essa música no Spotify")
        return
    if used_query:
        title = (result or {}).get("title") or (result or {}).get("name") or ""
        artist = (result or {}).get("artist") or (result or {}).get("artists") or ""
        if isinstance(artist, list):
            artist = ", ".join(str(a) for a in artist)
        log.info(f"Spotify busca '{query}' -> '{used_query}' => {title} — {artist}")
    fallback_query = " ".join(str(x) for x in (title, artist) if x).strip() or used_query or query
    await _spotify(ctx, url, fallback_query=fallback_query, prefer_original=prefer_original)


async def _instagram(ctx: MessageContext, url: str):
    """Baixa foto ou vídeo de um post/reel do Instagram via Delirius.
    Tenta instagramv2 primeiro (mais estável) e cai no v1 se falhar.
    Detecta se é vídeo pelo conteúdo da resposta para escolher a extensão correta.
    """
    data = (
        _get_json("/download/instagramv2", {"url": url})
        or _get_json("/download/instagram", {"url": url})
    )
    if not data:
        await ctx.reply("API fora agora")
        return

    media_url = _extract_url(data)
    if not media_url:
        await ctx.reply(f"não achei mídia 🌀\n`{str(data)[:200]}`")
        return

    is_video = any(k in str(data).lower() for k in ("video", "mp4", "reel"))
    ext = "mp4" if is_video else "jpg"
    path = await _baixar(media_url, ext)
    if not path:
        await ctx.reply("não consegui baixar")
        return
    try:
        await ctx.reply_media(path, caption="📸 Instagram")
    finally:
        _rm(path)


async def _twitter(ctx: MessageContext, url: str):
    """Baixa o vídeo de um tweet/post do Twitter ou X via Delirius."""
    data = _get_json("/download/twitterdl", {"url": url})
    if not data:
        await ctx.reply("API fora agora")
        return

    media_url = _extract_url(data)
    if not media_url:
        await ctx.reply(f"não achei mídia 🌀\n`{str(data)[:200]}`")
        return

    path = await _baixar(media_url, "mp4")
    if not path:
        await ctx.reply("não consegui baixar")
        return
    try:
        await ctx.reply_media(path, caption="🐦 Twitter/X")
    finally:
        _rm(path)


# ── Detecção de URL ───────────────────────────────────────────────────────────

def detect_url(text: str) -> tuple[str | None, str | None]:
    """Procura no texto uma URL de plataforma suportada e retorna (url, tipo).
    Tipos possíveis: 'yt', 'spotify', 'ig', 'twitter'. Retorna (None, None) se não achar.
    Chamado por main.py antes do router para interceptar URLs coladas sem comando.
    """
    m = _RE_YT.search(text)
    if m:
        return m.group(0), "yt"
    m = _RE_SPOTIFY.search(text)
    if m:
        return m.group(0), "spotify"
    m = _RE_IG.search(text)
    if m:
        return m.group(0), "ig"
    m = _RE_TW.search(text)
    if m:
        return m.group(0), "twitter"
    return None, None


# ── Handler principal ─────────────────────────────────────────────────────────

async def handle(ctx: MessageContext):
    """Handler da skill delirius_dl.
    Detecta a URL e o tipo de plataforma no texto completo da mensagem,
    depois chama o handler específico (_yt, _spotify, _instagram, _twitter).
    Para YouTube decide entre MP3 e MP4 pelas palavras da mensagem (video/mp4 → mp4, resto → mp3).
    """
    text = f"{ctx.raw_text} {ctx.args_text}".strip()
    norm = text.lower()

    url, tipo = detect_url(text)

    if not url:
        args = ctx.args_text.strip()
        youtube_intent = _is_youtube_intent(ctx.raw_text, norm)
        youtube_video = any(w in norm for w in ("vídeo", "video", "mp4", "assisti", "ytv", "ytmp4"))
        if youtube_intent:
            if args:
                await ctx.typing()
                await _youtube_query(ctx, args, "mp4" if youtube_video else "mp3")
                return
            await ctx.reply("qual música ou vídeo do YouTube?")
            return
        # Instagram precisa de link
        if any(w in norm for w in ("instagram", " ig ", "insta", "reels", "reel")):
            await ctx.reply("manda o link do Instagram junto 🔗")
            return
        # Twitter/X precisa de link
        if any(w in norm for w in ("twitter", " x.com", "/status/")):
            await ctx.reply("manda o link do Twitter/X junto 🔗")
            return
        # Spotify aceita busca por texto — qualquer menção a música/spot vai pra cá
        if args and any(w in norm for w in ("spot", "spotify", "música", "musica", "song", "faixa", "track", "toca", "tocar", "ouvi", "play", "baixa", "baixar", "manda")):
            await ctx.typing()
            await _spotify_query(ctx, args, context=ctx.raw_text)
            return
        # args limpos vindos do AI matcher → assume Spotify
        if args:
            await ctx.typing()
            await _spotify_query(ctx, args, context=ctx.raw_text)
            return
        await ctx.reply(
            "manda o link junto 🔗\n"
            "_aceito: YouTube, Spotify, Instagram, Twitter/X_\n"
            "_Spotify também aceita busca por texto._\n\n"
            "exemplos:\n"
            "`!yt zelda lost woods`\n"
            "`!spot zelda lost woods`\n"
            "`!ig https://instagram.com/reel/...`"
        )
        return

    await ctx.typing()

    if tipo == "yt":
        modo = "mp4" if any(w in norm for w in ("vídeo", "video", "mp4", "assisti")) else "mp3"
        await _yt(ctx, url, modo)
    elif tipo == "spotify":
        await _spotify(ctx, url)
    elif tipo == "ig":
        await _instagram(ctx, url)
    elif tipo == "twitter":
        await _twitter(ctx, url)


SKILL = Skill(
    name="delirius_dl",
    description=(
        "Baixar músicas, vídeos e mídias — use quando alguém pede pra baixar, mandar, tocar ou buscar mídia.\n"
        "Suporta: Spotify (busca por texto ou link), YouTube (busca por texto ou link, MP3/MP4), Instagram, Twitter/X.\n"
        "*!spot <busca ou link>* — baixar/buscar no Spotify\n"
        "*!yt <busca ou link>* — áudio do YouTube (MP3)\n"
        "*!ytv <busca ou link>* — vídeo do YouTube (MP4)\n"
        "*!ig <link>* — baixar do Instagram\n"
        "*!x <link>* — baixar do Twitter/X"
    ),
    triggers=[
        "!baixa", "!dl", "!download",
        "!yt", "!ytmp3",
        "!ytv", "!ytmp4",
        "!spotify", "!spot", "!spoty",
        "!ig", "!insta", "!instagram",
        "!x", "!twitter",
    ],
    handler=handle,
    category="midia",
    priority=110,
)
