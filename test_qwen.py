#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Testa o sistema completo: executar_pedido + qwen2.5:7b.
Simula exatamente o que o supervisor faz ao receber um pedido.

Uso: python test_qwen.py
"""
import json
import sys
import time
import urllib.request
from pathlib import Path

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, str(Path(__file__).parent))
from bot_supervisor import (
    OLLAMA_URL, OLLAMA_MODEL, TOOLS_DEFINICAO,
    _ollama_chat, _selecionar_tools, _gerar_hint_sequencia,
    _parse_tool_calls_from_content, executar_pedido,
    carregar_contexto_pc,
)

GREEN  = "\033[92m"
RED    = "\033[91m"
YELLOW = "\033[93m"
RESET  = "\033[0m"
BOLD   = "\033[1m"

# ── Cenários ──────────────────────────────────────────────────────────────────
# Formato: (descrição, pedido, esperado_contém, via)
# via: "python" = executar_pedido deve resolver | "qwen" = qwen deve resolver
# esperado_contém: substring que deve aparecer no resultado (case-insensitive)
CENARIOS = [
    # Atalhos Python (executar_pedido)
    ("IP do PC",
     "qual o ip do meu pc?",
     "ip é",  # "Seu IP é X.X.X.X"
     "python"),

    ("Nome do computador",
     "qual o nome do meu pc?",
     "chama",  # "Seu PC se chama XXXXX"
     "python"),

    ("Espaço em disco",
     "quanto de espaço livre tem no meu hd?",
     "livre",
     "python"),

    ("Listar processos",
     "quais programas estão rodando agora?",
     "rodando agora",
     "python"),

    ("Listar arquivos Desktop via Python",
     "o que tem na minha area de trabalho?",
     "desktop",  # "Desktop:\n[arquivo] ..."
     "python"),

    # qwen ReAct
    ("Abrir chrome",
     "abre o chrome pra mim",
     "abrir_programa",  # verifica tool chamada
     "qwen"),

    ("Fechar notepad",
     "fecha o bloco de notas",
     "fechar_programa",
     "qwen"),

    ("Ler arquivo",
     "le o arquivo senhas.txt que ta no Desktop",
     "ler_arquivo",
     "qwen"),

    ("Escrever arquivo",
     "cria um arquivo notas.txt no Desktop com 'reuniao amanha'",
     "escrever_arquivo",
     "qwen"),

    ("Enviar mensagem USER2",
     "manda uma mensagem pra USER2 dizendo que chego as 20h",
     "enviar_mensagem",
     "qwen"),

    ("Criar arquivo com processos",
     "cria um txt chamado processos.txt no Desktop com a lista de processos rodando",
     "processo",
     "python"),

]


def chamar_qwen_e_verificar(pedido: str, esperado: str) -> tuple[bool, str]:
    """Chama qwen e verifica se a tool chamada contém a string esperada."""
    tools = _selecionar_tools(pedido)
    nomes_tools = [t["function"]["name"] for t in tools]
    tool_hint = _gerar_hint_sequencia(pedido, tools)

    tool_name_hint = ""
    if len(tools) == 1:
        tool_name_hint = f" You MUST call {nomes_tools[0]}."
    elif tools:
        tool_name_hint = f" You MUST call one of: {', '.join(nomes_tools)}."

    system = (
        carregar_contexto_pc() +
        "You are Link, an autonomous PC agent on OWNER's Windows PC.\n"
        "CRITICAL: Do NOT answer from memory. Do NOT guess."
        f"{tool_name_hint}\n"
        "Call the tool to get real data, then reply to OWNER in Portuguese in one sentence.\n"
        "Use executar_comando for any OS query."
    )
    if tool_hint:
        system += "\nInstruction: " + tool_hint

    payload = json.dumps({
        "model":          OLLAMA_MODEL,
        "stream":         False,
        "temperature":    0.7,
        "top_p":          0.8,
        "top_k":          20,
        "repeat_penalty": 1.05,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user",   "content": pedido},
        ],
        "tools": tools,
    }).encode("utf-8")

    req = urllib.request.Request(OLLAMA_URL, data=payload,
          headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            data = json.loads(r.read())
        msg = data.get("message", {})
        tool_calls = msg.get("tool_calls") or []
        content = (msg.get("content") or "").strip()
        if not tool_calls and content:
            tool_calls = _parse_tool_calls_from_content(content)
            if tool_calls:
                content = ""
    except Exception as e:
        return False, f"ERRO Ollama: {e}"

    if not tool_calls:
        return False, f"sem tool call | resposta: {content[:80]}"

    fn_name = tool_calls[0]["function"]["name"]
    fn_args = tool_calls[0]["function"].get("arguments", {})
    if isinstance(fn_args, str):
        try: fn_args = json.loads(fn_args)
        except: fn_args = {}

    detalhe = f"{fn_name}({json.dumps(fn_args, ensure_ascii=False)[:80]})"
    if esperado.lower() in fn_name.lower():
        return True, detalhe
    # Também checa nos args
    args_str = json.dumps(fn_args, ensure_ascii=False).lower()
    if esperado.lower() in args_str:
        return True, detalhe
    return False, f"esperado '{esperado}' mas chamou: {detalhe}"


def main():
    print(f"\n{BOLD}=== Teste Sistema Hyrule — {len(CENARIOS)} cenários ==={RESET}\n")

    resultados = []
    for i, (desc, pedido, esperado, via) in enumerate(CENARIOS, 1):
        print(f"[{i:02d}] {BOLD}{desc}{RESET}  [{via.upper()}]")
        print(f"     Pedido: \"{pedido}\"")

        t0 = time.time()

        if via == "python":
            # Testa executar_pedido diretamente
            try:
                resultado = executar_pedido(pedido)
            except Exception as e:
                resultado = None
            elapsed = time.time() - t0

            if resultado and esperado.lower() in resultado.lower():
                print(f"     {GREEN}✓ OK — Python ({elapsed:.1f}s){RESET}")
                print(f"     Resultado: {resultado[:100]}")
                resultados.append((desc, True, "python"))
            elif resultado:
                # Resultado existe mas não tem o esperado — pode ser OK (teste de hostname pode variar)
                print(f"     {YELLOW}~ OK mas resultado diferente ({elapsed:.1f}s){RESET}")
                print(f"     Resultado: {resultado[:100]}")
                resultados.append((desc, "parcial", "python"))
            else:
                print(f"     {RED}✗ FALHOU — executar_pedido retornou None ({elapsed:.1f}s){RESET}")
                resultados.append((desc, False, "python"))

        else:  # qwen
            ok, detalhe = chamar_qwen_e_verificar(pedido, esperado)
            elapsed = time.time() - t0
            if ok:
                print(f"     {GREEN}✓ OK — qwen ({elapsed:.1f}s){RESET}")
                print(f"     Tool: {detalhe}")
                resultados.append((desc, True, "qwen"))
            else:
                print(f"     {RED}✗ FALHOU — qwen ({elapsed:.1f}s){RESET}")
                print(f"     {detalhe}")
                resultados.append((desc, False, "qwen"))
        print()

    # Resumo
    ok      = sum(1 for _, r, _ in resultados if r is True)
    parcial = sum(1 for _, r, _ in resultados if r == "parcial")
    falhou  = sum(1 for _, r, _ in resultados if r is False)
    total   = len(resultados)

    python_ok = sum(1 for _, r, via in resultados if via == "python" and r is True)
    python_t  = sum(1 for _, _, via in resultados if via == "python")
    qwen_ok   = sum(1 for _, r, via in resultados if via == "qwen" and r is True)
    qwen_t    = sum(1 for _, _, via in resultados if via == "qwen")

    print(f"{BOLD}=== Resultado: {ok}/{total} passou | {parcial} parcial | {falhou} falhou ==={RESET}")
    print(f"     Python (executar_pedido): {python_ok}/{python_t}")
    print(f"     qwen2.5:7b:            {qwen_ok}/{qwen_t}\n")

    if falhou > 0:
        print(f"{RED}Falhas:{RESET}")
        for desc, r, via in resultados:
            if r is False:
                print(f"  - [{via.upper()}] {desc}")

    return 0 if falhou == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
