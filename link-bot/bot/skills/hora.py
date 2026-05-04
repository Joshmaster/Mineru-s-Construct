"""Skill: hora mundial - timezone via zoneinfo (stdlib)."""

from datetime import datetime
from zoneinfo import ZoneInfo
from bot.core.router import Skill
from bot.core.context import MessageContext


CIDADES_TZ = {
    "tokyo": ("Asia/Tokyo", "Tóquio 🗾"),
    "tóquio": ("Asia/Tokyo", "Tóquio 🗾"),
    "toquio": ("Asia/Tokyo", "Tóquio 🗾"),
    "japao": ("Asia/Tokyo", "Tóquio 🗾"),
    "japão": ("Asia/Tokyo", "Tóquio 🗾"),
    "new york": ("America/New_York", "Nova York 🗽"),
    "ny": ("America/New_York", "Nova York 🗽"),
    "nova york": ("America/New_York", "Nova York 🗽"),
    "los angeles": ("America/Los_Angeles", "Los Angeles 🌴"),
    "la": ("America/Los_Angeles", "Los Angeles 🌴"),
    "london": ("Europe/London", "Londres 🇬🇧"),
    "londres": ("Europe/London", "Londres 🇬🇧"),
    "paris": ("Europe/Paris", "Paris 🥐"),
    "frança": ("Europe/Paris", "Paris 🥐"),
    "franca": ("Europe/Paris", "Paris 🥐"),
    "berlim": ("Europe/Berlin", "Berlim 🇩🇪"),
    "berlin": ("Europe/Berlin", "Berlim 🇩🇪"),
    "madrid": ("Europe/Madrid", "Madrid 🇪🇸"),
    "espanha": ("Europe/Madrid", "Madrid 🇪🇸"),
    "lisboa": ("Europe/Lisbon", "Lisboa 🇵🇹"),
    "portugal": ("Europe/Lisbon", "Lisboa 🇵🇹"),
    "sydney": ("Australia/Sydney", "Sydney 🦘"),
    "australia": ("Australia/Sydney", "Sydney 🦘"),
    "austrália": ("Australia/Sydney", "Sydney 🦘"),
    "dubai": ("Asia/Dubai", "Dubai 🌴"),
    "moscow": ("Europe/Moscow", "Moscou 🇷🇺"),
    "moscou": ("Europe/Moscow", "Moscou 🇷🇺"),
    "china": ("Asia/Shanghai", "Shanghai 🐉"),
    "shanghai": ("Asia/Shanghai", "Shanghai 🐉"),
    "pequim": ("Asia/Shanghai", "Shanghai 🐉"),
    "india": ("Asia/Kolkata", "Mumbai 🇮🇳"),
    "índia": ("Asia/Kolkata", "Mumbai 🇮🇳"),
    "buenos aires": ("America/Argentina/Buenos_Aires", "Buenos Aires 🇦🇷"),
    "argentina": ("America/Argentina/Buenos_Aires", "Buenos Aires 🇦🇷"),
    "santiago": ("America/Santiago", "Santiago 🇨🇱"),
    "chile": ("America/Santiago", "Santiago 🇨🇱"),
    "mexico": ("America/Mexico_City", "Cidade do México 🇲🇽"),
    "méxico": ("America/Mexico_City", "Cidade do México 🇲🇽"),
}


async def handle(ctx: MessageContext):
    args = ctx.args_text.lower().strip()
    if not args:
        # Hora local
        agora = datetime.now()
        await ctx.reply(
            f"⏰ Aqui em Hyrule são *{agora.strftime('%H:%M')}* "
            f"do dia {agora.strftime('%d/%m/%Y')}. 🌀"
        )
        return

    # Procura cidade conhecida
    found = None
    for chave, (tz, nome) in CIDADES_TZ.items():
        if chave in args:
            found = (tz, nome)
            break

    if found is None:
        # Mostra algumas opções
        await ctx.reply(
            "Esse reino eu não tenho no mapa, parceiro. 🗺️\n"
            "_Tenho: Tóquio, NY, Londres, Paris, Sydney, Dubai, "
            "Moscou, Pequim, Buenos Aires, Lisboa..._"
        )
        return

    tz_name, nome = found
    try:
        agora = datetime.now(ZoneInfo(tz_name))
    except Exception:
        await ctx.reply("Esse fuso travou no portal 🌀")
        return

    msg = (
        f"⏰ *{nome}*\n"
        f"─────────────────\n"
        f"🕐 {agora.strftime('%H:%M')}\n"
        f"📅 {agora.strftime('%A, %d/%m/%Y')}\n"
        f"🌐 {tz_name}"
    )
    await ctx.reply(msg)


SKILL = Skill(
    name="hora",
    description="*que horas em <cidade>* — consultar fuso horário",
    triggers=["!hora", "que horas", "hora em", "horario em", "horário em", "fuso"],
    handler=handle,
    category="info",
)
