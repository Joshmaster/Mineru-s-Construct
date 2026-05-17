#!/usr/bin/env python3
"""One-shot: envia card Zelda no Discord às 14:00 de 17/05/2026."""
import datetime, time, json, urllib.request, tempfile, sys, os
from zoneinfo import ZoneInfo
from pathlib import Path

BASE = Path(__file__).parent
tz   = ZoneInfo("America/Sao_Paulo")

TARGET = datetime.datetime(2026, 5, 17, 14, 0, 0, tzinfo=tz)
DISCORD_API = "http://localhost:7331"
MANU_DISCORD_ID = "512825467397603328"
ZELDA_PROMPT = "Link hero of Hyrule holding a milkshake, lush Hyrule landscape, Legend of Zelda art style, watercolor, golden sunset"
MSG = "comprar o milk gostosim 🥤"

def log(msg):
    ts = datetime.datetime.now().strftime("%H:%M:%S")
    print(f"[{ts}] {msg}", flush=True)

def gerar_imagem() -> str | None:
    try:
        from hyrule_env import CF_WORKER_IMG_URL as url
    except ImportError:
        log("CF_WORKER_IMG_URL não encontrado")
        return None
    payload = json.dumps({"prompt": ZELDA_PROMPT, "model": "flux-schnell"}).encode()
    req = urllib.request.Request(url, data=payload,
                                  headers={"Content-Type": "application/json",
                                           "User-Agent": "HyruleBot/1.0"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=90) as r:
            if r.status != 200:
                log(f"Worker retornou {r.status}")
                return None
            data = r.read()
        out = Path(tempfile.gettempdir()) / "zelda_milkshake.jpg"
        out.write_bytes(data)
        log(f"Imagem gerada: {out}")
        return str(out)
    except Exception as e:
        log(f"Falha ao gerar imagem: {e}")
        return None

def discord_send_file(to: str, path: str, caption: str):
    payload = json.dumps({"to": to, "file": path, "caption": caption}).encode()
    req = urllib.request.Request(f"{DISCORD_API}/send-file", data=payload,
                                  headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            resp = json.loads(r.read())
            log(f"Discord → {to}: {resp}")
    except Exception as e:
        log(f"Falha Discord send-file → {to}: {e}")
        discord_send_text(to, caption)

def discord_send_text(to: str, msg: str):
    payload = json.dumps({"to": to, "msg": msg}).encode()
    req = urllib.request.Request(f"{DISCORD_API}/send", data=payload,
                                  headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            log(f"Discord texto → {to}: {json.loads(r.read())}")
    except Exception as e:
        log(f"Falha Discord texto → {to}: {e}")

def main():
    agora = datetime.datetime.now(tz)
    espera = (TARGET - agora).total_seconds()
    if espera > 0:
        log(f"Aguardando {espera:.0f}s até {TARGET.strftime('%d/%m %H:%M')} BRT...")
        time.sleep(espera)

    log("Disparando lembrete milkshake Zelda!")
    img = gerar_imagem()

    if img:
        discord_send_file("josh_barbosa", img, MSG)
        discord_send_file(MANU_DISCORD_ID, img, MSG)
    else:
        discord_send_text("josh_barbosa", MSG)
        discord_send_text(MANU_DISCORD_ID, MSG)

    log("Concluído. Encerrando.")
    try:
        os.unlink(img)
    except Exception:
        pass

if __name__ == "__main__":
    main()
