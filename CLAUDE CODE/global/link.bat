@echo off
chcp 65001 > nul 2>&1

echo.
echo   ██╗     ██╗███╗   ██╗██╗  ██╗
echo   ██║     ██║████╗  ██║██║ ██╔╝
echo   ██║     ██║██╔██╗ ██║█████╔╝
echo   ██║     ██║██║╚██╗██║██╔═██╗
echo   ███████╗██║██║ ╚████║██║  ██╗
echo   ╚══════╝╚═╝╚═╝  ╚═══╝╚═╝  ╚═╝
echo.

REM Carrega as chaves de API do arquivo de segredos
set "SECRETS=%USERPROFILE%\.secrets\hyrule.bat"
if exist "%SECRETS%" (
    call "%SECRETS%"
) else (
    echo [AVISO] Arquivo de segredos nao encontrado: %SECRETS%
    echo Crie o arquivo com suas chaves de API antes de continuar.
    pause
    exit /b 1
)

REM Inicia OpenCode
set "OPENCODE_BIN=%LOCALAPPDATA%\Microsoft\WinGet\Packages\SST.opencode_Microsoft.Winget.Source_8wekyb3d8bbwe\opencode.exe"

if exist "%OPENCODE_BIN%" (
    "%OPENCODE_BIN%" %*
) else (
    opencode %*
)
