@echo off
chcp 65001 > nul 2>&1
echo.
echo  +--------------------------------------------------+
echo  ^|   Claude Code - Finalizar Migracao              ^|
echo  ^|   Execute com Claude Code FECHADO               ^|
echo  +--------------------------------------------------+
echo.

set "SOURCE=%USERPROFILE%\.claude"
set "BACKUP=%USERPROFILE%\.claude_bak"
set "TARGET=C:\Users\OWNER\Agents\CLAUDE CODE\global"

REM Verifica se o global ja existe
if not exist "%TARGET%\" (
    echo  [ERRO] Pasta global nao encontrada: %TARGET%
    echo  Execute o Claude Code primeiro para copiar os arquivos.
    pause
    exit /b 1
)

REM Verifica se .claude ainda e diretorio real (nao junction)
fsutil reparsepoint query "%SOURCE%" > nul 2>&1
if not errorlevel 1 (
    echo  Junction ja existe em %SOURCE%
    echo  Migracao ja foi concluida!
    pause
    exit /b 0
)

REM Renomeia .claude para .claude_bak
echo  Renomeando %SOURCE% para %BACKUP% ...
rename "%SOURCE%" ".claude_bak"
if errorlevel 1 (
    echo  [ERRO] Nao foi possivel renomear .claude
    echo  Certifique-se de que o Claude Code esta FECHADO.
    pause
    exit /b 1
)

REM Cria junction
echo  Criando junction: %SOURCE% -^> %TARGET%
mklink /J "%SOURCE%" "%TARGET%"
if errorlevel 1 (
    echo  [ERRO] Falha ao criar junction. Revertendo...
    rename "%BACKUP%" ".claude"
    pause
    exit /b 1
)

echo.
echo  [OK] Migracao concluida com sucesso!
echo  ~/.claude agora aponta para: %TARGET%
echo  Backup original em: %BACKUP%
echo.
pause
