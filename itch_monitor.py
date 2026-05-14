"""
Daemon: monitora vendas e seguidores do Adventure Kit (itch.io).
Roda localmente a cada 5 minutos — substitui o GitHub Actions.
Notifica via Discord DM (porta 7331) e WhatsApp (ponte Baileys porta 7334).
"""

import json
import re
import time
import urllib.request
import urllib.parse
import urllib.error
from pathlib import Path

BASE_DIR   = Path(__file__).resolve().parent
STATE_FILE = BASE_DIR / "itch_state.json"
PID_FILE   = BASE_DIR / ".itch_monitor_pid"
LOG_FILE   = BASE_DIR / "itch_monitor.log"

ITCH_URL   = "https://joshsword.itch.io/adventure-kit"
PROFILE_URL = "https://itch.io/profile/joshsword"

DISCORD_API = "http://localhost:7331/send"
WA_API      = "http://localhost:7334/send/text"

INTERVAL = 5 * 60  # 5 minutos


def _log(msg: str):
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line, flush=True)
    try:
        with LOG_FILE.open("a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


def _wa_owner_jid() -> str | None:
    try:
        cfg = json.loads((BASE_DIR / "link-bot/config/config.json").read_text())
        owner = cfg.get("OWNER") or (cfg.get("OWNER_IDS") or [None])[0]
        if owner:
            raw = str(owner).split("@")[0].split(":")[0]
            return f"{raw}@s.whatsapp.net"
    except Exception:
        pass
    return None


def _post_json(url: str, payload: dict) -> bool:
    try:
        body = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url, data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=15) as r:
            return r.status == 200
    except Exception as e:
        _log(f"[warn] POST {url} falhou: {e}")
        return False


def notify(msg: str):
    # Discord DM para josh
    ok_d = _post_json(DISCORD_API, {"to": "josh", "msg": msg})
    _log(f"Discord: {'ok' if ok_d else 'falhou'}")

    # WhatsApp DM para o owner
    jid = _wa_owner_jid()
    if jid:
        ok_w = _post_json(WA_API, {"jid": jid, "text": msg})
        _log(f"WhatsApp ({jid}): {'ok' if ok_w else 'falhou'}")


def _get(url: str) -> str | None:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=15) as r:
            return r.read().decode("utf-8", errors="ignore")
    except Exception as e:
        _log(f"[warn] GET {url}: {e}")
        return None


def _val_after_label(html: str, label: str) -> str | None:
    """Extrai stat_value imediatamente antes de um stat_label."""
    m = re.search(
        r'stat_value[^>]*>([\$\d,\.]+)</div>\s*<div[^>]*stat_label[^>]*>' + re.escape(label),
        html, re.I,
    )
    return m.group(1).strip() if m else None


def scrape_funding(html: str) -> dict:
    data = {}

    # Raised (primary_stat → stat_value)
    m = re.search(r'primary_stat[^>]*>.*?stat_value[^>]*>([\$\d,\.]+)', html, re.S)
    if m:
        data["arrecadado"] = m.group(1)

    # Goal (right_box → stat_value)
    m = re.search(r'right_box[^>]*>.*?stat_value[^>]*>([\$\d,\.]+)', html, re.S)
    if m:
        data["meta"] = m.group(1)

    # Porcentagem (div com class progress_inner e style width)
    m = re.search(r'style="width:\s*([\d\.]+)%"[^>]*class="progress_inner"|class="progress_inner"[^>]*style="width:\s*([\d\.]+)%"', html)
    if m:
        pct = m.group(1) or m.group(2)
        data["porcentagem"] = f"{int(float(pct))}%"

    # Contributors, average, top via label
    for label, campo in [
        ("contributors", "contribuidores"),
        ("average contribution", "media"),
        ("top contribution", "maior"),
    ]:
        v = _val_after_label(html, label)
        if v:
            data[campo] = v

    return data


def scrape_followers(html: str) -> str | None:
    m = re.search(r'stat_value[^>]*>(\d+)</div>\s*<div[^>]*stat_label[^>]*>Followers', html, re.I)
    return m.group(1) if m else None


def barra(pct_str: str, size: int = 12) -> str:
    try:
        pct = max(0, min(100, int(re.sub(r"[^\d]", "", str(pct_str)))))
    except Exception:
        pct = 0
    filled = round(size * pct / 100)
    return "▓" * filled + "░" * (size - filled) + f" {pct}%"


def montar_msg(data: dict, seguidores: str | None = None) -> str:
    lines = [
        f"💰 Arrecadado: {data.get('arrecadado', '—')}",
        f"🎯 Meta: {data.get('meta', '$100.00')}",
        barra(data.get("porcentagem", "0")),
        f"👥 {data.get('contribuidores', '—')} contribuidor(es)",
        f"📈 Média: {data.get('media', '—')}",
        f"🏆 Maior: {data.get('maior', '—')}",
    ]
    if seguidores:
        lines.append(f"👤 Seguidores: {seguidores}")
    return "\n".join(lines)


def load_state() -> dict:
    try:
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_state(state: dict):
    STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def check_once():
    _log("Verificando itch.io...")

    html_itch    = _get(ITCH_URL)
    html_profile = _get(PROFILE_URL)

    if not html_itch:
        _log("Falha ao acessar itch.io — pulando ciclo.")
        return

    dados   = scrape_funding(html_itch)
    seguidores = scrape_followers(html_profile) if html_profile else None
    anterior = load_state()

    novo = {**dados}
    if seguidores:
        novo["seguidores"] = seguidores

    if not anterior:
        _log("Primeiro ciclo — capturando estado inicial.")
        msg = "🛡️ *itch-monitor iniciado!* Estado atual:\n\n" + montar_msg(dados, seguidores)
        notify(msg)
        save_state(novo)
        return

    campos_venda = ["arrecadado", "porcentagem", "contribuidores", "media", "maior"]
    mudou_venda  = any(dados.get(c) != anterior.get(c) for c in campos_venda if dados.get(c))
    mudou_seg    = bool(seguidores and seguidores != anterior.get("seguidores"))

    if mudou_venda:
        _log("Nova venda detectada!")
        notify("🎉 *Adventure Kit — Nova VENDA!*\n\n" + montar_msg(dados, seguidores))
    if mudou_seg:
        _log(f"Novo seguidor! {anterior.get('seguidores')} → {seguidores}")
        notify(f"👤 *Novo seguidor no itch.io!*\nAgora você tem *{seguidores}* seguidores.")

    if mudou_venda or mudou_seg:
        save_state(novo)
    else:
        _log("Sem mudanças.")


def main():
    PID_FILE.write_text(str(__import__("os").getpid()))
    _log("itch-monitor daemon iniciado.")
    while True:
        try:
            check_once()
        except Exception as e:
            _log(f"[erro] {e}")
        time.sleep(INTERVAL)


if __name__ == "__main__":
    main()
