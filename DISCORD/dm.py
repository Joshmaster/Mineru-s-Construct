"""
CLI para gerenciar DMs Discord via Link daemon (localhost:7331).

Comandos:
  python dm.py OWNER "mensagem"              — envia DM
  python dm.py ver [N]                      — mostra ultimas N msgs do buffer (padrao 20)
  python dm.py historico OWNER [N]           — historico real do DM com usuario
  python dm.py apagar OWNER N                — apaga as ultimas N mensagens do bot
  python dm.py limpar OWNER                  — modo interativo: revisa e apaga mensagem a mensagem
  python dm.py baixar OWNER [N]              — baixa anexos das ultimas N msgs (padrao 1)
  python dm.py enviar-arquivo OWNER arquivo  — envia arquivo pelo DM
  python dm.py status                       — status do daemon
"""
import sys
import os
import json
import urllib.request
import urllib.error

BASE = "http://localhost:7331"


def _post(endpoint: str, data: dict) -> dict:
    payload = json.dumps(data).encode("utf-8")
    req = urllib.request.Request(
        f"{BASE}{endpoint}",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST"
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read())


def _get(endpoint: str) -> dict:
    with urllib.request.urlopen(f"{BASE}{endpoint}", timeout=10) as resp:
        return json.loads(resp.read())


def daemon_offline():
    print("Erro: Link Discord daemon nao esta rodando.")
    print("Inicie com: discord-start  (ou python .../link_discord.py)")


def enviar(nome: str, msg: str):
    try:
        r = _post("/send", {"to": nome, "msg": msg})
        if r.get("ok"):
            print(f"[Enviado para {nome}] {msg}")
        else:
            print(f"Erro: {r.get('error')}")
    except urllib.error.URLError:
        daemon_offline()


def ver_buffer(limit: int = 20):
    try:
        msgs = _get(f"/messages?limit={limit}")
        if not msgs:
            print("Nenhuma mensagem no buffer.")
            return
        print(f"\n--- Ultimas {len(msgs)} mensagens ---")
        for m in msgs:
            linha = f"[{m['time']}] [{m['direction']}] {m['from']} -> {m['to']}: {m['msg']}"
            print(linha.encode('ascii', 'replace').decode('ascii'))
        print("------------------------------------\n")
    except urllib.error.URLError:
        daemon_offline()


def historico(nome: str, limit: int = 20):
    try:
        r = _get(f"/history?user={nome}&limit={limit}")
        if not r.get("ok"):
            print(f"Erro: {r.get('error')}")
            return
        msgs = r["mensagens"]
        print(f"\n--- Historico com {r['usuario']} ({len(msgs)} msgs) ---")
        for m in msgs:
            quem = "Voce" if m["meu"] else m["autor"]
            anexo = f" [{len(m['anexos'])} anexo(s)]" if m["anexos"] else ""
            print(f"[{m['data']}] {quem}: {m['conteudo']}{anexo}  (ID: {m['id']})".encode('ascii', 'replace').decode('ascii'))
        print("------------------------------------------------------\n")
    except urllib.error.URLError:
        daemon_offline()


def apagar(nome: str, count: int):
    try:
        r = _post("/delete", {"to": nome, "count": count})
        if r.get("ok"):
            print(f"{r['deletadas']} mensagem(ns) apagada(s) com {nome}.")
            if r["erros"]:
                for e in r["erros"]:
                    print(f"  Aviso: {e}")
        else:
            print(f"Erro: {r.get('error')}")
    except urllib.error.URLError:
        daemon_offline()


def limpar_interativo(nome: str):
    """Modo interativo: mostra cada mensagem do bot e pergunta se quer deletar."""
    try:
        r = _get(f"/history?user={nome}&limit=200")
        if not r.get("ok"):
            print(f"Erro: {r.get('error')}")
            return

        msgs = [m for m in r["mensagens"] if m["meu"]]
        if not msgs:
            print(f"Nenhuma mensagem sua no DM com {nome}.")
            return

        print(f"\n{'='*60}")
        print(f"  Limpeza interativa: {nome} ({len(msgs)} mensagens suas)")
        print(f"{'='*60}\n")

        deletadas = 0
        mantidas = 0

        for idx, m in enumerate(msgs, 1):
            print(f"\n[{idx}/{len(msgs)}] {m['data']}")
            print(f"  Conteudo: {m['conteudo'][:120] or '(sem texto)'}")
            if m["anexos"]:
                for a in m["anexos"]:
                    print(f"  Anexo: {a['nome']} ({a['tamanho_mb']} MB)")
            print(f"  ID: {m['id']}")
            print("-" * 60)

            while True:
                resp = input("  Deletar? (S/N/Q para sair): ").strip().upper()
                if resp == "S":
                    try:
                        result = _post("/delete", {"to": nome, "ids": [m["id"]]})
                        if result.get("deletadas", 0) > 0:
                            print("  Deletada.\n")
                            deletadas += 1
                        else:
                            print(f"  Nao deletada: {result.get('erros', [])}\n")
                    except urllib.error.URLError:
                        daemon_offline()
                    break
                elif resp == "N":
                    mantidas += 1
                    print("  Mantida.\n")
                    break
                elif resp == "Q":
                    print("\nInterrompido.")
                    break
                else:
                    print("  Digite S, N ou Q.")
            else:
                continue
            if resp == "Q":
                break

        print(f"\n{'='*60}")
        print(f"  Deletadas: {deletadas} | Mantidas: {mantidas}")
        print(f"{'='*60}\n")

    except urllib.error.URLError:
        daemon_offline()


def baixar(nome: str, limit: int = 1):
    """Baixa anexos das ultimas N mensagens de um usuario."""
    try:
        r = _get(f"/history?user={nome}&limit=50")
        if not r.get("ok"):
            print(f"Erro: {r.get('error')}")
            return

        baixados = 0
        for m in r["mensagens"]:
            if not m["meu"] and m["anexos"]:
                for a in m["anexos"]:
                    print(f"Baixando: {a['nome']} ({a['tamanho_mb']} MB)...")
                    result = _post("/download", {"url": a["url"], "filename": a["nome"]})
                    if result.get("ok"):
                        print(f"  Salvo em: {result['path']}")
                        baixados += 1
                    else:
                        print(f"  Erro: {result.get('error')}")
                    if baixados >= limit:
                        return
        if baixados == 0:
            print(f"Nenhum anexo encontrado nas ultimas mensagens de {nome}.")
    except urllib.error.URLError:
        daemon_offline()


def enviar_arquivo(nome: str, filepath: str, msg: str = ""):
    try:
        filepath = os.path.abspath(filepath)
        r = _post("/send-file", {"to": nome, "file": filepath, "msg": msg})
        if r.get("ok"):
            print(f"[Arquivo enviado para {nome}] {r['arquivo']}")
        else:
            print(f"Erro: {r.get('error')}")
    except urllib.error.URLError:
        daemon_offline()


def status():
    try:
        r = _get("/status")
        bot = (r['bot'] or 'offline').encode('ascii', 'replace').decode('ascii')
        print(f"Online: {r['online']} | Bot: {bot} | Usuarios: {', '.join(r['usuarios'])}")
    except urllib.error.URLError:
        print("Daemon offline.")


def limpar_historico(user: str = ""):
    try:
        r = _post("/clear-history", {"user": user})
        if r.get("ok"):
            print(f"Historico limpo: {r['cleared']}")
        else:
            print(f"Erro: {r.get('error')}")
    except urllib.error.URLError:
        daemon_offline()


if __name__ == "__main__":
    args = sys.argv[1:]

    if not args:
        print(__doc__)
        sys.exit(0)

    cmd = args[0].lower()

    if cmd == "status":
        status()

    elif cmd == "limpar-historico":
        user = args[1] if len(args) > 1 else ""
        limpar_historico(user)

    elif cmd == "ver":
        limit = int(args[1]) if len(args) > 1 else 20
        ver_buffer(limit)

    elif cmd == "historico":
        if len(args) < 2:
            print("Uso: python dm.py historico <nome> [limit]")
        else:
            limit = int(args[2]) if len(args) > 2 else 20
            historico(args[1], limit)

    elif cmd == "apagar":
        if len(args) < 3:
            print("Uso: python dm.py apagar <nome> <quantidade>")
        else:
            apagar(args[1], int(args[2]))

    elif cmd == "limpar":
        if len(args) < 2:
            print("Uso: python dm.py limpar <nome>")
        else:
            limpar_interativo(args[1])

    elif cmd == "baixar":
        if len(args) < 2:
            print("Uso: python dm.py baixar <nome> [quantidade]")
        else:
            limit = int(args[2]) if len(args) > 2 else 1
            baixar(args[1], limit)

    elif cmd == "enviar-arquivo":
        if len(args) < 3:
            print("Uso: python dm.py enviar-arquivo <nome> <caminho> [mensagem]")
        else:
            msg = " ".join(args[3:]) if len(args) > 3 else ""
            enviar_arquivo(args[1], args[2], msg)

    else:
        # Assume que e um nome de usuario
        nome = args[0]
        if len(args) < 2:
            print(f"Uso: python dm.py {nome} <mensagem>")
            sys.exit(1)
        msg = " ".join(args[1:])
        enviar(nome, msg)
