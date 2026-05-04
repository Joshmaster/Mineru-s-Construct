@echo off
chcp 65001 > nul 2>&1

REM Inicia o agent apontando para o Hyrule Proxy
set ANTHROPIC_BASE_URL=http://localhost:8765
set ANTHROPIC_API_KEY=proxy-key

echo  Agent apontando para Hyrule Proxy (localhost:8765)
echo  Certifique-se de que o start_proxy.bat esta rodando em outro terminal.
echo.

set "OPENCODE_BIN=%LOCALAPPDATA%\Microsoft\WinGet\Packages\SST.opencode_Microsoft.Winget.Source_8wekyb3d8bbwe\opencode.exe"
if exist "%OPENCODE_BIN%" (
    "%OPENCODE_BIN%" %*
) else (
    opencode %*
)
