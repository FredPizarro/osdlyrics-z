@echo off
chcp 65001 >nul
cd /d "%~dp0"

echo ============================================
echo  OSD Lyrics para Spotify — Instalador
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

echo Creando entorno virtual...
uv venv .venv
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
echo SIGUIENTE PASO (para letras sincronizadas con posicion):
echo.
echo  1. Ve a https://developer.spotify.com/dashboard
echo  2. Crea una app (gratis) con Redirect URI: http://127.0.0.1:9090/callback
echo  3. Copia tu Client ID
echo  4. Abre spotify_connector.py y reemplaza TU_CLIENT_ID_AQUI
echo.
echo Si no configuras el Client ID, el programa funcionara en modo
echo basico (detecta cancion pero sin sincronizacion de posicion).
echo.
echo Ahora puedes ejecutar:
echo   iniciar.bat    - Lanza el OSD de letras
echo   testear.bat    - Prueba la conexion con Spotify
echo.
pause
