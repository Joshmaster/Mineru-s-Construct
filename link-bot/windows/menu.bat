@echo off
REM ============================================================
REM  Link Bot TOTK - Menu Principal (Windows)
REM ============================================================
chcp 65001 >nul
title Link Bot - Menu

set PY_CMD=
python --version >nul 2>&1 && set PY_CMD=python
if "%PY_CMD%"=="" (
    py --version >nul 2>&1 && set PY_CMD=py
)
if "%PY_CMD%"=="" (
    color 0C
    echo  Python nao encontrado. Rode  instalar-atualizar.bat  primeiro.
    pause
    exit /b 1
)

set KIT_DIR=%~dp0..
set LINKBOT_DIR=%USERPROFILE%\.linkbot

:menu
cls
color 0B
echo.
echo  =============================================================
echo                  LINK BOT TOTK - MENU
echo                Bot pessoal de WhatsApp
echo  =============================================================
echo.
echo   ===== ROTINA DIARIA =====
echo   [1] Iniciar bot                    ^<- mais usado
echo   [2] Re-parear WhatsApp ^(reseta QR^)
echo   [3] Status / config atual
echo.
echo   ===== MANUTENCAO =====
echo   [4] Atualizar dependencias
echo   [5] Reaplicar personalizacao ^(numero/PC^)
echo   [6] Editar config.json
echo   [7] Abrir pasta do bot ^(.linkbot^)
echo.
echo   ===== INFO =====
echo   [V] Versao Python e libs
echo   [S] Listar skills do bot
echo   [B] Backup de tudo
echo   [L] Ver banco ^(SQLite^)
echo.
echo   [0] Sair
echo.
echo  =============================================================
set /p ESCOLHA="  Escolha uma opcao: "

if "%ESCOLHA%"=="1" goto iniciar
if "%ESCOLHA%"=="2" goto reset
if "%ESCOLHA%"=="3" goto status
if "%ESCOLHA%"=="4" goto atualizar
if "%ESCOLHA%"=="5" goto personalizar
if "%ESCOLHA%"=="6" goto editar
if "%ESCOLHA%"=="7" goto pasta
if /i "%ESCOLHA%"=="v" goto versao
if /i "%ESCOLHA%"=="s" goto skills
if /i "%ESCOLHA%"=="b" goto backup
if /i "%ESCOLHA%"=="l" goto banco
if "%ESCOLHA%"=="0" goto sair
echo  Opcao invalida.
timeout /t 1 >nul
goto menu

:iniciar
cls
color 0A
echo.
echo  ============================================================
echo    LINK ESTA ACORDANDO...
echo  ============================================================
echo.
echo   Primeira vez? Aparece QR no terminal pra escanear.
echo   No celular: Aparelhos conectados ^> Conectar um aparelho.
echo.
echo   Pra parar o bot: Ctrl+C
echo.
cd /d "%KIT_DIR%"
%PY_CMD% -m bot.main
cd /d "%~dp0"
echo.
echo   Bot encerrado.
pause
goto menu

:reset
cls
color 0E
echo.
echo  Resetar sessao do WhatsApp ^(vai pedir QR de novo^)?
set /p CONFIRMA="  Tem certeza? [S/N]: "
if /i not "%CONFIRMA%"=="S" goto menu
cd /d "%KIT_DIR%"
%PY_CMD% -m bot.main --reset
cd /d "%~dp0"
echo.
pause
goto menu

:status
cls
color 0B
echo.
echo  ============================================================
echo    STATUS / CONFIG
echo  ============================================================
echo.
if exist "%KIT_DIR%\config\config.json" (
    echo  Config atual:
    echo  ---
    type "%KIT_DIR%\config\config.json"
    echo  ---
) else (
    color 0C
    echo  Config NAO encontrado. Rode personalizar.bat.
)
echo.
if exist "%LINKBOT_DIR%\session.sqlite" (
    echo  Sessao do WhatsApp: PAREADA
) else (
    echo  Sessao do WhatsApp: NAO PAREADA
)
echo.
if exist "%LINKBOT_DIR%\data.db" (
    echo  Banco de dados: existe
) else (
    echo  Banco de dados: ainda nao criado
)
echo.
pause
goto menu

:atualizar
cls
color 0B
echo.
%PY_CMD% -m pip install --upgrade neonize qrcode[pil] httpx psutil
echo.
pause
goto menu

:personalizar
call "%~dp0personalizar.bat"
goto menu

:editar
cls
if exist "%KIT_DIR%\config\config.json" (
    notepad "%KIT_DIR%\config\config.json"
) else (
    color 0C
    echo  Config nao existe. Rode personalizar.bat primeiro.
    pause
)
goto menu

:pasta
if exist "%LINKBOT_DIR%" (
    explorer "%LINKBOT_DIR%"
) else (
    mkdir "%LINKBOT_DIR%"
    explorer "%LINKBOT_DIR%"
)
goto menu

:versao
cls
color 0B
echo.
echo  Python:
%PY_CMD% --version
echo.
echo  Libs do bot:
%PY_CMD% -m pip show neonize 2>nul | findstr "Name Version"
%PY_CMD% -m pip show qrcode 2>nul | findstr "Name Version"
%PY_CMD% -m pip show httpx 2>nul | findstr "Name Version"
%PY_CMD% -m pip show psutil 2>nul | findstr "Name Version"
echo.
echo  FFmpeg:
ffmpeg -version 2>nul | findstr "ffmpeg version"
if errorlevel 1 echo  ^(nao instalado^)
echo.
pause
goto menu

:skills
cls
color 0B
echo.
echo  Skills disponiveis:
echo.
dir /b "%KIT_DIR%\bot\skills\*.py" | findstr /v "__"
echo.
echo  Total:
dir /b "%KIT_DIR%\bot\skills\*.py" | findstr /v "__" | find /c /v ""
echo.
pause
goto menu

:backup
cls
color 0E
set BTS=%date:~6,4%%date:~3,2%%date:~0,2%-%time:~0,2%%time:~3,2%
set BTS=%BTS: =0%
set BACKUP_DIR=%USERPROFILE%\Desktop\backup-linkbot-%BTS%
echo.
echo  Criando backup em: %BACKUP_DIR%
echo.
mkdir "%BACKUP_DIR%" 2>nul
xcopy /E /I /H /Y "%LINKBOT_DIR%" "%BACKUP_DIR%\linkbot-data" >nul 2>&1
xcopy /E /I /H /Y "%KIT_DIR%\config" "%BACKUP_DIR%\config" >nul 2>&1
echo  Backup completo.
echo.
pause
goto menu

:banco
cls
color 0B
echo.
if not exist "%LINKBOT_DIR%\data.db" (
    echo  Banco ainda nao criado. Rode o bot primeiro.
    pause
    goto menu
)
echo  Tamanho do banco:
dir "%LINKBOT_DIR%\data.db" | findstr "data.db"
echo.
echo  Localizacao: %LINKBOT_DIR%\data.db
echo.
echo  Pra inspecionar: instale "DB Browser for SQLite"
echo  https://sqlitebrowser.org/
echo.
pause
goto menu

:sair
cls
color 0A
echo.
echo  Boa jornada, aventureiro. Hyrule te aguarda. 
echo.
timeout /t 2 >nul
exit /b 0
