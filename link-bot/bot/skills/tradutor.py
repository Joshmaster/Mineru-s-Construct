"""Skill: tradutor - via MyMemory API (gratuita, sem key, 5000 chars/dia)."""

import re
import httpx
from bot.core.router import Skill
from bot.core.context import MessageContext


# Mapeia palavras comuns pra códigos de idioma
LANGS = {
    "ingles": "en", "inglês": "en", "english": "en", "en": "en",
    "espanhol": "es", "espanol": "es", "spanish": "es", "es": "es",
    "frances": "fr", "francês": "fr", "french": "fr", "fr": "fr",
    "alemao": "de", "alemão": "de", "german": "de", "de": "de",
    "italiano": "it", "italian": "it", "it": "it",
    "japones": "ja", "japonês": "ja", "japanese": "ja", "ja": "ja",
    "chines": "zh", "chinês": "zh", "chinese": "zh", "zh": "zh",
    "coreano": "ko", "korean": "ko", "ko": "ko",
    "russo": "ru", "russian": "ru", "ru": "ru",
    "arabe": "ar", "árabe": "ar", "arabic": "ar", "ar": "ar",
    "portugues": "pt", "português": "pt", "portuguese": "pt", "pt": "pt",
}


async def handle(ctx: MessageContext):
    args = ctx.args_text.strip()
    if not args:
        await ctx.reply(
            "O que traduzir, parceiro? 🌐\n"
            "_Ex: 'traduz pra inglês: bom dia'_\n"
            "_Ex: 'traduz pro espanhol: tudo bem?'_"
        )
        return

    # Padrão: "pra <idioma>:?\s*<texto>" ou "para <idioma>:?\s*<texto>"
    m = re.search(
        r"(?:pra|para|pro|to|em)\s+(\w+)\s*[:.]?\s*(.+)",
        args, re.IGNORECASE | re.DOTALL
    )

    target_lang = "en"  # default inglês
    text = args

    if m:
        lang_word = m.group(1).lower()
        if lang_word in LANGS:
            target_lang = LANGS[lang_word]
            text = m.group(2).strip()

    if not text:
        await ctx.reply("E o texto pra traduzir, parceiro? 🌐")
        return

    # Limita pra não estourar o quota free
    if len(text) > 1000:
        await ctx.reply("Texto longo demais 📜. Limita em ~1000 caracteres.")
        return

    # Source: detecta se já é PT, senão assume inglês
    # Heurística simples: se tem ã, ç, õ, é, etc → PT
    has_pt_chars = bool(re.search(r"[ãáâàçéêíóôõúüÃÁÂÀÇÉÊÍÓÔÕÚÜ]", text))
    source = "pt" if has_pt_chars else "auto"
    if source == "auto":
        # Sem chars típicos PT, tenta inferir: se target é pt, source é en
        source = "en" if target_lang == "pt" else "pt"

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.get(
                "https://api.mymemory.translated.net/get",
                params={
                    "q": text,
                    "langpair": f"{source}|{target_lang}"
                }
            )
            if r.status_code != 200:
                await ctx.reply("O escriba não respondeu 🌀")
                return
            data = r.json()
    except Exception as e:
        await ctx.reply(f"Portal de tradução travou: {e}")
        return

    response_data = data.get("responseData", {})
    translated = response_data.get("translatedText", "")

    if not translated:
        await ctx.reply("Não consegui traduzir essa passagem 📜")
        return

    # Resposta
    msg = (
        f"📜 *Tradução* ({source} → {target_lang})\n"
        f"─────────────────\n"
        f"_{text[:200]}_\n"
        f"⬇️\n"
        f"*{translated}*"
    )
    await ctx.reply(msg)


SKILL = Skill(
    name="tradutor",
    description="*traduz pra <idioma>: <texto>* — escriba poliglota",
    triggers=["!trad", "traduz", "traduzir", "traducao", "tradução", "translate"],
    handler=handle,
    category="util",
)
