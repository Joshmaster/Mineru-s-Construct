"""Skill: clima - usa Open-Meteo (gratuita, sem API key)."""

import httpx
from bot.core.router import Skill
from bot.core.context import MessageContext


WEATHER_CODE = {
    0: ("☀️", "céu limpo"),
    1: ("🌤️", "principalmente claro"),
    2: ("⛅", "parcialmente nublado"),
    3: ("☁️", "nublado"),
    45: ("🌫️", "neblina"),
    48: ("🌫️", "neblina com geada"),
    51: ("🌦️", "chuvisco fraco"),
    53: ("🌦️", "chuvisco moderado"),
    55: ("🌧️", "chuvisco intenso"),
    61: ("🌧️", "chuva fraca"),
    63: ("🌧️", "chuva moderada"),
    65: ("⛈️", "chuva forte"),
    71: ("🌨️", "neve fraca"),
    73: ("🌨️", "neve moderada"),
    75: ("❄️", "neve forte"),
    80: ("🌦️", "pancadas de chuva fracas"),
    81: ("🌧️", "pancadas de chuva"),
    82: ("⛈️", "pancadas fortes"),
    95: ("⛈️", "trovoada"),
    96: ("⛈️", "trovoada com granizo"),
    99: ("⛈️", "trovoada forte com granizo"),
}


async def _geocode(city: str) -> tuple | None:
    """Busca coordenadas de cidade via Open-Meteo geocoding (gratis)."""
    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.get(
            "https://geocoding-api.open-meteo.com/v1/search",
            params={"name": city, "count": 1, "language": "pt", "format": "json"}
        )
        if r.status_code != 200:
            return None
        data = r.json()
        results = data.get("results", [])
        if not results:
            return None
        first = results[0]
        return (
            first["latitude"],
            first["longitude"],
            first.get("name", city),
            first.get("country", ""),
        )


async def handle(ctx: MessageContext):
    cidade = ctx.args_text.strip()
    if not cidade:
        await ctx.reply(
            "Pra qual reino consultar os ventos, parceiro? 🌬️\n"
            "_Ex: 'clima Porto Alegre'_"
        )
        return

    geo = await _geocode(cidade)
    if geo is None:
        await ctx.reply(
            f"Não achei o reino '{cidade}' nos meus mapas, parceiro. 🗺️\n"
            "Tenta o nome mais completo ou outro lugar."
        )
        return

    lat, lon, nome, pais = geo

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(
                "https://api.open-meteo.com/v1/forecast",
                params={
                    "latitude": lat,
                    "longitude": lon,
                    "current": "temperature_2m,relative_humidity_2m,"
                               "apparent_temperature,weather_code,wind_speed_10m",
                    "daily": "weather_code,temperature_2m_max,"
                             "temperature_2m_min,precipitation_probability_max",
                    "forecast_days": 2,
                    "timezone": "auto",
                }
            )
            if r.status_code != 200:
                await ctx.reply("Os ventos não responderam 🌀. Tenta de novo daqui pouco.")
                return
            data = r.json()
    except Exception as e:
        await ctx.reply(f"O portal travou: {e}")
        return

    cur = data.get("current", {})
    daily = data.get("daily", {})

    code = cur.get("weather_code", 0)
    emoji, desc = WEATHER_CODE.get(code, ("🌀", "indefinido"))
    temp = cur.get("temperature_2m")
    feels = cur.get("apparent_temperature")
    umid = cur.get("relative_humidity_2m")
    vento = cur.get("wind_speed_10m")

    # Amanhã
    tmax_amanha = daily.get("temperature_2m_max", [None, None])[1]
    tmin_amanha = daily.get("temperature_2m_min", [None, None])[1]
    chuva_amanha = daily.get("precipitation_probability_max", [None, None])[1]
    code_amanha = daily.get("weather_code", [0, 0])[1]
    emoji_amanha, desc_amanha = WEATHER_CODE.get(code_amanha, ("🌀", "indefinido"))

    local = f"{nome}" + (f", {pais}" if pais else "")

    msg = (
        f"🗺️ *{local}* {emoji}\n"
        f"─────────────────\n"
        f"*Agora:* {desc}\n"
        f"🌡️ {temp}°C (sensação {feels}°C)\n"
        f"💧 Umidade: {umid}%\n"
        f"🌬️ Vento: {vento} km/h\n"
        f"─────────────────\n"
        f"*Amanhã:* {emoji_amanha} {desc_amanha}\n"
        f"🌡️ Min {tmin_amanha}°C / Max {tmax_amanha}°C\n"
        f"☔ Chance de chuva: {chuva_amanha}%"
    )
    await ctx.reply(msg)


SKILL = Skill(
    name="clima",
    description="*clima <cidade>* — consultar os ventos do reino",
    triggers=["clima", "tempo", "temperatura", "vai chover", "previsao"],
    handler=handle,
    category="info",
)
