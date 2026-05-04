@echo off
chcp 65001 > nul 2>&1
setlocal

set "AGENT_DIR=%~dp0"

REM Verifica dependencias
python -c "import requests" > nul 2>&1
if errorlevel 1 (
    echo  Instalando dependencias minimas...
    pip install requests pyyaml python-dotenv -q --disable-pip-version-check
)

python "%AGENT_DIR%universal_agent.py" %*
