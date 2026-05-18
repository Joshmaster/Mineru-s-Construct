#!/usr/bin/env python3
"""
Gera cards Boss Mundial Diablo 4 usando Recraft (atual) e DeeVid (próximos).
Usa o mesmo sistema de overlay PIL do world_boss_card.py.
"""
import json, time, sys, requests, io, random
from pathlib import Path
from PIL import Image, ImageDraw, ImageFilter

sys.path.insert(0, str(Path.home() / "Agents"))
from hyrule_env import DISCORD_TOKEN, CF_WORKER_IMG_URL
from world_boss_card import (
    upcoming_bosses, fmt_time, fmt_date, fmt_hour,
    BOSS_DURATION_MIN, BOSS_PROMPTS,
    _font, _text, _text_center, _draw_border, _draw_sep, _glow_overlay, _darken,
    W, H
)

COOKIES_DIR = Path(__file__).parent / "cookies"
CAPTURE_DIR = Path(__file__).parent / "api_capture"
DISCORD_CH  = "1465722444105908315"
DISCORD_API = "https://discord.com/api/v10"

def discord_send(img_bytes, fname, caption):
    r = requests.post(f"{DISCORD_API}/channels/{DISCORD_CH}/messages",
        headers={"Authorization": f"Bot {DISCORD_TOKEN}"},
        data={"content": caption},
        files={"files[0]": (fname, img_bytes, "image/jpeg")})
    d = r.json()
    mid = d.get("id", "?")
    print(f"  Discord: {r.status_code} msg_id={mid}")
    return mid

# ─── Background generators ────────────────────────────────────────────────────

def bg_from_cf(prompt: str) -> Image.Image | None:
    """CF Worker Flux Schnell — sempre disponível."""
    payload = json.dumps({"prompt": prompt, "model": "flux-schnell"}).encode()
    try:
        import urllib.request
        req = urllib.request.Request(CF_WORKER_IMG_URL, data=payload,
            headers={"Content-Type": "application/json", "User-Agent": "HyruleBot/1.0"}, method="POST")
        with urllib.request.urlopen(req, timeout=90) as r:
            if r.status != 200: return None
            return Image.open(io.BytesIO(r.read())).convert("RGBA").resize((W, H))
    except Exception as e:
        print(f"  CF error: {e}")
        return None

def get_recraft_bearer() -> str | None:
    """Carrega token Recraft do arquivo, refresh via Playwright se necessário."""
    raw = (COOKIES_DIR / "recraft_bearer.txt").read_text().strip()
    # Test if token is valid
    token = raw if raw.startswith("Bearer ") else f"Bearer {raw}"
    # Test with a real endpoint
    r = requests.post(
        "https://api.recraft.ai/chat?project_id=ad70c0aa-33dc-47c8-9bd8-ee8ab070c270",
        headers={"Authorization": token, "Content-Type": "application/json"},
        json={"meta": {"prompt": "", "simple_mode": False}},
        timeout=10
    )
    if r.status_code in (200, 201):
        print("  Recraft token: válido")
        return token

    print(f"  Recraft token expirado ({r.status_code}), renovando via Playwright...")
    return _refresh_recraft_token()

def _refresh_recraft_token() -> str | None:
    """Abre Recraft em headless, captura o Bearer de qualquer request da API."""
    from playwright.sync_api import sync_playwright
    cookies = json.loads((COOKIES_DIR / "recraft_cookies.json").read_text())
    captured = []

    with sync_playwright() as p:
        browser = p.chromium.launch(
            executable_path="/usr/bin/google-chrome-stable",
            args=["--no-sandbox", "--disable-dev-shm-usage"], headless=True)
        ctx = browser.new_context(
            user_agent="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/136.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 900})

        def on_req(req):
            auth = req.headers.get("authorization", "")
            if auth.startswith("Bearer ") and "api.recraft.ai" in req.url:
                captured.append(auth)

        page = ctx.new_page()
        page.on("request", on_req)
        page.context.add_cookies(cookies)
        page.goto("https://www.recraft.ai/", wait_until="domcontentloaded", timeout=30000)
        time.sleep(8)  # Wait for auth to initialize

        browser.close()

    if captured:
        token = captured[0]
        (COOKIES_DIR / "recraft_bearer.txt").write_text(token)
        print(f"  Token renovado: {token[:30]}...")
        return token
    print("  Falhou renovar token Recraft")
    return None

def bg_from_recraft(prompt: str, token: str) -> Image.Image | None:
    """Gera background via Recraft API."""
    PROJECT_ID = "ad70c0aa-33dc-47c8-9bd8-ee8ab070c270"
    headers = {"Authorization": token, "Content-Type": "application/json"}

    # Create chat
    r = requests.post(f"https://api.recraft.ai/chat?project_id={PROJECT_ID}",
        headers=headers, json={"meta": {"prompt": "", "simple_mode": False}}, timeout=15)
    if r.status_code not in (200, 201):
        print(f"  Recraft create chat: {r.status_code}")
        return None
    chat_id = r.json()["id"]
    print(f"  Recraft chat: {chat_id}")

    # Send message
    r = requests.post(f"https://api.recraft.ai/chat/{chat_id}/send_message",
        headers=headers, timeout=15,
        json={
            "message": {"type": "user_message", "role": "user", "text": prompt},
            "meta": {"prompt": "", "simple_mode": False}, "stream": False
        })
    if r.status_code not in (200, 201, 204):
        print(f"  Recraft send_message: {r.status_code}")
        return None

    # Poll — novo formato: messages[].message.recraft.result_image_ids[].image_id
    for i in range(40):
        time.sleep(4)
        r = requests.get(f"https://api.recraft.ai/chat/{chat_id}/poll",
            headers=headers, timeout=15)
        if r.status_code != 200:
            print(f"  Recraft poll: {r.status_code}")
            break
        data = r.json()
        msgs = data.get("messages", [])
        generating = data.get("is_generating", True)

        # New format: each msg has type="message" and msg["message"]["type"]=="recraft"
        for msg in msgs:
            inner = msg.get("message", {})
            if inner.get("type") == "recraft" or "recraft" in inner:
                # result_image_ids is always inside inner["recraft"]
                recraft_data = inner.get("recraft", {})
                raw_ids = recraft_data.get("result_image_ids", [])
                # IDs can be strings or {"image_id": "uuid"} dicts
                image_ids = [
                    (x["image_id"] if isinstance(x, dict) else x)
                    for x in raw_ids
                ]
                if image_ids:
                    img_r = requests.get(f"https://api.recraft.ai/image/{image_ids[0]}",
                        headers=headers, timeout=30)
                    if img_r.status_code == 200:
                        print(f"  Recraft imagem baixada ({len(img_r.content)} bytes)")
                        return Image.open(io.BytesIO(img_r.content)).convert("RGBA").resize((W, H))
                    break

        if not generating:
            print("  Recraft: geração concluída mas sem imagem")
            break

    print("  Recraft polling expirou")
    return None

def bg_from_deevid_browser(prompt: str) -> Image.Image | None:
    """Gera imagem DeeVid via Chrome visível (CDP). Funciona mesmo com plano free."""
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            browser = p.chromium.connect_over_cdp("http://localhost:9222")
            ctx = browser.contexts[0]

            # Encontra ou abre tab do DeeVid
            deevid_page = None
            for pg in ctx.pages:
                if "deevid.ai" in pg.url:
                    deevid_page = pg
                    break
            if not deevid_page:
                deevid_page = ctx.new_page()
                deevid_page.goto("https://deevid.ai/pt/ai-image-generator",
                                 wait_until="domcontentloaded", timeout=30000)
                time.sleep(5)

            page = deevid_page
            page.bring_to_front()
            time.sleep(1)

            # Coleta URLs de imagens já existentes para não confundir com a nova
            existing = set(page.evaluate("""() =>
                [...document.querySelectorAll('img[src*="cdn2.deevid.ai"], img[src*="cdn.deevid.ai"]')]
                .map(i => i.src)
            """))

            # Acha textarea via JS para pegar coordenadas exatas
            ta_info = page.evaluate("""() => {
                const ta = [...document.querySelectorAll('textarea')]
                    .find(el => { const r = el.getBoundingClientRect(); return r.width > 100 && r.height > 20; });
                if (!ta) return null;
                const r = ta.getBoundingClientRect();
                return {x: Math.round(r.x + r.width/2), y: Math.round(r.y + r.height/2)};
            }""")
            tx = ta_info["x"] if ta_info else 562
            ty = ta_info["y"] if ta_info else 554
            print(f"  DeeVid browser: textarea em ({tx},{ty})")

            page.mouse.click(tx, ty)
            time.sleep(0.3)
            page.keyboard.press("Control+a")
            page.keyboard.press("Delete")
            time.sleep(0.2)
            page.keyboard.type(prompt, delay=15)
            time.sleep(1.0)  # espera o botão habilitar após digitar

            # Verifica se "Criar" está habilitado e clica
            btn_info = page.evaluate("""() => {
                const btn = [...document.querySelectorAll('button')]
                    .find(b => b.innerText?.trim().startsWith('Criar'));
                if (!btn) return {found: false};
                const r = btn.getBoundingClientRect();
                return {found: true, disabled: btn.disabled,
                        x: Math.round(r.x + r.width/2), y: Math.round(r.y + r.height/2)};
            }""")
            print(f"  DeeVid browser: Criar btn={btn_info}")

            if btn_info.get("found"):
                bx, by = btn_info["x"], btn_info["y"]
                page.mouse.click(bx, by)
                print(f"  DeeVid browser: clicou Criar em ({bx},{by})")
            else:
                page.keyboard.press("Enter")
                print("  DeeVid browser: Enter fallback")

            # Aguarda imagem nova aparecer no DOM (max 90s)
            deadline = time.time() + 90
            new_url = None
            while time.time() < deadline:
                time.sleep(4)
                urls = page.evaluate("""() =>
                    [...document.querySelectorAll('img[src*="cdn2.deevid.ai"], img[src*="cdn.deevid.ai"]')]
                    .filter(i => i.naturalWidth > 100)
                    .map(i => i.src)
                """)
                for u in urls:
                    if u not in existing and "deevid.ai" in u:
                        new_url = u
                        break
                if new_url:
                    break
                elapsed = int(time.time() - (deadline - 90))
                print(f"  DeeVid browser: aguardando imagem... {elapsed}s")

            browser.close()

            if new_url:
                print(f"  DeeVid browser: imagem encontrada {new_url[:80]}")
                r = requests.get(new_url, timeout=30, headers={"Referer": "https://deevid.ai/"})
                if r.status_code == 200 and len(r.content) > 5000:
                    return Image.open(io.BytesIO(r.content)).convert("RGBA").resize((W, H))
            else:
                print("  DeeVid browser: timeout sem imagem nova")
    except Exception as e:
        print(f"  DeeVid browser erro: {e}")
    return None


def bg_from_deevid(prompt: str) -> Image.Image | None:
    """Gera background via DeeVid API (Supabase JWT + Bearer)."""
    import urllib.parse
    cookies_data = json.loads((COOKIES_DIR / "deevid_cookies.json").read_text())
    parts = {c["name"]: urllib.parse.unquote(c["value"]) for c in cookies_data if "sb-sp-auth-token" in c["name"]}
    full = parts.get("sb-sp-auth-token.0", "") + parts.get("sb-sp-auth-token.1", "")
    if not full:
        print("  DeeVid: sem token Supabase")
        return None
    access_token = json.loads(full)["access_token"]

    session = requests.Session()
    for c in cookies_data:
        session.cookies.set(c["name"], c["value"], domain=c.get("domain", "").lstrip("."))

    headers = {
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/136.0.0.0 Safari/537.36",
        "Referer": "https://deevid.ai/pt/ai-image-generator",
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
    }

    # Prompt sem IP direta para evitar content moderation
    safe_prompt = prompt.replace("Diablo 4", "dark fantasy game").replace("Diablo", "demonic")

    r = session.post("https://api.deevid.ai/text-to-image/task/submit",
        headers=headers, timeout=15,
        json={"prompt": safe_prompt, "imageSize": "ONE_BY_ONE"})

    if r.status_code not in (200, 201):
        print(f"  DeeVid submit: {r.status_code}")
        return None

    task_id = r.json().get("data", {}).get("data", {}).get("taskId")
    print(f"  DeeVid task: {task_id}")
    if not task_id:
        return None

    # Poll via my-assets — timeout de 45s para não bloquear o fallback
    import time as _time
    submitted_ts = _time.time()
    MAX_WAIT = 45  # desiste em 45s se DeeVid não completar
    for i in range(24):
        if _time.time() - submitted_ts > MAX_WAIT:
            print("  DeeVid: timeout (>45s), passando para fallback")
            return None
        _time.sleep(5)
        # Verifica se task ainda running
        ex = session.get("https://api.deevid.ai/image/task/existed?type=TEXT2IMAGE",
            headers=headers, timeout=10)
        running = ex.json().get("data", {}).get("data", True)
        print(f"  DeeVid [{i}] running={running}")

        # Pega assets recentes independente do running
        assets_r = session.get(
            "https://api.deevid.ai/my-assets?limit=5&assetType=IMAGE&filter=CREATION",
            headers=headers, timeout=10)
        groups = assets_r.json().get("data", {}).get("data", {}).get("groups", [])
        for g in groups:
            for item in g.get("items", []):
                creation = item.get("detail", {}).get("creation", {})
                if creation.get("taskId") == task_id:
                    state = creation.get("taskState", "")
                    print(f"  DeeVid task state: {state}")
                    if state == "FAIL":
                        print("  DeeVid: FAIL (provavelmente plano free não suporta mais)")
                        return None
                    # Try to find image URL
                    for key in ["imageList", "waterMarkImageList", "noWaterMarkImageList"]:
                        lst = creation.get(key, [])
                        if lst:
                            url = lst[0].get("url", "") if isinstance(lst[0], dict) else lst[0]
                            if url:
                                img_r = requests.get(url, timeout=30)
                                if img_r.status_code == 200:
                                    print(f"  DeeVid imagem: {url[:80]}")
                                    return Image.open(io.BytesIO(img_r.content)).convert("RGBA").resize((W, H))
        # Se passou 25s e ainda PROCESSING, desiste rápido
        if _time.time() - submitted_ts > 25 and not running:
            print("  DeeVid: concluído sem imagem")
            return None

    print("  DeeVid: timeout")
    return None

# ─── Card rendering ───────────────────────────────────────────────────────────

def render_card(boss_ms: int, bg: Image.Image, is_active: bool = False, ai_source: str = "") -> bytes:
    """Renderiza card para um boss específico."""
    bg = _darken(bg.copy(), 155)
    bg = _glow_overlay(bg, is_active)
    canvas = bg.copy()
    draw = ImageDraw.Draw(canvas)

    GOLD  = (200, 160, 20, 255)
    RED   = (220, 40, 20, 255)
    DRED  = (210, 90, 30, 255)
    GRAY  = (150, 120, 90, 255)

    f_title    = _font(54)
    f_subtitle = _font(22)
    f_big      = _font(130)
    f_date     = _font(48)
    f_label    = _font(20)
    f_small    = _font(20)
    f_ai       = _font(22)

    _draw_border(draw)
    _text_center(draw, 60,  ">> BOSS MUNDIAL <<", f_title, GOLD, (40, 0, 0))
    _text_center(draw, 128, "SANTUARIO AGUARDA...", f_subtitle, DRED)
    _draw_sep(draw, 175)

    date_str = fmt_date(boss_ms)
    hour_str = fmt_hour(boss_ms)

    if is_active:
        _text_center(draw, 192, "[ BOSS ATIVO AGORA ]", f_subtitle, RED)
        _text_center(draw, 225, date_str, f_date, RED, (60, 0, 0))
        _text_center(draw, 278, hour_str, f_big, RED, (60, 0, 0))
    else:
        _text_center(draw, 192, "Proximo boss", f_label, GRAY)
        _text_center(draw, 225, date_str, f_date, GOLD, (40, 0, 0))
        _text_center(draw, 278, hour_str, f_big, GOLD, (40, 0, 0))

    _text_center(draw, H - 65, f"Boss Mundial - {date_str} as {hour_str}", f_small, (190, 150, 80, 255))

    # Label da IA no canto inferior esquerdo — fundo escuro + texto branco
    if ai_source:
        label = f"IA: {ai_source}"
        bbox = draw.textbbox((0, 0), label, font=f_ai)
        tw = bbox[2] - bbox[0]
        th = bbox[3] - bbox[1]
        px, py = 28, H - 52
        pad = 6
        draw.rounded_rectangle([px - pad, py - pad, px + tw + pad, py + th + pad],
                                radius=6, fill=(0, 0, 0, 160))
        draw.text((px, py), label, font=f_ai, fill=(240, 220, 100, 255))

    buf = io.BytesIO()
    canvas.convert("RGB").save(buf, format="JPEG", quality=92)
    return buf.getvalue()

# ─── Main ─────────────────────────────────────────────────────────────────────

def _bg_with_fallback(prompt: str, recraft_token: str | None) -> tuple[Image.Image | None, str]:
    """Tenta Recraft → CF Flux. DeeVid desabilitado (account bloqueada por tasks FAIL)."""
    # 1. Recraft (30 créditos/dia)
    if recraft_token:
        print("  [1] Tentando Recraft...")
        bg = bg_from_recraft(prompt, recraft_token)
        if bg:
            return bg, "Recraft"

    # 2. CF Flux Schnell (ilimitado)
    print("  [2] Usando CF Flux Schnell...")
    bg = bg_from_cf(prompt)
    return bg, "CF Flux"


def main():
    now_ms = int(time.time() * 1000)
    bosses = upcoming_bosses(now_ms, 5)
    CAPTURE_DIR.mkdir(exist_ok=True)

    recraft_token = get_recraft_bearer()

    for i, boss_ms in enumerate(bosses):
        label_n = "ATUAL" if i == 0 else f"+{i}"
        ts = fmt_time(boss_ms)
        print(f"\n[{i+1}/5] Card {label_n} — {ts}")

        prompt = random.choice(BOSS_PROMPTS)
        bg, source = _bg_with_fallback(prompt, recraft_token)

        if not bg:
            print(f"  Todas as IAs falharam para card {label_n}")
            continue

        is_active = boss_ms <= now_ms < boss_ms + BOSS_DURATION_MIN * 60 * 1000
        card = render_card(boss_ms, bg, is_active, ai_source=source)
        fname = f"boss_{label_n}.jpg"
        (CAPTURE_DIR / fname).write_bytes(card)

        if i == 0:
            status_label = "🔴 **ATIVO AGORA**" if is_active else f"🗓️ **{ts}**"
            caption = f"⚔️ **Boss Mundial Diablo 4** — {status_label}\n🕐 Dura {BOSS_DURATION_MIN} min | 🎨 {source}"
        else:
            caption = f"📅 **Boss Mundial +{i}** — {ts} ⚔️\n🕐 {BOSS_DURATION_MIN} min | 🎨 {source}"

        discord_send(card, fname, caption)
        print(f"  Card {label_n} enviado via {source}!")
        time.sleep(2)

    print("\n=== Todos os cards enviados! ===")

if __name__ == "__main__":
    main()
