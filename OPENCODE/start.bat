@echo off
chcp 65001 > nul 2>&1
setlocal

set "AGENT_DIR=%~dp0"

echo.
echo  +--------------------------------------------------+
echo  ^|   OpenCode - Link, Heroi de Hyrule              ^|
echo  +--------------------------------------------------+
echo.

REM Carrega chaves de API (arquivo de segredos opcional)
set "SECRETS=%USERPROFILE%\.secrets\hyrule.bat"
if exist "%SECRETS%" (
    call "%SECRETS%"
) else (
    REM Tenta usar variaveis ja definidas no ambiente
    if "%GROQ_API_KEY%"=="" (
        echo  [AVISO] GROQ_API_KEY nao definida.
    )
    if "%OPENROUTER_API_KEY%"=="" (
        echo  [AVISO] OPENROUTER_API_KEY nao definida.
    )
)

REM Detecta o executavel do OpenCode
set "OPENCODE_BIN=%USERPROFILE%\Agents\OPENCODE\bin\opencode.exe"

if not exist "%OPENCODE_BIN%" (
    where opencode > nul 2>&1
    if errorlevel 1 (
        echo  [ERRO] opencode.exe nao encontrado.
        echo  Instale via: winget install SST.opencode
        pause
        exit /b 1
    )
    set "OPENCODE_BIN=opencode"
)

REM Roda OpenCode apontando para o config desta pasta
cd /d "%AGENT_DIR%"
"%OPENCODE_BIN%" %*
