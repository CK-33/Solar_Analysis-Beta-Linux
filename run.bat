@echo off
title Sistema de Analise Fotovoltaica
echo ============================================
echo   Sistema de Analise Fotovoltaica
echo ============================================
echo.
echo Iniciando GUI...
echo.

cd /d "%~dp0"
python run_gui.py

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [ERRO] Falha ao iniciar. Verifique se o Python esta instalado.
    echo Instale as dependencias com: pip install -r requirements.txt
    pause
)
