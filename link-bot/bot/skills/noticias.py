"""Skill: notícias - manchetes via RSS (G1, BBC Brasil)."""

import re
import httpx
from xml.etree import ElementTree as ET
from bot.core.router import Skill
from bot.core.context import MessageContext


FEEDS = {
    "geral": [
        ("G1", "https://g1.globo.com/rss/g1/"),
    ],
    "tecnologia": [
        ("G1 Tecnologia", "https://g1.globo.com/rss/g1/tecnologia/"),
    ],
    "economia": [
        ("G1 Economia", "https://g1.globo.com/rss/g1/economia/"),
    ],
    "mundo": [
        ("G1 Mundo", "https://g1.globo.com/rss/g1/mundo/"),
        ("BBC Brasil", "https://feeds.bbci.co.uk/portuguese/rss.xml"),
    ],
}


def _strip_html(text: str) -> str:
    return re.sub(r"<[^>]+>", "", text or "").strip()


async def _fetch_feed(url: str, max_items: int = 5):
    try:
        async with httpx.AsyncClient(
            timeout=10, follow_redirects=True,
            headers={"User-Agent": "Mozilla/5.0"}
        ) as client:
            r = await client.get(url)
            if r.status_code != 200:
                return []
            root = ET.fromstring(r.text)
            items = []
            for item in root.iter("item"):
                title = item.findtext("title", default="").strip()
                title = _strip_html(title)
                link = item.findtext("link", default="").strip()
                if title:
                    items.append((title, link))
                if len(items) >= max_items:
                    break
            return items
    except Exception:
        return []


async def handle(ctx: MessageContext):
    args = ctx.args_text.lower().strip()

    # Detecta categoria
    categoria = "geral"
    for cat in FEEDS.keys():
        if cat in args:
            categoria = cat
            break

    feeds = FEEDS[categoria]
    todas = []
    for nome, url in feeds:
        items = await _fetch_feed(url, max_items=4)
        for title, link in items:
            todas.append((nome, title, link))
        if len(todas) >= 6:
            break

    if not todas:
        await ctx.reply(
            "Os corvos mensageiros não trouxeram notícias hoje 🌀.\n"
            "Tenta de novo daqui pouco."
        )
        return

    cat_nome = {
        "geral": "📰 Manchetes do Reino",
        "tecnologia": "💻 Notícias de Tecnologia",
        "economia": "💰 Notícias de Economia",
        "mundo": "🌍 Notícias do Mundo",
    }.get(categoria, "📰 Notícias")

    lines = [f"*{cat_nome}*", "─────────────────"]
    for fonte, titulo, link in todas[:6]:
        lines.append(f"• *[{fonte}]* {titulo}")

    lines.append("\n_Categorias: tecnologia, economia, mundo_")
    await ctx.reply("\n".join(lines))


SKILL = Skill(
    name="noticias",
    description="*notícias* / *notícias tecnologia* — manchetes do dia",
    triggers=["!news", "noticias", "notícias", "manchetes", "news", "novidades"],
    handler=handle,
    category="info",
)
