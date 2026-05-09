#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Teste isolado: valida que llama3.2:3b consegue usar tools do supervisor.
Bypassa OpenRouter e Groq — usa SOMENTE Ollama local.
"""
import json, os, sys, time, urllib.request
from pathlib import Path

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# Importa funções do supervisor
sys.path.insert(0, str(Path(__file__).parent))
from bot_supervisor import (
    chamar_ollama_tools, executar_tool, enviar_discord,
    TOOLS_DEFINICAO, OLLAMA_MODEL
)

FOTO_URL = os.environ.get("TEST_IMAGE_URL", "https://example.com/foto_teste.jpg")
DESKTOP = "~/Desktop/foto_teste.jpg"

SYSTEM = (
    "Voce e o agente Hyrule Supervisor, rodando no PC do OWNER.\n"
    "Use as tools disponiveis para resolver o pedido.\n"
    "Responda em portugues, de forma breve e direta."
)

TAREFAS = [
    {
        "nome": "TESTE 1 — Enviar 5 emojis e apagar",
        "pedido": "Envia a mensagem '🔥⚡🎮🌟💎' para OWNER pelo Discord e depois apaga essa mensagem.",
    },
    {
        "nome": "TESTE 2 — Baixar foto do OWNER para Desktop",
        "pedido": (
            f"Baixa a foto que OWNER enviou no Discord (URL: {FOTO_URL}) "
            f"e salva no caminho: {DESKTOP}"
        ),
    },
    {
        "nome": "TESTE 3 — Baixar gif de Link Zelda e enviar para OWNER",
        "pedido": (
            "Baixa o gif do Link de Zelda que ja existe em "
            "~/Agents/DISCORD/files/link_zelda.gif"
            "e envia para OWNER no Discord."
        ),
    },
]


def rodar_tarefa(tarefa: dict):
    nome   = tarefa["nome"]
    pedido = tarefa["pedido"]
    print(f"\n{'='*60}")
    print(f"  {nome}")
    print(f"  Modelo: {OLLAMA_MODEL}")
    print(f"{'='*60}")
    print(f"  Pedido: {pedido[:100]}...")

    content, tool_calls = chamar_ollama_tools(pedido, SYSTEM, TOOLS_DEFINICAO)

    if not tool_calls and not content:
        print("  [ERRO] Ollama nao respondeu nada.")
        return

    print(f"  Texto do modelo: {content[:100] if content else '(nenhum)'}")
    print(f"  Tool calls: {len(tool_calls)}")

    if not tool_calls:
        print(f"  [AVISO] Modelo respondeu em texto sem chamar tools.")
        return

    for tc in tool_calls:
        fn_name = tc["function"]["name"]
        fn_args = tc["function"].get("arguments", {})
        if isinstance(fn_args, str):
            fn_args = json.loads(fn_args)
        print(f"\n  >> Tool: {fn_name}")
        print(f"     Args: {json.dumps(fn_args, ensure_ascii=False)[:120]}")
        resultado = executar_tool(fn_name, fn_args)
        print(f"     Resultado: {resultado[:120]}")

    print(f"\n  [OK] {nome} concluido.")


if __name__ == "__main__":
    print(f"\nIniciando testes com llama3.2:3b (Ollama local)")
    print(f"Modelo: {OLLAMA_MODEL}\n")

    for tarefa in TAREFAS:
        rodar_tarefa(tarefa)
        time.sleep(2)

    print("\n\nTodos os testes finalizados.")
