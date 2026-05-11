"""
Exibe o QR do WhatsApp no terminal.

Com Baileys bridge: acessa http://localhost:7334/qr no browser.
Este script agora só redireciona para o bridge.
"""
import sys
import urllib.request

BRIDGE_URL = "http://localhost:7334"

try:
    with urllib.request.urlopen(f"{BRIDGE_URL}/status", timeout=3) as r:
        import json
        data = json.loads(r.read())
except Exception:
    print("Bridge não está rodando. Inicia com: node whatsapp-bridge/index.js")
    sys.exit(1)

if data.get("connected"):
    print("✅ WhatsApp já está conectado.")
elif data.get("hasQr"):
    print(f"\n📱 Escaneie o QR em: {BRIDGE_URL}/qr\n")
    print("Abra o link no browser ou use:")
    print(f"  curl {BRIDGE_URL}/qr > qr.html && xdg-open qr.html")
else:
    print("Bridge está iniciando, aguarde alguns segundos e tente de novo.")
