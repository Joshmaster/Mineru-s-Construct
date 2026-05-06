"""Gera QR WhatsApp, salva PNG e faz upload para catbox.moe."""
import sys, asyncio, urllib.request, urllib.parse
from pathlib import Path
BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

import qrcode
from neonize.aioze.client import NewAClient
from neonize.aioze.events import ConnectedEv

QR_PATH = str(BASE_DIR / "link-bot" / ".linkbot" / "qr_upload.png")
client = NewAClient("qr_upload")

@client.event.qr
async def on_qr(c, data: bytes):
    qr = qrcode.QRCode(version=1, box_size=20, border=4)
    qr.add_data(data)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    img.save(QR_PATH)

    import urllib.request, urllib.parse
    import io, os
    boundary = b'----boundary'
    with open(QR_PATH, 'rb') as f:
        file_data = f.read()

    body  = b'--' + boundary + b'\r\n'
    body += b'Content-Disposition: form-data; name="reqtype"\r\n\r\nfileupload\r\n'
    body += b'--' + boundary + b'\r\n'
    body += b'Content-Disposition: form-data; name="fileToUpload"; filename="qr.png"\r\n'
    body += b'Content-Type: image/png\r\n\r\n'
    body += file_data + b'\r\n'
    body += b'--' + boundary + b'--\r\n'

    req = urllib.request.Request(
        'https://catbox.moe/user/api.php',
        data=body,
        headers={'Content-Type': f'multipart/form-data; boundary=----boundary'}
    )
    try:
        resp = urllib.request.urlopen(req, timeout=10)
        url = resp.read().decode().strip()
        print(f"\n=== LINK DO QR ===\n{url}\n==================", flush=True)
    except Exception as e:
        print(f"Erro upload: {e}", flush=True)

    await asyncio.sleep(2)
    sys.exit(0)

@client.event(ConnectedEv)
async def on_connected(c, ev):
    print("Conectado!", flush=True)
    sys.exit(0)

asyncio.run(client.connect())
