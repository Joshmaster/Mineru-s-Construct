"""
Helpers para criação de figurinhas WhatsApp.

Refinado pra ficar 100% compatível com o formato esperado pelo app:
- Estática: 512x512, WebP, ≤100KB, fundo transparente preservado
- Animada: 512x512, WebP animado, ≤500KB, ≤10s, ≤30fps
- Metadados EXIF (sticker pack, autor) — opcional mas recomendado

Requer FFmpeg no PATH.
"""

import asyncio
import json
import os
import shutil
import struct
import tempfile
from pathlib import Path
from typing import Optional, Tuple


STICKER_PACK_NAME = "Pergaminhos do Aventureiro"
STICKER_AUTHOR = "Link de Hyrule"
STICKER_EMOJIS = ["⚔️", "🗡️", "🛡️"]


async def _run_cmd(cmd: list, timeout: int = 60) -> Tuple[int, str, str]:
    """Roda comando async, retorna (returncode, stdout, stderr)."""
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout, stderr = await asyncio.wait_for(
            proc.communicate(), timeout=timeout
        )
    except asyncio.TimeoutError:
        proc.kill()
        return -1, "", "timeout"
    return (
        proc.returncode,
        stdout.decode(errors="replace"),
        stderr.decode(errors="replace"),
    )


def has_ffmpeg() -> bool:
    return shutil.which("ffmpeg") is not None


async def make_static_sticker(input_path: str, output_path: str,
                              max_size_kb: int = 100) -> Tuple[bool, str]:
    """
    Converte imagem em sticker estático WhatsApp.

    Retorna (sucesso, mensagem).
    """
    if not has_ffmpeg():
        return False, "FFmpeg não encontrado no PATH"

    if not os.path.exists(input_path):
        return False, f"Entrada não existe: {input_path}"

    # Tenta com qualidade alta, depois reduz se passar do limite
    for quality in [80, 60, 40, 25, 15]:
        cmd = [
            "ffmpeg", "-y",
            "-i", input_path,
            "-vf",
            "scale=512:512:force_original_aspect_ratio=decrease,"
            "pad=512:512:(ow-iw)/2:(oh-ih)/2:color=0x00000000,"
            "format=rgba",
            "-lossless", "0",
            "-compression_level", "6",
            "-q:v", str(quality),
            "-an",
            "-vsync", "0",
            output_path,
        ]
        rc, _out, err = await _run_cmd(cmd, timeout=30)

        if rc != 0:
            continue

        size_kb = os.path.getsize(output_path) / 1024
        if size_kb <= max_size_kb:
            # Adiciona metadados WhatsApp
            _add_webp_metadata(output_path)
            return True, f"OK ({size_kb:.1f}KB, q={quality})"

    return False, "Não foi possível ajustar pro tamanho máximo"


async def make_animated_sticker(input_path: str, output_path: str,
                                max_duration: float = 6.0,
                                max_size_kb: int = 500
                                ) -> Tuple[bool, str]:
    """
    Converte vídeo/GIF em sticker animado WhatsApp.

    max_duration em segundos (limite real do WA é 10s, padrão 6s pra margem).
    """
    if not has_ffmpeg():
        return False, "FFmpeg não encontrado no PATH"

    if not os.path.exists(input_path):
        return False, f"Entrada não existe: {input_path}"

    # Tenta combinações de fps + qualidade
    attempts = [
        (15, 60),
        (15, 50),
        (12, 50),
        (12, 40),
        (10, 40),
        (10, 30),
        (8, 30),
    ]

    for fps, quality in attempts:
        cmd = [
            "ffmpeg", "-y",
            "-t", str(max_duration),
            "-i", input_path,
            "-vf",
            f"scale=512:512:force_original_aspect_ratio=decrease,"
            f"pad=512:512:(ow-iw)/2:(oh-ih)/2:color=0x00000000,"
            f"fps={fps}",
            "-loop", "0",
            "-lossless", "0",
            "-compression_level", "6",
            "-q:v", str(quality),
            "-preset", "default",
            "-an",
            "-vsync", "0",
            output_path,
        ]
        rc, _out, err = await _run_cmd(cmd, timeout=60)

        if rc != 0:
            continue

        size_kb = os.path.getsize(output_path) / 1024
        if size_kb <= max_size_kb:
            _add_webp_metadata(output_path, animated=True)
            return True, f"OK ({size_kb:.1f}KB, fps={fps}, q={quality})"

    # Última tentativa: corta duração mais
    cmd = [
        "ffmpeg", "-y",
        "-t", "3",
        "-i", input_path,
        "-vf",
        "scale=512:512:force_original_aspect_ratio=decrease,"
        "pad=512:512:(ow-iw)/2:(oh-ih)/2:color=0x00000000,fps=8",
        "-loop", "0",
        "-lossless", "0",
        "-compression_level", "6",
        "-q:v", "20",
        "-an",
        "-vsync", "0",
        output_path,
    ]
    rc, _out, err = await _run_cmd(cmd, timeout=60)
    if rc == 0:
        size_kb = os.path.getsize(output_path) / 1024
        if size_kb <= max_size_kb:
            _add_webp_metadata(output_path, animated=True)
            return True, f"OK reduzido ({size_kb:.1f}KB)"

    return False, f"Vídeo grande demais — tentei várias qualidades"


def _add_webp_metadata(webp_path: str, animated: bool = False):
    """
    Adiciona metadados EXIF de sticker pack ao WebP.

    Formato: chunk EXIF dentro do RIFF container.
    Estrutura: dict JSON serializado contendo sticker-pack-id, name, etc.

    Spec: https://github.com/WhatsApp/stickers/blob/main/Android/README.md
    """
    try:
        meta = {
            "sticker-pack-id": "link-totk-1",
            "sticker-pack-name": STICKER_PACK_NAME,
            "sticker-pack-publisher": STICKER_AUTHOR,
            "emojis": STICKER_EMOJIS,
        }
        meta_json = json.dumps(meta, separators=(",", ":")).encode("utf-8")

        # Lê WebP atual
        with open(webp_path, "rb") as f:
            data = f.read()

        if not data.startswith(b"RIFF") or data[8:12] != b"WEBP":
            return  # não é WebP válido

        # Constrói chunk EXIF (ID="EXIF", size, data)
        # WebP usa little-endian, chunks alinhados em par
        exif_payload = (
            b"II*\x00"  # TIFF header little-endian
            + struct.pack("<I", 8)  # offset to first IFD
            + struct.pack("<H", 1)  # 1 entry
            + struct.pack("<HHII", 0x9286, 7, len(meta_json), 26)  # UserComment
            + struct.pack("<I", 0)  # next IFD = none
            + meta_json
        )

        chunk = b"EXIF" + struct.pack("<I", len(exif_payload)) + exif_payload
        if len(exif_payload) % 2 == 1:
            chunk += b"\x00"  # padding

        # Insere antes do final
        new_data = data + chunk

        # Atualiza tamanho do RIFF
        new_size = len(new_data) - 8
        new_data = b"RIFF" + struct.pack("<I", new_size) + new_data[8:]

        with open(webp_path, "wb") as f:
            f.write(new_data)
    except Exception:
        # metadados são opcionais — se falhar, sticker funciona sem
        pass
