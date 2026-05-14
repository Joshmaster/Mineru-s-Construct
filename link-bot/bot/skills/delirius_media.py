"""Skills de mídia via Delirius Store API.

!fala (!voz, !tts)     — converte texto em áudio via Google TTS
!tt / !attp            — cria sticker com texto escrito (estático ou animado)
!gif                   — busca e envia GIF do Tenor
!print (!screenshot)   — tira screenshot de qualquer site
!melhora (!upscale)    — melhora qualidade ou resolução de imagem

Todas as skills usam api.delirius.store, sem chave de API.
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

BASE    = "https://api.delirius.store"
TIMEOUT = 45


def _get_json(path: str, params: dict, timeout: int = TIMEOUT) -> dict | None:
    """Faz GET na Delirius API e retorna o JSON. Retorna None se falhar."""
    url = f"{BASE}{path}?" + urllib.parse.urlencode(params)
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "HyruleBot/1.0"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8"))
    except Exception:
        return None


def _extract_url(data) -> str | None:
    """Percorre recursivamente a resposta procurando a primeira URL de mídia.
    Tenta chaves comuns (url, link, audio, image, gif, screenshot…) e dicts aninhados.
    """
    if isinstance(data, str) and data.startswith("http"):
        return data
    if isinstance(data, list):
        for item in data:
            u = _extract_url(item)
            if u:
                return u
        return None
    if not isinstance(data, dict):
        return None
    for key in ("url", "link", "download", "audio", "image", "gif", "video", "media", "result", "screenshot"):
        val = data.get(key)
        if isinstance(val, str) and val.startswith("http"):
            return val
    for key in ("data", "result"):
        nested = data.get(key)
        if nested:
            u = _extract_url(nested)
            if u:
                return u
    return None


async def _baixar(url: str, ext: str, timeout: int = 60) -> str | None:
    """Baixa o arquivo da URL para um arquivo temporário e retorna o caminho local.
    Retorna None se o download falhar.
    """
    out = Path(tempfile.gettempdir()) / f"hyrule_media_{int(time.time())}.{ext}"
    try:
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
            r = await client.get(url)
            if r.status_code == 200:
                out.write_bytes(r.content)
                return str(out)
    except Exception:
        pass
    return None


def _rm(path: str | None):
    """Remove o arquivo temporário após envio. Silencia FileNotFoundError."""
    if path:
        try:
            os.unlink(path)
        except FileNotFoundError:
            pass


# ── vozes edge-tts por idioma (Microsoft Neural) ─────────────────────────────
_EDGE_VOICES = {
    "pt": "en-US-BrianMultilingualNeural",
    "en": "en-US-AndrewMultilingualNeural",
    "es": "es-ES-AlvaroNeural",
    "fr": "fr-FR-RemyMultilingualNeural",
    "de": "de-DE-FlorianMultilingualNeural",
    "it": "it-IT-GiuseppeMultilingualNeural",
    "ja": "ja-JP-KeitaNeural",
    "ko": "ko-KR-HyunsuMultilingualNeural",
}

# ── !fala — TTS via edge-tts (Microsoft Neural) ───────────────────────────────

async def handle_fala(ctx: MessageContext):
    """Converte texto em áudio usando vozes neurais da Microsoft Edge (edge-tts).
    Voz padrão PT-BR: ThalitaMultilingualNeural (alta qualidade).
    Para outro idioma, prefixar com código: 'en: hello', 'es: hola'.
    Para voz específica: 'voz AntonioNeural: texto aqui'.
    Limite de 500 caracteres. Envia como nota de voz.
    """
    text = ctx.args_text.strip()
    if not text:
        await ctx.reply(
            "o que eu falo? 🎙️\n"
            "`!fala olá, mundo`\n"
            "`!fala en: hello world` — inglês\n"
            "`!fala es: hola mundo` — espanhol\n"
            "`!fala voz AntonioNeural: texto` — voz específica"
        )
        return

    import asyncio, subprocess
    import edge_tts

    # seleção de voz específica: "voz NomeVoz: texto"
    voice = _EDGE_VOICES["pt"]
    m_voz = re.match(r"^voz\s+(\S+)\s*:\s*", text, re.IGNORECASE)
    if m_voz:
        voice = m_voz.group(1)
        if not voice.endswith("Neural"):
            voice += "Neural"
        text = text[m_voz.end():].strip()
    else:
        m = re.match(r"^(pt|en|es|fr|de|it|ja|ko)\s*:\s*", text, re.IGNORECASE)
        if m:
            voice = _EDGE_VOICES.get(m.group(1).lower(), voice)
            text = text[m.end():].strip()

    if len(text) > 500:
        await ctx.reply("texto longo demais, máximo 500 caracteres")
        return

    await ctx.typing()

    # Corrige o texto via LLM antes de converter; mantém original se LLM falhar
    try:
        from bot.core.llm import rewrite_for_tts
        improved = await asyncio.get_event_loop().run_in_executor(None, rewrite_for_tts, text)
        if improved:
            text = improved
    except Exception:
        pass

    mp3 = Path(tempfile.gettempdir()) / f"hyrule_tts_{int(time.time())}.mp3"
    ogg = mp3.with_suffix(".ogg")
    try:
        communicate = edge_tts.Communicate(text, voice)
        await communicate.save(str(mp3))
        await asyncio.get_event_loop().run_in_executor(None, lambda: subprocess.run(
            ["ffmpeg", "-y", "-i", str(mp3), "-c:a", "libopus", "-b:a", "32k", str(ogg)],
            capture_output=True, check=True,
        ))
    except Exception as e:
        await ctx.reply(f"erro ao gerar áudio: {e}")
        _rm(str(mp3)); _rm(str(ogg))
        return

    try:
        await ctx.reply_media(str(ogg))
    finally:
        _rm(str(mp3)); _rm(str(ogg))


SKILL_FALA = Skill(
    name="delirius_fala",
    description="*!fala <texto>* — converte texto em áudio (pt/en/es/...)",
    triggers=["!fala", "!voz", "!tts", "!diz", "!falar"],
    handler=handle_fala,
    category="util",
    priority=100,
)


# ── !tt / !attp — sticker com texto ──────────────────────────────────────────

async def handle_stickertext(ctx: MessageContext):
    """Cria um sticker com o texto escrito via Delirius Canvas.
    !tt  → sticker estático PNG via /canvas/ttp
    !attp → sticker animado GIF via /canvas/attp (mais lento, ~8s)
    Tenta enviar como sticker nativo do WhatsApp; cai pra imagem normal se falhar.
    """
    text = ctx.args_text.strip()
    if not text:
        await ctx.reply(
            "qual texto pro sticker? ✍️\n"
            "`!tt seu texto aqui`  — estático\n"
            "`!attp seu texto aqui`  — animado"
        )
        return

    animado = ctx.raw_text.lower().startswith("!attp")
    await ctx.typing()

    endpoint = "/canvas/attp" if animado else "/canvas/ttp"
    ext = "gif" if animado else "png"
    api_url = f"{BASE}{endpoint}?" + urllib.parse.urlencode({"text": text})

    path = await _baixar(api_url, ext, timeout=60)
    if not path:
        await ctx.reply("não consegui baixar o sticker")
        return
    try:
        try:
            await ctx.reply_media(path, as_sticker=True)
        except Exception:
            await ctx.reply_media(path, caption=text[:60])
    finally:
        _rm(path)


SKILL_TT = Skill(
    name="delirius_tt",
    description=(
        "*!tt <texto>* — sticker com texto (estático)\n"
        "*!attp <texto>* — sticker com texto (animado)"
    ),
    triggers=["!tt", "!ttp", "!attp", "!stickertext"],
    handler=handle_stickertext,
    category="midia",
    priority=105,
)


# ── !gif — busca GIF no Tenor ─────────────────────────────────────────────────

async def handle_gif(ctx: MessageContext):
    """Busca um GIF no Tenor via Delirius (/search/tenor) e envia como mídia.
    Retorna o primeiro resultado encontrado para o termo buscado.
    """
    query = ctx.args_text.strip()
    if not query:
        await ctx.reply("o que buscar? ex: `!gif feliz`")
        return

    await ctx.typing()
    data = _get_json("/search/tenor", {"q": query})
    if not data:
        await ctx.reply("API fora agora")
        return

    gif_url = _extract_url(data)
    if not gif_url:
        await ctx.reply(f"não achei GIF de `{query}` 🌀")
        return

    path = await _baixar(gif_url, "gif")
    if not path:
        await ctx.reply("não consegui baixar o GIF")
        return
    try:
        await ctx.reply_media(path, caption=f"🎞️ {query}")
    finally:
        _rm(path)


SKILL_GIF = Skill(
    name="delirius_gif",
    description="*!gif <busca>* — busca GIF no Tenor",
    triggers=["!gif", "!giff"],
    handler=handle_gif,
    category="midia",
    priority=100,
)


# ── !print — screenshot de site ───────────────────────────────────────────────

async def handle_print(ctx: MessageContext):
    """Tira screenshot de qualquer URL via Delirius (/tools/ssweb) e envia como imagem.
    Adiciona 'https://' automaticamente se o usuário omitir o protocolo.
    """
    url = ctx.args_text.strip()
    if not url:
        await ctx.reply("qual site? ex: `!print https://google.com`")
        return
    if not url.startswith("http"):
        url = "https://" + url

    await ctx.typing()
    data = _get_json("/tools/ssweb", {"url": url}, timeout=60)
    if not data:
        await ctx.reply("API fora agora")
        return

    img_url = _extract_url(data)
    if not img_url:
        await ctx.reply(f"não consegui tirar o print 🌀\n`{str(data)[:150]}`")
        return

    path = await _baixar(img_url, "jpg")
    if not path:
        await ctx.reply("não consegui baixar o print")
        return
    try:
        await ctx.reply_media(path, caption=f"🖥️ {url[:60]}")
    finally:
        _rm(path)


SKILL_PRINT = Skill(
    name="delirius_print",
    description="*!print <url>* — screenshot de qualquer site",
    triggers=["!print", "!screenshot", "!screen"],
    handler=handle_print,
    category="util",
    priority=100,
)


# ── !melhora / !upscale — enhance/upscale de imagem ──────────────────────────

async def handle_melhora(ctx: MessageContext):
    """Melhora a qualidade ou aumenta a resolução de uma imagem via Delirius IA.
    !melhora → /ia/enhance (melhora nitidez, iluminação, detalhes)
    !upscale  → /ia/upscale (aumenta resolução, escala 4x)
    Requer URL pública da imagem nos args (não aceita arquivo anexado diretamente,
    pois a API Delirius precisa buscar a imagem pela URL).
    """
    text = ctx.args_text.strip()
    media_path = ctx.media_path
    img_url = None

    if media_path and os.path.exists(media_path):
        await ctx.reply("preciso de uma URL pública da imagem. Manda o link direto da foto 🔗")
        return
    elif text.startswith("http"):
        img_url = text
    else:
        await ctx.reply(
            "manda o link direto da imagem junto 🔗\n"
            "`!melhora https://exemplo.com/foto.jpg`\n"
            "_ou !upscale para aumentar resolução_"
        )
        return

    await ctx.typing()

    norm = ctx.raw_text.lower()
    endpoint = "/ia/upscale" if ("upscale" in norm or "resolucao" in norm or "resolução" in norm) else "/ia/enhance"

    data = _get_json(endpoint, {"image": img_url, "scale": "4"})
    if not data:
        await ctx.reply("API fora agora")
        return

    result_url = _extract_url(data)
    if not result_url:
        await ctx.reply(f"não recebi imagem melhorada 🌀\n`{str(data)[:150]}`")
        return

    path = await _baixar(result_url, "jpg")
    if not path:
        await ctx.reply("não consegui baixar a imagem")
        return
    try:
        await ctx.reply_media(path, caption="✨ imagem melhorada")
    finally:
        _rm(path)


SKILL_MELHORA = Skill(
    name="delirius_melhora",
    description=(
        "*!melhora <url>* — melhora qualidade da imagem (enhance)\n"
        "*!upscale <url>* — aumenta resolução da imagem"
    ),
    triggers=["!melhora", "!enhance", "!upscale", "!melhorar"],
    handler=handle_melhora,
    category="midia",
    priority=100,
)

# O skill loader procura SKILL (único ou lista)
SKILL = [SKILL_FALA, SKILL_TT, SKILL_GIF, SKILL_PRINT, SKILL_MELHORA]
