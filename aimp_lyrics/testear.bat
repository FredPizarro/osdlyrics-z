@echo off
chcp 65001 >nul
cd /d "%~dp0"

echo ============================================
echo  OSD Lyrics — Tests de diagnostico
echo ============================================
echo.

echo [1/3] Testeando parser LRC...
uv run python main.py --test-lrc
if %errorlevel% neq 0 (
    echo ERROR en el parser LRC.
    pause
    exit /b 1
)
echo.

echo [2/3] Buscando letras: "Bohemian Rhapsody" de Queen...
uv run python main.py --test-fetch "Bohemian Rhapsody" "Queen" --no-cache
echo.

echo [3/3] Buscando letras: "Blinding Lights" de The Weeknd...
uv run python main.py --test-fetch "Blinding Lights" "The Weeknd" --no-cache
echo.

echo ============================================
echo  Tests completados.
echo ============================================
pause
