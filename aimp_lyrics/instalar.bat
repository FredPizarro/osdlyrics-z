@echo off
chcp 65001 >nul
cd /d "%~dp0"

echo ============================================
echo  OSD Lyrics para AIMP — Instalador
echo ============================================
echo.

:: Verificar que uv este instalado
uv --version >nul 2>&1
if %errorlevel% neq 0 (
    echo ERROR: uv no esta instalado.
    echo Instalalo con:
    echo   powershell -c "irm https://astral.sh/uv/install.ps1 | iex"
    echo.
    pause
    exit /b 1
)

echo uv encontrado:
uv --version
echo.

echo Instalando dependencias...
uv pip install -r requirements.txt
if %errorlevel% neq 0 (
    echo.
    echo ERROR: No se pudieron instalar las dependencias.
    pause
    exit /b 1
)

echo.
echo ============================================
echo  Instalacion completada exitosamente!
echo ============================================
echo.
echo Ahora puedes ejecutar:
echo   iniciar.bat   - Lanza el OSD de letras
echo   testear.bat   - Prueba el parser y la busqueda
echo.
pause
