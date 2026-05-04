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
echo  --- GROQ ---
echo   [1]  LLaMA 4 Scout 17B
echo        Rapido, gratis. Persona OK. Edit/bash bugados (tipos errados no schema).
echo.
echo  --- OPENROUTER (gratuito) ---
echo   [10] GPT OSS 120B
echo        Tools OK (bash, edit, read, glob, grep). Recomendado para codigo.
echo   [11] Nemotron 120B
echo        Tools OK. Modelo grande da NVIDIA, bom raciocinio.
echo   [12] Gemma 4 31B
echo        Tools OK. Multimodal, contexto longo.
echo   [13] Gemma 3 12B
echo        INDISPONIVEL para tools. Modelo trava ao iniciar no OpenCode.
echo   [14] Gemma 3 4B
echo        INDISPONIVEL para tools. Modelo trava ao iniciar no OpenCode.
echo   [15] Gemma 3n E2B
echo        INDISPONIVEL para tools. Modelo trava ao iniciar no OpenCode.
echo   [16] Nemotron Nano 30B
echo        Tools OK. Compacto da NVIDIA, bom custo-beneficio.
echo   [17] GLM 4.5 Air
echo        Tools OK. Modelo chines (Zhipu AI), bom em codigo.
echo   [18] MiniMax M2.5
echo        INDISPONIVEL para tools. Modelo nao encontrado no OpenRouter.
echo   [19] Trinity Large Preview
echo        Tools OK. Modelo Arcee focado em agentes e instrucoes.
echo   [20] LFM 2.5 1.2B
echo        INDISPONIVEL para tools. Modelo trava ao iniciar no OpenCode.
echo   [21] Gemma 3 27B
echo        INDISPONIVEL para tools. Modelo trava ao iniciar no OpenCode.
echo.
echo  --- OPENROUTER (pago) ---
echo   [22] Gemini 2.5 Pro
echo        Tools OK. Melhor modelo do Google. Contexto 1M tokens. Requer creditos pagos.
echo.
echo  --- OLLAMA ---
echo   [23] Kimi K2.5 (cloud)
echo        Abre via: ollama launch opencode. NAO TESTADO ainda.
echo   [24] LLaMA 3.3
echo        Abre via: ollama launch opencode. NAO TESTADO ainda.
echo.

set /p CHOICE=" Opcao: "

if "%CHOICE%"=="1"  set "MODEL=groq/meta-llama/llama-4-scout-17b-16e-instruct"
if "%CHOICE%"=="10" set "MODEL=openrouter/openai/gpt-oss-120b:free"
if "%CHOICE%"=="11" set "MODEL=openrouter/nvidia/nemotron-3-super-120b-a12b:free"
if "%CHOICE%"=="12" set "MODEL=openrouter/google/gemma-4-31b-it:free"
if "%CHOICE%"=="13" set "MODEL=openrouter/google/gemma-3-12b-it:free"
if "%CHOICE%"=="14" set "MODEL=openrouter/google/gemma-3-4b-it:free"
if "%CHOICE%"=="15" set "MODEL=openrouter/google/gemma-3n-e2b-it:free"
if "%CHOICE%"=="16" set "MODEL=openrouter/nvidia/nemotron-3-nano-30b-a3b:free"
if "%CHOICE%"=="17" set "MODEL=openrouter/z-ai/glm-4.5-air:free"
if "%CHOICE%"=="18" set "MODEL=openrouter/minimax/minimax-m2.5:free"
if "%CHOICE%"=="19" set "MODEL=openrouter/arcee-ai/trinity-large-preview:free"
if "%CHOICE%"=="20" set "MODEL=openrouter/liquid/lfm-2.5-1.2b-instruct:free"
if "%CHOICE%"=="21" set "MODEL=openrouter/google/gemma-3-27b-it:free"
if "%CHOICE%"=="22" set "MODEL=openrouter/google/gemini-2.5-pro-preview-06-05"
if "%CHOICE%"=="23" set "MODEL=ollama/kimi-k2.5:cloud"
if "%CHOICE%"=="24" set "MODEL=ollama/llama3.3"

if "%MODEL%"=="" (
    echo.
    echo  [ERRO] Opcao invalida.
    pause
    exit /b 1
)

echo.
echo  Modelo selecionado: %MODEL%

REM Rotacao de chaves GROQ (opcao 1)
if "%CHOICE%"=="1" (
    set /a "GROQ_IDX=!RANDOM! %% 3"
    if "!GROQ_IDX!"=="0" set "GROQ_API_KEY=!GROQ_API_KEY!"
    if "!GROQ_IDX!"=="1" set "GROQ_API_KEY=!GROQ_API_KEY_2!"
    if "!GROQ_IDX!"=="2" set "GROQ_API_KEY=!GROQ_API_KEY_3!"
    echo  Chave GROQ: #!GROQ_IDX!
)

REM Rotacao de chaves OpenRouter (opcoes 10-22)
if not "%CHOICE%"=="1" if not "%CHOICE%"=="23" if not "%CHOICE%"=="24" (
    set /a "OR_IDX=!RANDOM! %% 3"
    if "!OR_IDX!"=="0" set "OPENROUTER_API_KEY=!OPENROUTER_API_KEY!"
    if "!OR_IDX!"=="1" set "OPENROUTER_API_KEY=!OPENROUTER_API_KEY_2!"
    if "!OR_IDX!"=="2" set "OPENROUTER_API_KEY=!OPENROUTER_API_KEY_3!"
    echo  Chave OpenRouter: #!OR_IDX!
)

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
