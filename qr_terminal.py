"""Gera QR do WhatsApp e imprime como ASCII no terminal."""
import sys, asyncio, qrcode as _qr
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))

from neonize.aioze.client import NewAClient
from neonize.aioze.events import ConnectedEv

client = NewAClient("qr_pair")

@client.event.qr
async def on_qr(c, data: bytes):
    q = _qr.QRCode(border=1)
    q.add_data(data)
    q.make()
    print("\n" + "="*50)
    print("  ESCANEIE NO WHATSAPP (Aparelhos conectados)")
    print("="*50)
    q.print_ascii(invert=True)
    print("="*50 + "\n")

@client.event(ConnectedEv)
async def on_connected(c, ev):
    print("\n✓ WhatsApp conectado!")
    sys.exit(0)

asyncio.run(client.connect())
