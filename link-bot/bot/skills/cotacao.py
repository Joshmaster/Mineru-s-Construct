"""Skill: cotação - moedas e cripto via AwesomeAPI (gratuita, sem key)."""

import re
import httpx
from bot.core.router import Skill
from bot.core.context import MessageContext


PARES_COMUNS = {
    "dolar": "USD-BRL",
    "dólar": "USD-BRL",
    "usd": "USD-BRL",
    "euro": "EUR-BRL",
    "eur": "EUR-BRL",
    "libra": "GBP-BRL",
    "gbp": "GBP-BRL",
    "iene": "JPY-BRL",
    "jpy": "JPY-BRL",
    "peso argentino": "ARS-BRL",
    "ars": "ARS-BRL",
    "bitcoin": "BTC-BRL",
    "btc": "BTC-BRL",
    "ethereum": "ETH-BRL",
    "eth": "ETH-BRL",
}


async def handle(ctx: MessageContext):
    args = ctx.args_text.lower().strip()

    # Detecta par
    pair = None
    for k, v in PARES_COMUNS.items():
        if k in args:
            pair = v
            break

    # Se não detectou, mostra os principais
    if pair is None:
        if not args:
            pair = "USD-BRL,EUR-BRL,BTC-BRL"
        else:
            await ctx.reply(
                "Qual moeda consultar nos mercadores, parceiro? 💰\n"
                "_Ex: 'cotação dólar'_, _'bitcoin'_, _'euro'_"
            )
            return

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(f"https://economia.awesomeapi.com.br/last/{pair}")
            if r.status_code != 200:
                await ctx.reply("Os mercadores não responderam. 🌀")
                return
            data = r.json()
    except Exception as e:
        await ctx.reply(f"O portal dos mercadores travou: {e}")
        return

    lines = ["💰 *Mercadores de Hyrule* 💰", "─────────────────"]
    for key, info in data.items():
        nome = info.get("name", key)
        preco = float(info.get("bid", 0))
        var = info.get("pctChange", "0")
        try:
            var_f = float(var)
            seta = "📈" if var_f > 0 else ("📉" if var_f < 0 else "➡️")
        except Exception:
            seta = "➡️"
            var_f = 0

        # Formato de preço: BTC tem casas, BRL com vírgula
        if preco >= 1000:
            preco_fmt = f"R$ {preco:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
        else:
            preco_fmt = f"R$ {preco:.4f}".replace(".", ",")

        lines.append(f"{seta} *{nome}*: {preco_fmt} ({var_f:+.2f}%)")

    await ctx.reply("\n".join(lines))


SKILL = Skill(
    name="cotacao",
    description="*cotação <moeda>* — consultar mercadores",
    triggers=["cotacao", "cotação", "dolar", "dólar", "euro", "bitcoin",
              "moeda", "cambio", "câmbio"],
    handler=handle,
    category="info",
)
