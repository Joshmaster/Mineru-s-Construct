"""Downloads de mídia com caminho local via yt-dlp e Delirius como fallback.

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
import threading
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

try:
    from yt_dlp import YoutubeDL
except Exception:
    YoutubeDL = None

# Regex de URLs suportadas — usados tanto aqui quanto em main.py via detect_url()
_RE_YT      = re.compile(r"https?://(?:www\.)?(?:youtube\.com/(?:watch\?[^\s]*v=|shorts/)|youtu\.be/)[\w\-]+(?:[^\s]*)?")
_RE_SPOTIFY = re.compile(r"https?://open\.spotify\.com/(?:track|album|playlist)/[\w]+")
_RE_IG      = re.compile(r"https?://(?:www\.)?instagram\.com/(?:p|reel|reels)/[\w\-]+")
_RE_TW      = re.compile(r"https?://(?:www\.)?(?:twitter\.com|x\.com)/\w+/status/\d+")


# ── Helpers ───────────────────────────────────────────────────────────────────

def _get_json(path: str, params: dict, timeout: int = TIMEOUT_API, attempts: int = 2) -> dict | None:
    """Faz GET na Delirius API e retorna o JSON. Retorna None se falhar.
    Usa thread com join(timeout) como hard wall-clock timeout — urllib socket timeout
    não cobre travamentos entre chunks.
    """
    url = f"{BASE}{path}?" + urllib.parse.urlencode(params)
    headers = {
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/125 Safari/537.36",
        "Accept": "application/json,text/plain,*/*",
    }
    for attempt in range(1, attempts + 1):
        result: list = []
        def _fetch():
            try:
                req = urllib.request.Request(url, headers=headers)
                with urllib.request.urlopen(req, timeout=timeout) as r:
                    result.append(json.loads(r.read().decode("utf-8")))
            except Exception as e:
                result.append(e)
        t = threading.Thread(target=_fetch, daemon=True)
        t.start()
        t.join(timeout)
        if t.is_alive():
            log.warning(f"Delirius {path} timeout hard ({timeout}s) tentativa {attempt}/{attempts}")
        elif result and not isinstance(result[0], Exception):
            return result[0]
        else:
            err = result[0] if result else "sem resposta"
            log.warning(f"Delirius {path} falhou tentativa {attempt}/{attempts}: {err}")
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


def _yt_item_from_info(item: dict) -> dict | None:
    if not isinstance(item, dict):
        return None
    url = item.get("webpage_url") or item.get("url")
    video_id = item.get("id")
    if isinstance(url, str) and url.startswith("http"):
        final_url = url
    elif video_id:
        final_url = f"https://www.youtube.com/watch?v={video_id}"
    else:
        return None
    title = item.get("title") or ""
    author = item.get("uploader") or item.get("channel") or item.get("artist") or ""
    return {
        "url": final_url,
        "title": title,
        "name": title,
        "artist": author,
        "author": author,
        "duration": item.get("duration"),
        "source": "yt-dlp",
    }


def _youtube_search_local(query: str, *, prefix: str = "ytsearch5") -> list[dict]:
    query = re.sub(r"\s+", " ", str(query or "")).strip()
    if not query or YoutubeDL is None:
        return []
    opts = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "extract_flat": True,
        "socket_timeout": 12,
        "retries": 1,
        "noplaylist": True,
    }
    try:
        with YoutubeDL(opts) as ydl:
            info = ydl.extract_info(f"{prefix}:{query}", download=False)
    except Exception as e:
        log.warning(f"yt-dlp search falhou '{query}': {e}")
        return []
    entries = (info or {}).get("entries") or []
    out: list[dict] = []
    for entry in entries:
        item = _yt_item_from_info(entry)
        if item:
            out.append(item)
    return out


def _youtube_search(query: str, *, prefer_original: bool = True) -> dict | None:
    query = re.sub(r"\s+", " ", str(query or "")).strip()
    if not query:
        return None
    candidates = _youtube_search_local(query)
    if candidates:
        if prefer_original:
            for item in candidates:
                if not _looks_non_original(item):
                    return item
        return candidates[0]
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
    """Busca uma faixa pelo texto. Primeiro local via YouTube; Delirius só como fallback de busca."""
    query = _spotify_clean_query(query)
    if not query:
        return None
    candidates = _youtube_search_local(query)
    if candidates:
        if prefer_original:
            for item in candidates:
                if not _looks_non_original(item):
                    return item
        return candidates[0]
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


async def _baixar(url: str, ext: str, *, progress_cb=None) -> str | None:
    """Baixa o arquivo via streaming. progress_cb(pct: float) é chamado a cada chunk."""
    out = Path(tempfile.gettempdir()) / f"hyrule_dl_{int(time.time())}.{ext}"
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT_DL, follow_redirects=True) as client:
            async with client.stream("GET", url) as r:
                if r.status_code != 200:
                    return None
                total = int(r.headers.get("content-length", 0))
                downloaded = 0
                chunks: list[bytes] = []
                async for chunk in r.aiter_bytes(chunk_size=65536):
                    chunks.append(chunk)
                    downloaded += len(chunk)
                    if progress_cb and total:
                        await progress_cb(min(downloaded / total, 0.99))
                out.write_bytes(b"".join(chunks))
                return str(out)
    except Exception as e:
        log.warning(f"_baixar falhou: {e}")
        return None


async def _yt_dlp_download(url: str, ext: str, *, progress_cb=None) -> tuple[str | None, dict]:
    """Baixa YouTube localmente via yt-dlp. Retorna (arquivo, info)."""
    if YoutubeDL is None:
        return None, {}

    tmpdir = Path(tempfile.mkdtemp(prefix="hyrule_ytdlp_"))
    loop = asyncio.get_running_loop()

    def _hook(status: dict):
        if not progress_cb or status.get("status") != "downloading":
            return
        total = status.get("total_bytes") or status.get("total_bytes_estimate") or 0
        done = status.get("downloaded_bytes") or 0
        if total and done:
            pct = min(max(done / total, 0.0), 0.99)
            loop.call_soon_threadsafe(lambda: asyncio.create_task(progress_cb(pct)))

    if ext == "mp4":
        opts = {
            "format": "bestvideo[height<=360][ext=mp4]+bestaudio[ext=m4a]/best[height<=360][ext=mp4]/best[height<=360]/best",
            "merge_output_format": "mp4",
            "outtmpl": str(tmpdir / "download.%(ext)s"),
            "noplaylist": True,
            "quiet": True,
            "no_warnings": True,
            "noprogress": True,
            "socket_timeout": 20,
            "retries": 2,
            "progress_hooks": [_hook],
        }
    else:
        opts = {
            "format": "bestaudio/best",
            "outtmpl": str(tmpdir / "download.%(ext)s"),
            "noplaylist": True,
            "quiet": True,
            "no_warnings": True,
            "noprogress": True,
            "socket_timeout": 20,
            "retries": 2,
            "progress_hooks": [_hook],
            "postprocessors": [{
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "192",
            }],
        }

    def _run() -> tuple[str | None, dict]:
        with YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True) or {}
        files = sorted(
            (p for p in tmpdir.iterdir() if p.is_file() and p.suffix.lower() == f".{ext}"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        if files:
            return str(files[0]), info
        any_files = sorted((p for p in tmpdir.iterdir() if p.is_file()), key=lambda p: p.stat().st_mtime, reverse=True)
        return (str(any_files[0]), info) if any_files else (None, info)

    try:
        return await asyncio.to_thread(_run)
    except Exception as e:
        log.warning(f"yt-dlp download falhou {url}: {e}")
        return None, {}


async def _yt_dlp_media_download(url: str, *, progress_cb=None) -> tuple[str | None, dict]:
    """Baixa mídia genérica localmente via yt-dlp (Instagram, Twitter/X, etc.)."""
    if YoutubeDL is None:
        return None, {}

    tmpdir = Path(tempfile.mkdtemp(prefix="hyrule_ytdlp_"))
    loop = asyncio.get_running_loop()

    def _hook(status: dict):
        if not progress_cb or status.get("status") != "downloading":
            return
        total = status.get("total_bytes") or status.get("total_bytes_estimate") or 0
        done = status.get("downloaded_bytes") or 0
        if total and done:
            pct = min(max(done / total, 0.0), 0.99)
            loop.call_soon_threadsafe(lambda: asyncio.create_task(progress_cb(pct)))

    opts = {
        "format": "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
        "merge_output_format": "mp4",
        "outtmpl": str(tmpdir / "media.%(ext)s"),
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
        "socket_timeout": 20,
        "retries": 2,
        "progress_hooks": [_hook],
    }

    def _run() -> tuple[str | None, dict]:
        with YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True) or {}
        files = sorted(
            (p for p in tmpdir.iterdir() if p.is_file()),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        if files:
            return str(files[0]), info
        try:
            tmpdir.rmdir()
        except OSError:
            pass
        return None, info

    try:
        return await asyncio.to_thread(_run)
    except Exception as e:
        log.warning(f"yt-dlp media falhou {url}: {e}")
        try:
            tmpdir.rmdir()
        except OSError:
            pass
        return None, {}


def _spotify_oembed_title(url: str, timeout: int = 10) -> str:
    api_url = "https://open.spotify.com/oembed?" + urllib.parse.urlencode({"url": url})
    try:
        req = urllib.request.Request(api_url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            data = json.loads(r.read().decode("utf-8"))
        title = data.get("title")
        return title.strip() if isinstance(title, str) else ""
    except Exception as e:
        log.warning(f"Spotify oEmbed falhou: {e}")
        return ""


def _rm(path: str | None):
    """Remove o arquivo temporário após envio. Silencia FileNotFoundError (já apagado)."""
    if path:
        try:
            parent = Path(path).parent
            os.unlink(path)
            if parent.name.startswith("hyrule_ytdlp_"):
                try:
                    parent.rmdir()
                except OSError:
                    pass
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


# ── Barra de progresso ───────────────────────────────────────────────────────

def _bar(pct: float, width: int = 10) -> str:
    filled = round(min(max(pct, 0), 1) * width)
    return "🟩" * filled + "⬜" * (width - filled)

def _bar_text(pct: float, label: str = "") -> str:
    suffix = f" {label}" if label else ""
    return f"{_bar(pct)} {int(pct * 100)}%{suffix}"


class _ProgressMsg:
    """Mensagem de texto editável usada como barra de progresso no WhatsApp."""

    def __init__(self, ctx: MessageContext, msg_id: str):
        self._ctx    = ctx
        self._msg_id = msg_id
        self._bucket = -1  # 0-10; atualiza a cada ~10%

    async def update(self, pct: float, label: str = ""):
        if not self._msg_id or self._ctx.client is None:
            return
        bucket = int(min(max(pct, 0), 1.0) * 10)  # 0-10 inclusive; 1.0 → 10
        if bucket <= self._bucket:  # nunca retrocede
            return
        self._bucket = bucket
        try:
            await self._ctx.client.edit_message(
                self._ctx.chat_jid, self._msg_id, _bar_text(pct, label)
            )
        except Exception:
            pass

    async def animate_bg(self, start: float, end: float, label: str, total_secs: float = 55.0):
        """Anima a barra de start até end ao longo de total_secs. Rodar via create_task; cancelável."""
        n = max(1, int((end - start) * 10))
        per_step = total_secs / n
        cur = start
        step = (end - start) / n
        for _ in range(n):
            await asyncio.sleep(per_step)
            cur = min(cur + step, end)
            await self.update(cur, label)

    async def delete(self):
        if not self._msg_id or self._ctx.client is None:
            return
        try:
            await self._ctx.client.delete_message(self._ctx.chat_jid, self._msg_id)
        except Exception:
            pass


async def _progress_start(ctx: MessageContext, label: str = "🔍 buscando...") -> "_ProgressMsg | None":
    """Envia a mensagem inicial de progresso e retorna o controlador."""
    if ctx.client is None:
        return None
    try:
        resp = await ctx.client.send_message(ctx.chat_jid, _bar_text(0, label))
        msg_id = getattr(resp, "ID", "") or getattr(resp, "ServerID", "")
        return _ProgressMsg(ctx, msg_id) if msg_id else None
    except Exception:
        return None


# ── Handlers por plataforma ───────────────────────────────────────────────────

async def _yt(ctx: MessageContext, url: str, modo: str, caption_extra: str = ""):
    """Baixa áudio (MP3) ou vídeo (MP4) de um link do YouTube localmente."""
    prog = await _progress_start(ctx, "🔍 buscando link...")

    if modo == "mp4":
        ext, caption = "mp4", "📹 vídeo do YouTube"
    else:
        ext, caption = "mp3", "🎵 áudio do YouTube"

    if caption_extra:
        caption = f"{caption}\n{caption_extra}"

    await prog.update(0.2, "⬇️ baixando...") if prog else None

    # Animação em background — avança independente do CDN ter content-length
    _anim = asyncio.create_task(prog.animate_bg(0.21, 0.88, "⬇️ baixando...", 55)) if prog else None

    async def on_dl(pct: float):
        # Progresso real (quando CDN envia content-length) tem prioridade via bucket <=
        await prog.update(0.2 + pct * 0.7, "⬇️ baixando...") if prog else None

    path, info = await _yt_dlp_download(url, ext, progress_cb=on_dl)
    if path and info.get("title"):
        caption = f"{caption}\n_{info.get('title')}_"

    if _anim:
        _anim.cancel()
    if not path:
        if prog:
            await prog.delete()
        await ctx.reply("não consegui baixar esse arquivo agora")
        return

    await prog.update(0.95, "🎵 convertendo...") if prog else None
    try:
        if ext == "mp3":
            await _send_audio_track(ctx, path, caption=caption)
        else:
            await ctx.reply_media(path, caption=caption)
        if prog:
            await prog.update(1.0, "✅ pronto!")
    finally:
        _rm(path)


async def _spotify(ctx: MessageContext, url: str, *, fallback_query: str = "",
                   prefer_original: bool = True, prog: "_ProgressMsg | None" = None):
    """Baixa música como MP3. Spotify vira busca local no YouTube."""
    await prog.update(0.15, "🔍 buscando link...") if prog else None

    source_url = url
    yt_url = url if _RE_YT.search(url or "") else ""
    spotify_title = ""
    if not yt_url and _RE_SPOTIFY.search(url or ""):
        spotify_title = await asyncio.to_thread(_spotify_oembed_title, url)
        search_query = fallback_query or spotify_title
        result = _spotify_search(search_query, prefer_original=prefer_original) if search_query else None
        yt_url = (result or {}).get("url") or ""
        if result:
            fallback_query = " ".join(str(x) for x in (
                (result or {}).get("title") or (result or {}).get("name") or "",
                (result or {}).get("artist") or (result or {}).get("author") or "",
            ) if x).strip() or fallback_query

    if yt_url:
        caption_title = fallback_query or spotify_title or "Spotify"
        caption = f"🎵 {caption_title}".strip()
        if _RE_SPOTIFY.search(source_url or ""):
            caption = f"{caption}\nSpotify: {source_url}"
        else:
            caption = f"{caption}\nYouTube: {yt_url}"

        await prog.update(0.25, "⬇️ baixando...") if prog else None
        _anim = asyncio.create_task(prog.animate_bg(0.26, 0.88, "⬇️ baixando...", 55)) if prog else None

        async def on_local_dl(pct: float):
            await prog.update(0.25 + pct * 0.65, "⬇️ baixando...") if prog else None

        path, info = await _yt_dlp_download(yt_url, "mp3", progress_cb=on_local_dl)
        if _anim:
            _anim.cancel()
        if path:
            title = info.get("title") or caption_title
            if title and title not in caption:
                caption = f"🎵 {title}\n" + ("\n".join(caption.splitlines()[1:]) if "\n" in caption else f"YouTube: {yt_url}")
            await prog.update(0.95, "🎵 convertendo...") if prog else None
            try:
                await _send_audio_track(ctx, path, caption=caption)
                if prog:
                    await prog.update(1.0, "✅ pronto!")
            finally:
                _rm(path)
            return
        if not _RE_SPOTIFY.search(source_url or ""):
            if prog:
                await prog.delete()
            await ctx.reply("não consegui baixar esse áudio agora")
            return
    if prog:
        await prog.delete()
    await ctx.reply("não consegui resolver essa música localmente agora")


async def _spotify_query(ctx: MessageContext, query: str, *, context: str = ""):
    """Busca a faixa pelo texto, refinando a consulta com LLM quando possível."""
    prog = await _progress_start(ctx, "🔍 buscando no Spotify...")

    prefer_original = not _allows_alternate_version(query)
    candidates = _spotify_search_candidates(query, context=context)

    await prog.update(0.1, "🔍 buscando no Spotify...") if prog else None

    result = None
    used_query = ""
    for candidate in candidates:
        result = _spotify_search(candidate, prefer_original=prefer_original)
        if result:
            used_query = candidate
            break

    url = (result or {}).get("url")
    if not url:
        if prog:
            await prog.delete()
        await ctx.reply("não achei essa música no Spotify")
        return

    title  = (result or {}).get("title") or (result or {}).get("name") or ""
    artist = (result or {}).get("artist") or (result or {}).get("artists") or ""
    if isinstance(artist, list):
        artist = ", ".join(str(a) for a in artist)
    if used_query:
        log.info(f"Spotify busca '{query}' -> '{used_query}' => {title} — {artist}")

    fallback_query = " ".join(str(x) for x in (title, artist) if x).strip() or used_query or query
    await _spotify(ctx, url, fallback_query=fallback_query, prefer_original=prefer_original, prog=prog)


async def _instagram(ctx: MessageContext, url: str):
    """Baixa foto ou vídeo de um post/reel do Instagram localmente; Delirius é fallback."""
    prog = await _progress_start(ctx, "🔍 buscando mídia...")
    await prog.update(0.2, "⬇️ baixando...") if prog else None

    async def on_local_dl(pct: float):
        await prog.update(0.2 + pct * 0.7, "⬇️ baixando...") if prog else None

    path, info = await _yt_dlp_media_download(url, progress_cb=on_local_dl)
    if path:
        caption = "📸 Instagram"
        title = (info or {}).get("title") or ""
        if title:
            caption = f"{caption}\n_{title}_"
        try:
            await ctx.reply_media(path, caption=caption)
            await prog.update(1.0, "✅ pronto!") if prog else None
        finally:
            _rm(path)
        return

    data = (
        _get_json("/download/instagramv2", {"url": url})
        or _get_json("/download/instagram", {"url": url})
    )
    if not data:
        if prog:
            await prog.delete()
        await ctx.reply("API fora agora")
        return

    media_url = _extract_url(data)
    if not media_url:
        if prog:
            await prog.delete()
        await ctx.reply(f"não achei mídia 🌀\n`{str(data)[:200]}`")
        return

    is_video = any(k in str(data).lower() for k in ("video", "mp4", "reel"))
    ext = "mp4" if is_video else "jpg"
    path = await _baixar(media_url, ext)
    if not path:
        if prog:
            await prog.delete()
        await ctx.reply("não consegui baixar")
        return
    try:
        await ctx.reply_media(path, caption="📸 Instagram")
        await prog.update(1.0, "✅ pronto!") if prog else None
    finally:
        _rm(path)


async def _twitter(ctx: MessageContext, url: str):
    """Baixa o vídeo de um tweet/post do Twitter/X localmente; Delirius é fallback."""
    prog = await _progress_start(ctx, "🔍 buscando mídia...")
    await prog.update(0.2, "⬇️ baixando...") if prog else None

    async def on_local_dl(pct: float):
        await prog.update(0.2 + pct * 0.7, "⬇️ baixando...") if prog else None

    path, info = await _yt_dlp_media_download(url, progress_cb=on_local_dl)
    if path:
        caption = "🐦 Twitter/X"
        title = (info or {}).get("title") or ""
        if title:
            caption = f"{caption}\n_{title}_"
        try:
            await ctx.reply_media(path, caption=caption)
            await prog.update(1.0, "✅ pronto!") if prog else None
        finally:
            _rm(path)
        return

    data = _get_json("/download/twitterdl", {"url": url})
    if not data:
        if prog:
            await prog.delete()
        await ctx.reply("API fora agora")
        return

    media_url = _extract_url(data)
    if not media_url:
        if prog:
            await prog.delete()
        await ctx.reply(f"não achei mídia 🌀\n`{str(data)[:200]}`")
        return

    path = await _baixar(media_url, "mp4")
    if not path:
        if prog:
            await prog.delete()
        await ctx.reply("não consegui baixar")
        return
    try:
        await ctx.reply_media(path, caption="🐦 Twitter/X")
        await prog.update(1.0, "✅ pronto!") if prog else None
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
        prog = await _progress_start(ctx, "🔍 buscando link...")
        await _spotify(ctx, url, prog=prog)
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
