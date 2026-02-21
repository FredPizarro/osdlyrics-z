@echo off
chcp 65001 >nul
cd /d "%~dp0"

echo ============================================
echo  OSD Lyrics para AIMP
echo ============================================
echo.
echo  INSTRUCCIONES:
echo   1. Abre AIMP y pon una cancion a reproducir.
echo   2. La ventana OSD aparece en la parte inferior.
echo   3. Arrastra la ventana con el mouse para moverla.
echo   4. Presiona ESC para cerrar.
echo.
echo  Si no se muestran letras, espera unos segundos
echo  mientras se buscan en internet.
echo.
echo Iniciando OSD Lyrics...
echo.

uv run python main.py
if %errorlevel% neq 0 (
    echo.
    echo ERROR al iniciar.
    echo Si es la primera vez, ejecuta primero: instalar.bat
    echo.
    pause
)
