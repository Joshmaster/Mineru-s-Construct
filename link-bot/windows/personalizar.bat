@echo off
REM ============================================================
REM  Link Bot TOTK - Personalizar (Windows)
REM ============================================================
chcp 65001 >nul
color 0E
title Link Bot - Personalizar
echo.
echo  ============================================================
echo    LINK BOT TOTK - Personalizar
echo  ============================================================
echo.

set KIT_DIR=%~dp0..
set CONFIG_DIR=%KIT_DIR%\config

REM --- Validacao ---
if not exist "%CONFIG_DIR%\config.example.json" (
    color 0C
    echo  ERRO: config.example.json nao encontrado.
    echo  Estrutura do kit corrompida.
    pause
    exit /b 1
)

REM --- Backup ---
if exist "%CONFIG_DIR%\config.json" (
    set BTS=%date:~6,4%%date:~3,2%%date:~0,2%-%time:~0,2%%time:~3,2%
    set BTS=%BTS: =0%
    copy /Y "%CONFIG_DIR%\config.json" "%CONFIG_DIR%\config.json.backup-%BTS%" >nul
    echo  Backup do config anterior: config.json.backup-%BTS%
    echo.
)

REM --- Pedir numero ---
echo  [1/2] Configurando seu numero...
echo.
echo  Digite seu numero do WhatsApp ^(que vai poder falar com o bot^):
echo  Formato: 5511999999999 ^(codigo do pais + DDD + numero, sem + ou espacos^)
echo.
set /p MEU_NUM="  Numero: "

REM Valida: so digitos, pelo menos 10 chars
echo %MEU_NUM%| findstr /R "^[0-9][0-9]*$" >nul
if errorlevel 1 (
    color 0C
    echo  ERRO: numero deve conter apenas digitos.
    pause
    exit /b 1
)

REM --- Pedir controle PC ---
echo.
echo  [2/2] Controle do PC pelo WhatsApp?
echo.
echo  As skills de PC ^(abre programa, CPU, volume, screenshot^)
echo  ficam DESATIVADAS por padrao por seguranca.
echo.
echo  [S] Ativar agora ^(use SO se confia 100% no numero acima^)
echo  [N] Manter desativado ^(recomendado, pode mudar depois^)
echo.
set /p PC_CHOICE="  Escolha [S/N] ^(default N^): "

set PC_ENABLED=false
if /i "%PC_CHOICE%"=="S" set PC_ENABLED=true

REM --- Gerar config.json ---
echo.
echo  Gerando config.json...

> "%CONFIG_DIR%\config.json" (
echo {
echo   "MODE": "TOTK puro ^(sem LLM^)",
echo   "ALLOW_FROM": ["%MEU_NUM%"],
echo   "STORAGE_PATH": "%%USERPROFILE%%\\.linkbot\\data.db",
echo   "SESSION_PATH": "%%USERPROFILE%%\\.linkbot\\session.sqlite",
echo   "ENABLE_PC_CONTROL": %PC_ENABLED%
echo }
)

echo  OK.

REM --- Mensagem final ---
echo.
echo  ============================================================
echo    Personalizacao concluida!
echo.
echo    Numero autorizado: %MEU_NUM%
echo    Controle PC: %PC_ENABLED%
echo.
echo    Proximo: duplo clique em  menu.bat
echo      [4] Iniciar bot ^(primeira vez vai pedir QR^)
echo  ============================================================
echo.
pause
