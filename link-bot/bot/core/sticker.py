"""
Helpers para criação de figurinhas WhatsApp.

Refinado pra ficar 100% compatível com o formato esperado pelo app:
- Estática: 512x512, WebP, ≤100KB, corte quadrado por padrao
- Animada: 512x512, WebP animado, ≤500KB, ≤10s, corte quadrado
- Metadados EXIF sao opcionais; o envio direto prioriza WebP valido e leve

Requer FFmpeg instalado. Usa o PATH primeiro e cai para /usr/bin/ffmpeg
quando o servico sobe com ambiente reduzido.
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
SYSTEM_FFMPEG = "/usr/bin/ffmpeg"


def ffmpeg_bin() -> Optional[str]:
    """Retorna o binario do FFmpeg, mesmo com PATH reduzido no servico."""
    found = shutil.which("ffmpeg")
    if found:
        return found
    if os.path.isfile(SYSTEM_FFMPEG) and os.access(SYSTEM_FFMPEG, os.X_OK):
        return SYSTEM_FFMPEG
    return None


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
    return ffmpeg_bin() is not None


def _sticker_filter(fit: str = "cover", fps: Optional[int] = None,
                    alpha: bool = True) -> str:
    """
    Monta filtro 512x512.

    cover: preenche o quadrado com crop central, melhor pra figurinha pronta.
    contain: preserva tudo e completa com transparencia.
    """
    mode = "contain" if fit == "contain" else "cover"
    if mode == "contain":
        parts = [
            "scale=512:512:force_original_aspect_ratio=decrease:flags=lanczos",
            "pad=512:512:(ow-iw)/2:(oh-ih)/2:color=0x00000000",
        ]
    else:
        parts = [
            "scale=512:512:force_original_aspect_ratio=increase:flags=lanczos",
            "crop=512:512",
        ]
    if fps:
        parts.append(f"fps={fps}")
    parts.append("setsar=1")
    parts.append("format=rgba" if alpha else "format=yuv420p")
    return ",".join(parts)


def _file_kb(path: str) -> float:
    return os.path.getsize(path) / 1024


async def make_static_sticker(input_path: str, output_path: str,
                              max_size_kb: int = 100,
                              fit: str = "cover") -> Tuple[bool, str]:
    """
    Converte imagem em sticker estático WhatsApp.

    Retorna (sucesso, mensagem).
    """
    if not has_ffmpeg():
        return False, "FFmpeg não encontrado"

    if not os.path.exists(input_path):
        return False, f"Entrada não existe: {input_path}"

    ffmpeg = ffmpeg_bin()

    sticker_filter = _sticker_filter(fit=fit)

    # Comeca alto e reduz em passos pequenos para segurar qualidade sem passar do limite.
    for quality in [92, 86, 80, 74, 68, 60, 52, 44, 36, 28, 20]:
        cmd = [
            ffmpeg, "-y",
            "-i", input_path,
            "-vf", sticker_filter,
            "-frames:v", "1",
            "-lossless", "0",
            "-compression_level", "6",
            "-preset", "picture",
            "-q:v", str(quality),
            "-an",
            output_path,
        ]
        rc, _out, err = await _run_cmd(cmd, timeout=30)

        if rc != 0:
            continue

        size_kb = _file_kb(output_path)
        if size_kb <= max_size_kb:
            return True, f"OK ({size_kb:.1f}KB, q={quality}, fit={fit})"

    return False, "Não foi possível ajustar pro tamanho máximo"


async def make_animated_sticker(input_path: str, output_path: str,
                                max_duration: float = 6.0,
                                max_size_kb: int = 500,
                                fit: str = "cover"
                                ) -> Tuple[bool, str]:
    """
    Converte vídeo/GIF em sticker animado WhatsApp.

    max_duration em segundos (limite real do WA é 10s, padrão 6s pra margem).
    """
    if not has_ffmpeg():
        return False, "FFmpeg não encontrado"

    if not os.path.exists(input_path):
        return False, f"Entrada não existe: {input_path}"

    ffmpeg = ffmpeg_bin()

    # Tenta combinacoes de fps + qualidade. 15fps e 6s costumam ficar bons
    # sem estourar 500KB; se precisar, reduz suavemente.
    attempts = [
        (15, 82),
        (15, 72),
        (12, 72),
        (12, 62),
        (10, 62),
        (10, 52),
        (8, 46),
        (8, 36),
    ]

    for fps, quality in attempts:
        cmd = [
            ffmpeg, "-y",
            "-t", str(max_duration),
            "-i", input_path,
            "-vf", _sticker_filter(fit=fit, fps=fps, alpha=False),
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

        size_kb = _file_kb(output_path)
        if size_kb <= max_size_kb:
            return True, f"OK ({size_kb:.1f}KB, fps={fps}, q={quality}, fit={fit})"

    # Última tentativa: corta duração mais
    cmd = [
        ffmpeg, "-y",
        "-t", "3",
        "-i", input_path,
        "-vf", _sticker_filter(fit=fit, fps=8, alpha=False),
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
        size_kb = _file_kb(output_path)
        if size_kb <= max_size_kb:
            return True, f"OK reduzido ({size_kb:.1f}KB, fit={fit})"

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
