@echo off
REM ============================================================
REM  Link Bot TOTK - Instalar / Atualizar (Windows)
REM ============================================================
chcp 65001 >nul
color 0B
title Link Bot - Instalar/Atualizar
echo.
echo  ============================================================
echo    LINK BOT TOTK - Instalar / Atualizar
echo  ============================================================
echo.

REM --- Detectar Python ---
echo  [1/4] Procurando Python 3.11+...
set PY_CMD=
python --version >nul 2>&1
if not errorlevel 1 set PY_CMD=python
if "%PY_CMD%"=="" (
    py --version >nul 2>&1
    if not errorlevel 1 set PY_CMD=py
)
if "%PY_CMD%"=="" (
    color 0C
    echo.
    echo  ERRO: Python nao encontrado.
    echo.
    echo  Baixe Python 3.11+ em https://www.python.org/downloads/
    echo  IMPORTANTE: marque "Add Python to PATH" na instalacao.
    pause
    exit /b 1
)
%PY_CMD% --version
echo  OK.

REM --- Verificar versao minima ---
for /f "tokens=2" %%v in ('%PY_CMD% --version 2^>^&1') do set PY_VER=%%v
echo  Versao detectada: %PY_VER%

REM --- Atualizar pip ---
echo.
echo  [2/4] Atualizando pip...
%PY_CMD% -m pip install --upgrade pip --quiet --disable-pip-version-check
echo  OK.

REM --- Instalar/atualizar dependencias ---
echo.
echo  [3/4] Instalando dependencias do bot...
echo  ^(neonize, qrcode, httpx, psutil^)
echo.
%PY_CMD% -m pip install --upgrade neonize qrcode[pil] httpx psutil
if errorlevel 1 (
    color 0C
    echo.
    echo  ERRO ao instalar dependencias.
    echo  Possiveis causas: sem internet, firewall, ou Python antigo.
    pause
    exit /b 1
)

REM --- Verificar FFmpeg ---
echo.
echo  [4/4] Verificando FFmpeg ^(opcional, para figurinhas^)...
ffmpeg -version >nul 2>&1
if errorlevel 1 (
    color 0E
    echo.
    echo  ATENCAO: FFmpeg nao encontrado.
    echo  Sem ele, a skill de figurinha nao funciona.
    echo.
    echo  Instalar com:
    echo    winget install Gyan.FFmpeg
    echo  ou:
    echo    choco install ffmpeg
    echo.
    echo  ^(O resto do bot funciona normal sem FFmpeg^)
    color 0B
) else (
    echo  FFmpeg detectado.
)

echo.
echo  ============================================================
echo    Instalacao concluida, aventureiro!
echo.
echo    Proximo: rode  personalizar.bat
echo  ============================================================
echo.
pause
