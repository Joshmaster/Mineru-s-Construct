"""Daemon: envia card Boss Mundial no Discord 5min antes de cada spawn."""
import datetime, json, math, time, urllib.request
from zoneinfo import ZoneInfo
from world_boss_card import render_boss_card, get_next_boss, intervalMs, REMINDER_MIN

reminderMs = REMINDER_MIN * 60 * 1000

TZ           = ZoneInfo("America/Sao_Paulo")
DISCORD_API  = "http://localhost:7331"
TARGETS      = ["josh_barbosa", "manu"]


def _next_boss_ms() -> int:
    return get_next_boss(int(time.time() * 1000))


def _discord_file(to: str, path: str, caption: str):
    payload = json.dumps({"to": to, "file": path, "caption": caption}).encode()
    req = urllib.request.Request(f"{DISCORD_API}/send-file", data=payload,
        headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            print(f"  Discord {to}: {json.loads(r.read())}", flush=True)
    except Exception as e:
        print(f"  Discord {to} erro: {e}", flush=True)


def log(msg: str):
    ts = datetime.datetime.now(TZ).strftime("%d/%m %H:%M:%S")
    print(f"[{ts}] {msg}", flush=True)


def main():
    alerted: set[int] = set()
    log("Boss Mundial daemon iniciado.")

    while True:
        now_ms   = int(time.time() * 1000)
        next_ms  = _next_boss_ms()
        remind_ms = next_ms - reminderMs
        ms_left  = next_ms - now_ms

        # Dispara aviso 5 min antes (janela de 30s pra não perder o tick)
        if remind_ms <= now_ms < remind_ms + 30_000 and next_ms not in alerted:
            alerted.add(next_ms)
            boss_time = datetime.datetime.fromtimestamp(next_ms / 1000, tz=TZ).strftime("%d/%m às %H:%M")
            log(f"Aviso boss em 5min — {boss_time}")
            try:
                path = render_boss_card(warning=True)
                caption = f"Boss Mundial em 5 minutos! — {boss_time}"
                for t in TARGETS:
                    _discord_file(t, path, caption)
            except Exception as e:
                log(f"Erro ao gerar card: {e}")

        # Limpa alertas antigos
        alerted = {ts for ts in alerted if ts > now_ms - intervalMs}

        time.sleep(15)


if __name__ == "__main__":
    main()
