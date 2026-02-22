@echo off
chcp 65001 >nul
cd /d "%~dp0"

echo ============================================
echo  OSD Spotify Lyrics — Tests
echo ============================================
echo.

echo [1/3] Probando parser LRC...
uv run python main.py --test-lrc
echo.

echo [2/3] Probando busqueda de letras...
uv run python main.py --test-fetch "Blinding Lights" "The Weeknd"
echo.

echo [3/3] Probando conexion con Spotify...
uv run python main.py --test-spotify
echo.

echo ============================================
echo  Tests completados.
echo ============================================
pause
