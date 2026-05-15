#!/usr/bin/env python3
"""CLI simples para rodar o MASTERSWORD sem passar pela fila."""

from __future__ import annotations

import sys

from watch_mastersword_queue import _ensure_config, _modelos, _rodar_opencode


def main(argv: list[str]) -> int:
    _ensure_config()
    if not argv or argv[0] in {"-h", "--help", "help"}:
        print("uso:")
        print("  ./mastersword                 # abre OpenCode interativo com GPT-5.1")
        print("  ./mastersword \"pedido\"         # roda pedido direto")
        print("  ./mastersword run \"pedido\"     # igual acima")
        print("  ./mastersword models          # lista fallback")
        print("  ./mastersword config          # mostra config usada")
        return 0
    if argv[0] == "models":
        for i, model in enumerate(_modelos(), 1):
            print(f"{i}. {model}")
        return 0

    pedido = " ".join(argv).strip()
    if not pedido:
        print("pedido vazio")
        return 2
    resposta, model = _rodar_opencode(pedido, "cli")
    if model:
        print(f"[{model}]")
    print(resposta)
    return 0 if model else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
