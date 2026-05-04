"""Skill: calculadora segura via AST (sem eval, sem injeção de código)."""

import ast
import math
import operator as op
from bot.core.router import Skill
from bot.core.context import MessageContext


# Operações permitidas
OPS = {
    ast.Add: op.add,
    ast.Sub: op.sub,
    ast.Mult: op.mul,
    ast.Div: op.truediv,
    ast.FloorDiv: op.floordiv,
    ast.Mod: op.mod,
    ast.Pow: op.pow,
    ast.USub: op.neg,
    ast.UAdd: op.pos,
}

# Funções matemáticas permitidas
FUNCS = {
    "sqrt": math.sqrt,
    "abs": abs,
    "round": round,
    "floor": math.floor,
    "ceil": math.ceil,
    "log": math.log,
    "log10": math.log10,
    "log2": math.log2,
    "exp": math.exp,
    "sin": math.sin,
    "cos": math.cos,
    "tan": math.tan,
    "pi": lambda: math.pi,
    "e": lambda: math.e,
}

CONSTS = {
    "pi": math.pi,
    "e": math.e,
}


def safe_eval(node):
    """Avalia AST limitadamente."""
    if isinstance(node, ast.Constant):
        if isinstance(node.value, (int, float)):
            return node.value
        raise ValueError("só números")

    if isinstance(node, ast.Num):  # python <3.8 compat
        return node.n

    if isinstance(node, ast.BinOp):
        if type(node.op) not in OPS:
            raise ValueError("operador não permitido")
        return OPS[type(node.op)](safe_eval(node.left), safe_eval(node.right))

    if isinstance(node, ast.UnaryOp):
        if type(node.op) not in OPS:
            raise ValueError("operador unário não permitido")
        return OPS[type(node.op)](safe_eval(node.operand))

    if isinstance(node, ast.Name):
        if node.id in CONSTS:
            return CONSTS[node.id]
        raise ValueError(f"nome desconhecido: {node.id}")

    if isinstance(node, ast.Call):
        if not isinstance(node.func, ast.Name):
            raise ValueError("só funções nomeadas")
        fname = node.func.id
        if fname not in FUNCS:
            raise ValueError(f"função não permitida: {fname}")
        args = [safe_eval(a) for a in node.args]
        return FUNCS[fname](*args)

    raise ValueError(f"expressão não permitida: {type(node).__name__}")


def calculate(expr: str):
    """Avalia expressão matemática segura. Levanta ValueError se inválida."""
    # Normaliza vírgula → ponto, x/× → *
    expr = expr.replace(",", ".").replace("×", "*").replace("÷", "/")
    expr = expr.replace("x", "*")  # cuidado: x como variável quebra, mas aqui ok
    tree = ast.parse(expr, mode="eval")
    return safe_eval(tree.body)


async def handle(ctx: MessageContext):
    args = ctx.args_text.strip()
    if not args:
        await ctx.reply(
            "Qual cálculo, parceiro? 🧮\n"
            "_Ex: 'calcula 152 * 38'_, _'quanto é 1024 / 4'_"
        )
        return

    # Limpa palavras conectoras
    expr = args
    for word in ["!calc", "calcula", "calcular", "quanto e", "quanto é",
                 "resultado de", "resultado", "quanto da", "quanto dá"]:
        expr = expr.replace(word, "")
    expr = expr.strip(" ?.")

    if not expr:
        await ctx.reply("Manda a conta, parceiro. 🧮")
        return

    try:
        result = calculate(expr)
    except Exception as e:
        await ctx.reply(
            f"🌀 Não consegui calcular: {e}\n"
            f"_Operadores aceitos: + - * / ** % ()_\n"
            f"_Funções: sqrt, abs, round, log, sin, cos, tan_"
        )
        return

    # Formata: int se for inteiro, senão float com até 6 casas
    if isinstance(result, float):
        if result.is_integer():
            result_fmt = str(int(result))
        else:
            result_fmt = f"{result:.6f}".rstrip("0").rstrip(".")
    else:
        result_fmt = str(result)

    await ctx.reply(f"🧮 {expr.strip()} = *{result_fmt}*")


SKILL = Skill(
    name="calc",
    description="*calcula <expressão>* — runa de cálculo Sheikah",
    triggers=["calcula", "calcular", "quanto e", "quanto é",
              "calc", "resultado"],
    handler=handle,
    category="util",
)
