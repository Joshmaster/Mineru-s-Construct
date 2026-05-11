"""
Faz upload do QR do WhatsApp para catbox.moe.

Com Baileys bridge: o QR fica disponível em http://localhost:7334/qr (HTML).
Este script não é mais necessário — o bridge serve o QR diretamente.
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
    print("✅ WhatsApp já está conectado. QR não necessário.")
elif data.get("hasQr"):
    print(f"\n📱 QR disponível em: {BRIDGE_URL}/qr")
    print("Acesse pelo browser — não precisa de upload externo.")
else:
    print("Bridge está iniciando, aguarde alguns segundos.")
