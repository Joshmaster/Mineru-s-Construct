"""Skill: gerar QR code via biblioteca qrcode (local, sem internet)."""

import tempfile
from pathlib import Path
from bot.core.router import Skill
from bot.core.context import MessageContext

try:
    import qrcode
    HAS_QRCODE = True
except ImportError:
    HAS_QRCODE = False


async def handle(ctx: MessageContext):
    if not HAS_QRCODE:
        await ctx.reply(
            "🌀 Falta a biblioteca qrcode. Instala com:\n"
            "_`pip install qrcode[pil]`_"
        )
        return

    args = ctx.args_text.strip()
    if not args:
        await ctx.reply(
            "O que vira QR, parceiro? 🔢\n"
            "_Ex: 'gera qr https://github.com'_\n"
            "_Ex: 'qr meu wifi: senha123'_"
        )
        return

    if len(args) > 1500:
        await ctx.reply("Texto longo demais pro QR (max 1500 chars). 🌀")
        return

    try:
        qr = qrcode.QRCode(
            version=None,
            error_correction=qrcode.constants.ERROR_CORRECT_M,
            box_size=10,
            border=2,
        )
        qr.add_data(args)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")

        out_path = str(Path(tempfile.gettempdir()) / "link_qr.png")
        img.save(out_path)
    except Exception as e:
        await ctx.reply(f"⚡ A runa do QR explodiu: {e}")
        return

    try:
        await ctx.reply_media(out_path, caption=f"🔢 QR de: _{args[:60]}_")
    except Exception as e:
        await ctx.reply(f"🌀 Falhou ao enviar: {e}")


SKILL = Skill(
    name="qr",
    description="*gera qr <texto>* — runa de teleporte digital",
    triggers=["!qr", "gera qr", "qr code", "qrcode", "gerar qr"],
    handler=handle,
    category="util",
    priority=8,  # acima de "qr" sozinho que pode ser outra coisa
)
