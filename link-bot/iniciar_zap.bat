@echo off
chcp 65001 >nul
title Link Bot - WhatsApp
cd /d "%~dp0"
echo  ===========================================
echo   LINK BOT - WhatsApp (TOTK + LLM)
echo  ===========================================
echo.
python -m bot.main
pause
