@echo off
chcp 65001 > nul 2>&1

echo.
echo  +--------------------------------------------------+
echo  ^|   Hyrule Proxy - Iniciando...                   ^|
echo  +--------------------------------------------------+
echo.

REM Verifica Python
python --version > nul 2>&1
if errorlevel 1 (
    echo  [ERRO] Python nao encontrado.
    pause
    exit /b 1
)

REM Instala dependencias se necessario
pip show flask > nul 2>&1
if errorlevel 1 (
    echo  Instalando Flask...
    pip install flask requests pyyaml -q
)

REM Define caminho do proxy
set PROXY=%USERPROFILE%\.claude\proxy.py

if not exist "%PROXY%" (
    echo  [ERRO] proxy.py nao encontrado em %PROXY%
    echo  Copie o arquivo proxy.py para %USERPROFILE%\.claude\
    pause
    exit /b 1
)

REM Inicia o proxy
echo  Iniciando proxy em http://localhost:8765
echo  Mantenha esta janela aberta!
echo  O menu de fallback aparece AQUI quando o Ollama falhar.
echo.
python "%PROXY%"
pause
