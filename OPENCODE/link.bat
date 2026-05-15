@echo off
setlocal enabledelayedexpansion
chcp 65001 > nul 2>&1
cls

echo.
echo   +---------------------------+
echo   ^|   L I N K  -  OpenCode   ^|
echo   +---------------------------+
echo.

REM Carrega as chaves de API
set "SECRETS=%USERPROFILE%\.secrets\hyrule.bat"
if exist "%SECRETS%" (
    call "%SECRETS%"
) else (
    echo  [AVISO] Arquivo de segredos nao encontrado: %SECRETS%
    pause
    exit /b 1
)

echo  Escolha o modelo:
echo.
echo  --- OPENROUTER testados no MASTERSWORD ---
echo   [1] GPT-5.1
echo        Padrao de maior qualidade que funcionou com creditos atuais.
echo   [2] Gemini 2.5 Pro
echo        Fallback de qualidade, contexto longo.
echo   [3] Qwen3 Coder
echo        Fallback focado em codigo.
echo   [4] GPT OSS 120B
echo        Fallback gratuito.
echo   [5] GPT OSS 20B
echo        Fallback gratuito rapido.
echo.

set /p CHOICE=" Opcao: "

if "%CHOICE%"=="1" set "MODEL=openrouter/openai/gpt-5.1"
if "%CHOICE%"=="2" set "MODEL=openrouter/google/gemini-2.5-pro"
if "%CHOICE%"=="3" set "MODEL=openrouter/qwen/qwen3-coder"
if "%CHOICE%"=="4" set "MODEL=openrouter/openai/gpt-oss-120b:free"
if "%CHOICE%"=="5" set "MODEL=openrouter/openai/gpt-oss-20b:free"

if "%MODEL%"=="" (
    echo.
    echo  [ERRO] Opcao invalida.
    pause
    exit /b 1
)

echo.
echo  Modelo selecionado: %MODEL%

set /a "OR_IDX=!RANDOM! %% 3"
if "!OR_IDX!"=="0" set "OPENROUTER_API_KEY=!OPENROUTER_API_KEY!"
if "!OR_IDX!"=="1" set "OPENROUTER_API_KEY=!OPENROUTER_API_KEY_2!"
if "!OR_IDX!"=="2" set "OPENROUTER_API_KEY=!OPENROUTER_API_KEY_3!"
echo  Chave OpenRouter: #!OR_IDX!

if "%OPENCODE_EXPERIMENTAL_OUTPUT_TOKEN_MAX%"=="" set "OPENCODE_EXPERIMENTAL_OUTPUT_TOKEN_MAX=2048"

REM Atualiza o model no opencode.json
set "CONFIG=%APPDATA%\opencode\opencode.json"
powershell -Command "(Get-Content '%CONFIG%' -Raw | ConvertFrom-Json | ForEach-Object { $_.model = '%MODEL%'; $_ } | ConvertTo-Json -Depth 10) | Set-Content '%CONFIG%' -Encoding UTF8"

echo  Abrindo OpenCode...
echo.

set "OPENCODE_BIN=%USERPROFILE%\Agents\OPENCODE\bin\opencode.exe"
if exist "%OPENCODE_BIN%" (
    "%OPENCODE_BIN%" -m "%MODEL%" %*
) else (
    opencode -m "%MODEL%" %*
)
