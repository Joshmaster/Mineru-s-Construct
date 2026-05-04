@echo off
setlocal EnableDelayedExpansion

echo.
echo  ==========================================
echo   Hyrule - Instalador
echo  ==========================================
echo.

set SCRIPT_DIR=%~dp0
set CLAUDE_DIR=%USERPROFILE%\.claude
set BIN_DIR=%CLAUDE_DIR%\bin

REM Verifica Python
python --version > nul 2>&1
if errorlevel 1 (
    echo  [ERRO] Python nao encontrado. Instale em https://python.org
    pause & exit /b 1
)
for /f "tokens=*" %%v in ('python --version 2^>^&1') do echo  Python: %%v

REM Instala dependencias Python
echo.
echo  Instalando dependencias Python...
pip install flask requests pyyaml -q --disable-pip-version-check
if errorlevel 1 (
    echo  [ERRO] Falha ao instalar dependencias.
    pause & exit /b 1
)
echo  Dependencias: OK

REM Cria pastas
if not exist "%CLAUDE_DIR%" mkdir "%CLAUDE_DIR%"
if not exist "%BIN_DIR%"    mkdir "%BIN_DIR%"

REM Copia proxy.py
if not exist "%SCRIPT_DIR%proxy.py" (
    echo  [ERRO] proxy.py nao encontrado em %SCRIPT_DIR%
    pause & exit /b 1
)
copy /y "%SCRIPT_DIR%proxy.py" "%CLAUDE_DIR%\proxy.py" > nul
echo  proxy.py copiado para %CLAUDE_DIR%

REM Copia link.bat para bin\
if not exist "%SCRIPT_DIR%link.bat" (
    echo  [ERRO] link.bat nao encontrado em %SCRIPT_DIR%
    pause & exit /b 1
)
copy /y "%SCRIPT_DIR%link.bat" "%BIN_DIR%\link.bat" > nul
echo  link.bat copiado para %BIN_DIR%

REM Copia HYRULE.md (preserva se ja existir)
if not exist "%CLAUDE_DIR%\HYRULE.md" (
    if exist "%SCRIPT_DIR%HYRULE.md" (
        copy /y "%SCRIPT_DIR%HYRULE.md" "%CLAUDE_DIR%\HYRULE.md" > nul
        echo  HYRULE.md copiado para %CLAUDE_DIR%
    ) else (
        echo  [AVISO] HYRULE.md nao encontrado. Crie em %CLAUDE_DIR%
    )
) else (
    echo  HYRULE.md ja existe, mantido sem alteracoes
)

REM Adiciona bin\ ao PATH do usuario
echo %PATH% | findstr /i "%BIN_DIR%" > nul 2>&1
if not errorlevel 1 (
    echo  PATH: %BIN_DIR% ja no PATH
    goto :done
)

for /f "tokens=2*" %%a in ('reg query "HKCU\Environment" /v PATH 2^>nul') do set "CURRENT_PATH=%%b"
if "!CURRENT_PATH!"=="" (
    set "NEW_PATH=%BIN_DIR%"
) else (
    set "NEW_PATH=!CURRENT_PATH!;%BIN_DIR%"
)
reg add "HKCU\Environment" /v PATH /t REG_EXPAND_SZ /d "!NEW_PATH!" /f > nul
echo  PATH: %BIN_DIR% adicionado

:done
echo.
echo  ==========================================
echo   Instalacao concluida!
echo  ==========================================
echo   Abra um NOVO terminal e digite: link
echo  ==========================================
echo.
pause