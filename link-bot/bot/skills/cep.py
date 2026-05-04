"""Skill: CEP - busca endereço via ViaCEP (gratuita, sem key)."""

import re
import httpx
from bot.core.router import Skill
from bot.core.context import MessageContext


async def handle(ctx: MessageContext):
    args = ctx.args_text.strip()

    # Extrai CEP (8 dígitos)
    m = re.search(r"\d{5}[-\s]?\d{3}", args)
    if not m:
        # Tenta sequência de 8 dígitos
        m = re.search(r"\d{8}", args)
    if not m:
        await ctx.reply(
            "Qual CEP, parceiro? 📍\n"
            "_Ex: 'CEP 90010-150'_"
        )
        return

    cep_clean = re.sub(r"\D", "", m.group(0))
    if len(cep_clean) != 8:
        await ctx.reply("CEP precisa de 8 dígitos, parceiro. 🗺️")
        return

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(f"https://viacep.com.br/ws/{cep_clean}/json/")
            if r.status_code != 200:
                await ctx.reply("O cartógrafo não respondeu. 🌀")
                return
            data = r.json()
    except Exception as e:
        await ctx.reply(f"O portal travou: {e}")
        return

    if data.get("erro"):
        await ctx.reply(f"CEP {cep_clean} não consta nos mapas. 🗺️")
        return

    cep_fmt = f"{cep_clean[:5]}-{cep_clean[5:]}"
    msg = (
        f"📍 *CEP {cep_fmt}*\n"
        f"─────────────────\n"
        f"🛣️ {data.get('logradouro', '(sem rua)')}\n"
        f"🏘️ {data.get('bairro', '(sem bairro)')}\n"
        f"🏛️ {data.get('localidade', '?')}/{data.get('uf', '?')}\n"
        f"📮 DDD: {data.get('ddd', '?')}"
    )
    if data.get("complemento"):
        msg += f"\nℹ️ {data['complemento']}"
    await ctx.reply(msg)


SKILL = Skill(
    name="cep",
    description="*!cep / CEP <número>* — buscar endereço",
    triggers=["!cep", "cep", "endereco", "endereço"],
    handler=handle,
    category="info",
)
