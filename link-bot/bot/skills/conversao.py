"""Skill: conversão de unidades (peso, distância, temperatura, tempo, volume)."""

import re
from bot.core.router import Skill
from bot.core.context import MessageContext


# (alias_regex, fator_para_base_si, nome_amigável)
# Categoria → unidade base
CATEGORIES = {
    "distancia": {  # base: metro
        "base_unit": "m",
        "units": {
            "mm": (0.001, "milímetro"),
            "cm": (0.01, "centímetro"),
            "m": (1.0, "metro"),
            "km": (1000.0, "quilômetro"),
            "in": (0.0254, "polegada"),
            "polegada": (0.0254, "polegada"),
            "polegadas": (0.0254, "polegada"),
            "ft": (0.3048, "pé"),
            "pe": (0.3048, "pé"),
            "pes": (0.3048, "pé"),
            "yd": (0.9144, "jarda"),
            "jarda": (0.9144, "jarda"),
            "mi": (1609.344, "milha"),
            "milha": (1609.344, "milha"),
            "milhas": (1609.344, "milha"),
        }
    },
    "peso": {  # base: grama
        "base_unit": "g",
        "units": {
            "mg": (0.001, "miligrama"),
            "g": (1.0, "grama"),
            "grama": (1.0, "grama"),
            "gramas": (1.0, "grama"),
            "kg": (1000.0, "quilo"),
            "quilo": (1000.0, "quilo"),
            "quilos": (1000.0, "quilo"),
            "ton": (1_000_000.0, "tonelada"),
            "tonelada": (1_000_000.0, "tonelada"),
            "lb": (453.592, "libra"),
            "libra": (453.592, "libra"),
            "libras": (453.592, "libra"),
            "oz": (28.3495, "onça"),
            "onca": (28.3495, "onça"),
        }
    },
    "tempo": {  # base: segundo
        "base_unit": "s",
        "units": {
            "ms": (0.001, "milissegundo"),
            "s": (1.0, "segundo"),
            "segundo": (1.0, "segundo"),
            "segundos": (1.0, "segundo"),
            "min": (60.0, "minuto"),
            "minuto": (60.0, "minuto"),
            "minutos": (60.0, "minuto"),
            "h": (3600.0, "hora"),
            "hora": (3600.0, "hora"),
            "horas": (3600.0, "hora"),
            "d": (86400.0, "dia"),
            "dia": (86400.0, "dia"),
            "dias": (86400.0, "dia"),
        }
    },
    "volume": {  # base: litro
        "base_unit": "l",
        "units": {
            "ml": (0.001, "mililitro"),
            "l": (1.0, "litro"),
            "litro": (1.0, "litro"),
            "litros": (1.0, "litro"),
            "gal": (3.78541, "galão"),
            "galao": (3.78541, "galão"),
        }
    },
}


def _convert_temp(value: float, from_u: str, to_u: str) -> float | None:
    """Temperatura é especial — não é multiplicativa."""
    from_u = from_u.lower()
    to_u = to_u.lower()
    # Normaliza
    aliases = {
        "c": "c", "celsius": "c", "°c": "c",
        "f": "f", "fahrenheit": "f", "°f": "f",
        "k": "k", "kelvin": "k", "°k": "k",
    }
    fu = aliases.get(from_u)
    tu = aliases.get(to_u)
    if not fu or not tu:
        return None

    # Tudo pra Celsius primeiro
    if fu == "c":
        c = value
    elif fu == "f":
        c = (value - 32) * 5 / 9
    else:  # k
        c = value - 273.15

    # Celsius pro destino
    if tu == "c":
        return c
    if tu == "f":
        return c * 9 / 5 + 32
    return c + 273.15


def _find_category(unit: str) -> str | None:
    u = unit.lower()
    for cat, data in CATEGORIES.items():
        if u in data["units"]:
            return cat
    return None


def convert(value: float, from_u: str, to_u: str) -> tuple | None:
    """Retorna (valor_convertido, nome_destino) ou None."""
    from_u = from_u.lower().strip()
    to_u = to_u.lower().strip()

    # Tempera tura?
    if from_u in ("c", "f", "k", "celsius", "fahrenheit", "kelvin",
                   "°c", "°f", "°k") or \
       to_u in ("c", "f", "k", "celsius", "fahrenheit", "kelvin",
                "°c", "°f", "°k"):
        result = _convert_temp(value, from_u, to_u)
        if result is None:
            return None
        nomes = {"c": "°C", "f": "°F", "k": "K"}
        target_alias = to_u.lower().replace("°", "").replace("celsius", "c")\
            .replace("fahrenheit", "f").replace("kelvin", "k")
        return (result, nomes.get(target_alias, to_u))

    cat_from = _find_category(from_u)
    cat_to = _find_category(to_u)
    if cat_from is None or cat_to is None or cat_from != cat_to:
        return None

    units = CATEGORIES[cat_from]["units"]
    factor_from = units[from_u][0]
    factor_to = units[to_u][0]
    nome_to = units[to_u][1]
    result = value * factor_from / factor_to
    return (result, nome_to)


async def handle(ctx: MessageContext):
    args = ctx.args_text.strip().lower()
    if not args:
        await ctx.reply(
            "Qual conversão, parceiro? 🔄\n"
            "_Ex: 'converte 100 km em milhas'_\n"
            "_Ex: '50 kg em libras'_, _'72 F em C'_"
        )
        return

    # Padrão: "<numero> <unidade> em/para <unidade>"
    m = re.search(
        r"([-+]?\d+(?:[.,]\d+)?)\s*([a-z°]+)\s+(?:em|para|to|->|=)\s+([a-z°]+)",
        args
    )
    if not m:
        # Tenta sem palavra "em"
        m = re.search(r"([-+]?\d+(?:[.,]\d+)?)\s*([a-z°]+)\s+([a-z°]+)", args)
    if not m:
        await ctx.reply(
            "Não entendi a conversão 🌀.\n"
            "_Tenta: 'converte 100 km em milhas'_"
        )
        return

    valor_str = m.group(1).replace(",", ".")
    try:
        valor = float(valor_str)
    except ValueError:
        await ctx.reply("Valor inválido 🌀")
        return

    from_u = m.group(2)
    to_u = m.group(3)

    result = convert(valor, from_u, to_u)
    if result is None:
        await ctx.reply(
            f"Não consegui converter de '{from_u}' pra '{to_u}' 🗺️.\n"
            "_Aceito: distância (m, km, mi, ft), peso (g, kg, lb, oz),_\n"
            "_volume (l, ml, gal), tempo (s, min, h, d), temperatura (c, f, k)_"
        )
        return

    valor_conv, nome = result

    # Formata
    if abs(valor_conv) >= 1:
        v_fmt = f"{valor_conv:.4f}".rstrip("0").rstrip(".")
    else:
        v_fmt = f"{valor_conv:.6f}".rstrip("0").rstrip(".")

    await ctx.reply(f"🔄 {valor} {from_u} = *{v_fmt} {nome}(s)*")


SKILL = Skill(
    name="conversao",
    description="*converte X unidade em Y* — runa de transmutação",
    triggers=["converte", "converter", "conversao", "conversão"],
    handler=handle,
    category="util",
)
