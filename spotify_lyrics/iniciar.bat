@echo off
chcp 65001 >nul
cd /d "%~dp0"

echo ============================================
echo  OSD Lyrics para Spotify
echo ============================================
echo.
echo  INSTRUCCIONES:
echo   1. Abre Spotify Desktop y pon una cancion a reproducir.
echo   2. La ventana OSD aparece en la parte inferior.
echo   3. Arrastra la ventana con el mouse para moverla.
echo   4. Clic derecho para ver opciones y buscar letras.
echo   5. Flechas del teclado para ajustar sincronizacion.
echo   6. Presiona ESC para cerrar.
echo.
echo  Si no se muestran letras, espera unos segundos
echo  mientras se buscan en internet.
echo.
echo Iniciando OSD Lyrics para Spotify...
echo.

uv run python main.py
if %errorlevel% neq 0 (
    echo.
    echo ERROR al iniciar.
    echo Si es la primera vez, ejecuta primero: instalar.bat
    echo.
    pause
)
