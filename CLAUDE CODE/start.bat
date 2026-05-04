@echo off
chcp 65001 > nul 2>&1
setlocal

set "AGENT_DIR=%~dp0"

echo.
echo  +--------------------------------------------------+
echo  ^|   Claude Code + Hyrule Proxy                    ^|
echo  +--------------------------------------------------+
echo.

REM Verifica Python
python --version > nul 2>&1
if errorlevel 1 (
    echo  [ERRO] Python nao encontrado no PATH.
    pause
    exit /b 1
)

REM Instala dependencias se necessario
pip show flask > nul 2>&1
if errorlevel 1 (
    echo  Instalando dependencias...
    pip install flask requests pyyaml python-dotenv -q --disable-pip-version-check
)

REM Inicia proxy em janela separada
echo  Iniciando Hyrule Proxy em http://localhost:8765 ...
start "Hyrule Proxy" cmd /k "python \"%AGENT_DIR%proxy.py\""

REM Aguarda proxy subir
timeout /t 2 > nul

REM Aponta Claude Code para o proxy
set ANTHROPIC_BASE_URL=http://localhost:8765
set ANTHROPIC_API_KEY=hyrule-proxy

echo  Iniciando Claude Code...
echo.
claude %*
