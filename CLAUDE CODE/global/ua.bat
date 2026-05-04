@echo off
chcp 65001 > nul 2>&1
setlocal

set AGENT=%USERPROFILE%\.claude\universal_agent.py

REM Verifica dependencias
python -c "import requests" > nul 2>&1
if errorlevel 1 (
    echo  Instalando dependencias minimas...
    pip install requests pyyaml python-dotenv -q --disable-pip-version-check
)

python "%AGENT%" %*
