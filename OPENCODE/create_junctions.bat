@echo off
chcp 65001 > nul 2>&1

set "BASE=C:\Users\OWNER\Agents\OPENCODE"

echo Criando junctions do OpenCode...
echo.

mklink /J "%USERPROFILE%\.config\opencode"           "%BASE%\plugin"
mklink /J "%USERPROFILE%\.local\share\opencode"      "%BASE%\data"
mklink /J "%USERPROFILE%\.local\state\opencode"      "%BASE%\state"
mklink /J "%USERPROFILE%\.cache\opencode"            "%BASE%\cache"
mklink /J "%APPDATA%\opencode"                       "%BASE%\roaming"

echo.
echo Verificando...
dir "%USERPROFILE%\.config\" | findstr opencode
dir "%USERPROFILE%\.local\share\" | findstr opencode
dir "%APPDATA%" | findstr opencode
echo.
echo Concluido.
