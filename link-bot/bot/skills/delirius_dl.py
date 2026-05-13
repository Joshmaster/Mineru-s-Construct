"""Downloads via Delirius Store API.

Suporta: YouTube (MP3/MP4), Spotify, Instagram, Twitter/X.
Ativa por comando explícito (!yt, !spot, !ig, !x, !baixa)
ou por detecção automática de URL no texto (main.py injeta antes do router).
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import tempfile
import time
import urllib.parse
import urllib.request
from pathlib import Path

import httpx

from bot.core.router import Skill
from bot.core.context import MessageContext

BASE = "https://api.delirius.store"
TIMEOUT_API = 45   # timeout da chamada à API Delirius
TIMEOUT_DL  = 90   # timeout do download do arquivo

# Regex de URLs suportadas — usados tanto aqui quanto em main.py via detect_url()
_RE_YT      = re.compile(r"https?://(?:www\.)?(?:youtube\.com/(?:watch\?[^\s]*v=|shorts/)|youtu\.be/)[\w\-]+(?:[^\s]*)?")
_RE_SPOTIFY = re.compile(r"https?://open\.spotify\.com/(?:track|album|playlist)/[\w]+")
_RE_IG      = re.compile(r"https?://(?:www\.)?instagram\.com/(?:p|reel|reels)/[\w\-]+")
_RE_TW      = re.compile(r"https?://(?:www\.)?(?:twitter\.com|x\.com)/\w+/status/\d+")


# ── Helpers ───────────────────────────────────────────────────────────────────

def _get_json(path: str, params: dict, timeout: int = TIMEOUT_API) -> dict | None:
    """Faz GET na Delirius API e retorna o JSON. Retorna None se falhar."""
    url = f"{BASE}{path}?" + urllib.parse.urlencode(params)
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "HyruleBot/1.0"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8"))
    except Exception:
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


# ── Handlers por plataforma ───────────────────────────────────────────────────

async def _yt(ctx: MessageContext, url: str, modo: str):
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

    path = await _baixar(media_url, ext)
    if not path:
        await ctx.reply("baixei o link mas não consegui salvar o arquivo")
        return
    try:
        await ctx.reply_media(path, caption=caption)
    finally:
        _rm(path)


async def _spotify(ctx: MessageContext, url: str):
    """Baixa a faixa de um link do Spotify como MP3 via Delirius.
    Monta a legenda com título e artista se a API retornar esses dados.
    """
    data = _get_json("/download/spotifydl", {"url": url})
    if not data:
        await ctx.reply("API fora agora")
        return

    media_url = _extract_url(data)
    if not media_url:
        await ctx.reply(f"resposta inesperada 🌀\n`{str(data)[:200]}`")
        return

    title  = _extract_title(data)
    artist = data.get("artists") or data.get("artist") or ""
    if isinstance(artist, list):
        artist = ", ".join(str(a) for a in artist)
    caption = f"🎵 {title} — {artist}".strip(" —") if title else "🎵 Spotify"

    path = await _baixar(media_url, "mp3")
    if not path:
        await ctx.reply("não consegui baixar o arquivo")
        return
    try:
        await ctx.reply_media(path, caption=caption)
    finally:
        _rm(path)


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
        await ctx.reply(
            "manda o link junto 🔗\n"
            "_aceito: YouTube, Spotify, Instagram, Twitter/X_\n\n"
            "exemplos:\n"
            "`!yt https://youtu.be/...`\n"
            "`!spot https://open.spotify.com/track/...`\n"
            "`!ig https://instagram.com/reel/...`\n"
            "`!x https://x.com/.../status/...`"
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
        "*!yt <link>* — áudio do YouTube (MP3)\n"
        "*!ytv <link>* — vídeo do YouTube (MP4)\n"
        "*!spot <link>* — baixar do Spotify\n"
        "*!ig <link>* — baixar do Instagram\n"
        "*!x <link>* — baixar do Twitter/X"
    ),
    triggers=[
        "!baixa", "!dl", "!download",
        "!yt", "!ytmp3",
        "!ytv", "!ytmp4",
        "!spotify", "!spot",
        "!ig", "!insta", "!instagram",
        "!x", "!twitter",
    ],
    handler=handle,
    category="midia",
    priority=110,
)
