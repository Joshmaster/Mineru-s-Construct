#!/usr/bin/env python3
"""
Mantém sessões de sites de IA sempre frescas.
- Captura cookies após login manual
- Detecta expiração e renova automaticamente antes que expirarem
- Recraft: JWT Keycloak 1h — renova a cada 50min via Playwright headless
- DeeVid: Supabase JWT — renova a cada 6h via Playwright headless
"""
import json, time, sys, subprocess, threading
from pathlib import Path
from datetime import datetime, timezone
import base64

sys.path.insert(0, str(Path.home() / "Agents"))

COOKIES_DIR = Path(__file__).parent / "cookies"

# ─── JWT helpers ─────────────────────────────────────────────────────────────

def _jwt_exp(token: str) -> int | None:
    """Retorna o timestamp de expiração de um JWT, ou None."""
    try:
        parts = token.split(".")
        if len(parts) < 2:
            return None
        payload = parts[1]
        # Add padding
        payload += "=" * (-len(payload) % 4)
        data = json.loads(base64.urlsafe_b64decode(payload))
        return data.get("exp")
    except Exception:
        return None

def _seconds_until_exp(token: str) -> int:
    """Segundos até expirar. Negativo = já expirou."""
    exp = _jwt_exp(token)
    if exp is None:
        return -1
    return int(exp - time.time())

def _extract_bearer(raw: str) -> str:
    """Garante que o token tem prefixo 'Bearer '."""
    raw = raw.strip()
    return raw if raw.startswith("Bearer ") else f"Bearer {raw}"

# ─── Captura de cookies via CDP (após login manual) ──────────────────────────

def capture_cookies_from_live_browser(site_name: str, url: str) -> list | None:
    """Captura cookies do Chrome CDP já aberto."""
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            browser = p.chromium.connect_over_cdp("http://localhost:9222")
            ctx = browser.contexts[0]
            cookies = ctx.cookies([url])
            browser.close()
        if cookies:
            out = COOKIES_DIR / f"{site_name}_cookies.json"
            out.write_text(json.dumps(cookies, indent=2))
            print(f"[{site_name}] {len(cookies)} cookies salvos → {out}")
            return cookies
    except Exception as e:
        print(f"[{site_name}] Erro ao capturar cookies: {e}")
    return None

# ─── Recraft token refresh ────────────────────────────────────────────────────

def refresh_recraft(headless: bool = True) -> str | None:
    """Abre Recraft, captura novo Bearer token da API."""
    print("[recraft] Renovando token...")
    try:
        from playwright.sync_api import sync_playwright
        cookies = json.loads((COOKIES_DIR / "recraft_cookies.json").read_text())
        captured = []

        with sync_playwright() as p:
            browser = p.chromium.launch(
                executable_path="/usr/bin/google-chrome-stable",
                args=["--no-sandbox", "--disable-dev-shm-usage"], headless=headless)
            ctx = browser.new_context(
                user_agent="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/136.0.0.0 Safari/537.36",
                viewport={"width": 1280, "height": 900})

            def on_req(req):
                auth = req.headers.get("authorization", "")
                if auth.startswith("Bearer ") and "api.recraft.ai" in req.url:
                    if auth not in captured:
                        captured.append(auth)

            page = ctx.new_page()
            page.on("request", on_req)
            page.context.add_cookies(cookies)
            page.goto("https://www.recraft.ai/", wait_until="domcontentloaded", timeout=30000)
            time.sleep(8)

            # Also capture new recraft cookies (NextAuth session may rotate)
            new_cookies = ctx.cookies(["https://www.recraft.ai"])
            if new_cookies:
                (COOKIES_DIR / "recraft_cookies.json").write_text(json.dumps(new_cookies, indent=2))

            browser.close()

        if captured:
            token = captured[0]
            (COOKIES_DIR / "recraft_bearer.txt").write_text(token)
            exp = _seconds_until_exp(token.replace("Bearer ", ""))
            print(f"[recraft] Token renovado. Expira em {exp//60}min.")
            return token

    except Exception as e:
        print(f"[recraft] Erro: {e}")
    return None

# ─── DeeVid token refresh ─────────────────────────────────────────────────────

def refresh_deevid(headless: bool = True) -> bool:
    """Abre DeeVid e captura cookies frescos (Supabase JWT)."""
    print("[deevid] Renovando sessão...")
    try:
        from playwright.sync_api import sync_playwright
        cookies = json.loads((COOKIES_DIR / "deevid_cookies.json").read_text())

        with sync_playwright() as p:
            browser = p.chromium.launch(
                executable_path="/usr/bin/google-chrome-stable",
                args=["--no-sandbox", "--disable-dev-shm-usage"], headless=headless)
            ctx = browser.new_context(
                user_agent="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/136.0.0.0 Safari/537.36",
                viewport={"width": 1280, "height": 900})

            page = ctx.new_page()
            page.context.add_cookies(cookies)
            page.goto("https://deevid.ai/pt/ai-image-generator", wait_until="domcontentloaded", timeout=30000)
            time.sleep(6)

            new_cookies = ctx.cookies(["https://deevid.ai"])
            if new_cookies:
                (COOKIES_DIR / "deevid_cookies.json").write_text(json.dumps(new_cookies, indent=2))
                print(f"[deevid] {len(new_cookies)} cookies atualizados.")
                browser.close()
                return True

            browser.close()
    except Exception as e:
        print(f"[deevid] Erro: {e}")
    return False

# ─── Verificação de saúde ─────────────────────────────────────────────────────

def check_recraft_health() -> dict:
    """Retorna status do token Recraft."""
    bearer_file = COOKIES_DIR / "recraft_bearer.txt"
    if not bearer_file.exists():
        return {"ok": False, "reason": "sem arquivo"}
    raw = bearer_file.read_text().strip()
    token = raw.replace("Bearer ", "")
    exp = _jwt_exp(token)
    if exp is None:
        return {"ok": False, "reason": "JWT inválido"}
    secs = int(exp - time.time())
    return {"ok": secs > 60, "expires_in": secs, "expires_at": datetime.fromtimestamp(exp).strftime("%H:%M:%S")}

def check_deevid_health() -> dict:
    """Retorna status da sessão DeeVid (Supabase JWT)."""
    import urllib.parse
    cookies_file = COOKIES_DIR / "deevid_cookies.json"
    if not cookies_file.exists():
        return {"ok": False, "reason": "sem cookies"}
    cookies = json.loads(cookies_file.read_text())
    # Token é dividido entre .0 e .1 e vem URL-encoded
    parts = {c["name"]: urllib.parse.unquote(c["value"]) for c in cookies if "sb-sp-auth-token" in c["name"]}
    full = parts.get("sb-sp-auth-token.0", "") + parts.get("sb-sp-auth-token.1", "")
    if not full:
        return {"ok": False, "reason": "sem token supabase"}
    try:
        data = json.loads(full)
        access = data.get("access_token", "")
        secs = _seconds_until_exp(access)
        exp_at = datetime.fromtimestamp(time.time() + secs).strftime("%d/%m %H:%M") if secs > 0 else "EXPIRADO"
        return {"ok": secs > 60, "expires_in": secs, "expires_at": exp_at}
    except Exception as e:
        return {"ok": False, "reason": str(e)}

# ─── Daemon de renovação automática ──────────────────────────────────────────

def run_keeper_daemon(check_interval: int = 300):
    """Loop que renova tokens antes de expirarem. Roda em background."""
    RECRAFT_RENEW_BEFORE = 600   # renova 10min antes de expirar
    DEEVID_RENEW_BEFORE  = 1800  # renova 30min antes de expirar

    print(f"[keeper] Daemon iniciado. Check a cada {check_interval}s.")
    while True:
        # ── Recraft ──
        rh = check_recraft_health()
        if not rh["ok"] or rh.get("expires_in", 9999) < RECRAFT_RENEW_BEFORE:
            reason = f"expira em {rh.get('expires_in',0)//60}min" if rh["ok"] else rh.get("reason","?")
            print(f"[keeper] Recraft precisa renovar ({reason})")
            refresh_recraft(headless=True)

        # ── DeeVid ──
        dh = check_deevid_health()
        if not dh["ok"] or dh.get("expires_in", 9999) < DEEVID_RENEW_BEFORE:
            reason = f"expira em {dh.get('expires_in',0)//60}min" if dh["ok"] else dh.get("reason","?")
            print(f"[keeper] DeeVid precisa renovar ({reason})")
            refresh_deevid(headless=True)

        time.sleep(check_interval)

# ─── CLI ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="Session Keeper — mantém tokens de IA frescos")
    ap.add_argument("cmd", nargs="?", default="status",
        choices=["status", "capture-deevid", "capture-recraft", "refresh-recraft", "refresh-deevid", "daemon"])
    args = ap.parse_args()

    if args.cmd == "status":
        rh = check_recraft_health()
        dh = check_deevid_health()
        print(f"Recraft : {'✓ OK' if rh['ok'] else '✗ EXPIRADO'} — expira em {rh.get('expires_in',0)//60}min ({rh.get('expires_at','?')})")
        print(f"DeeVid  : {'✓ OK' if dh['ok'] else '✗ EXPIRADO'} — expira em {dh.get('expires_in',0)//60}min ({dh.get('expires_at','?')})")

    elif args.cmd == "capture-deevid":
        print("Capturando cookies do DeeVid do Chrome aberto...")
        c = capture_cookies_from_live_browser("deevid", "https://deevid.ai")
        if c:
            print(f"OK — {len(c)} cookies salvos")
            # Check Supabase token
            dh = check_deevid_health()
            print(f"Sessão DeeVid: {'OK' if dh['ok'] else 'EXPIRADO'} — {dh}")

    elif args.cmd == "capture-recraft":
        print("Capturando cookies do Recraft do Chrome aberto...")
        c = capture_cookies_from_live_browser("recraft", "https://www.recraft.ai")
        if c:
            print(f"OK — {len(c)} cookies salvos")

    elif args.cmd == "refresh-recraft":
        t = refresh_recraft(headless=True)
        print("OK" if t else "FALHOU")

    elif args.cmd == "refresh-deevid":
        ok = refresh_deevid(headless=True)
        print("OK" if ok else "FALHOU")

    elif args.cmd == "daemon":
        run_keeper_daemon()
