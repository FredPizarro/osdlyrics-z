# OSD Lyrics — Spotify Desktop 🎵

Visualizador de letras sincronizadas (karaoke) para **Spotify Desktop en Windows**.

Sibling project de [aimp_lyrics](../aimp_lyrics), con la misma arquitectura pero conectado a Spotify.

---

## Características

- 🎵 **Letras sincronizadas** al milisegundo (requiere Spotify Web API)
- 🪟 **Modo fallback** sin configuración: detecta la canción por título de ventana
- 🔍 **Buscador integrado** — busca en `lrclib.net` y `NetEase Music`
- 💾 **Caché local** en `C:\Lyrics` (compartida con aimp_lyrics)
- 🎨 **Ventana OSD transparente** siempre encima, estilo karaoke
- ⚙️ **Múltiples métodos de inicio**: arrastrable, configurable (fuente, color, opacidad)
- ⌨️ **Atajos de teclado** para ajustar sincronización en tiempo real
- 🔗 **Asociaciones persistentes**: recuerda qué letra elegiste para cada canción

---

## Instalación

### Paso 1 — Instalar dependencias

```bat
instalar.bat
```

O manualmente:
```powershell
uv pip install -r requirements.txt
```

### Paso 2 — (Opcional pero recomendado) Configurar Spotify Web API

Para tener letras **sincronizadas al milisegundo** (con posición de reproducción real):

1. Ve a [developer.spotify.com/dashboard](https://developer.spotify.com/dashboard)
2. Crea una **app gratuita**
3. En *Edit Settings*, agrega como **Redirect URI**: `http://127.0.0.1:9090/callback`
4. Copia tu **Client ID**
5. Abre `spotify_connector.py` y reemplaza la línea:
   ```python
   CLIENT_ID = "TU_CLIENT_ID_AQUI"
   ```
   con tu Client ID real.

> **Sin Client ID:** El programa funciona en **modo fallback**, detectando la canción por el título de ventana de Spotify. Las letras se muestran pero sin sincronización de posición.

---

## Uso

```bat
iniciar.bat         # Lanza el OSD
testear.bat         # Ejecuta todos los tests
```

O con Python directamente:
```powershell
uv run python main.py                              # Lanzar OSD
uv run python main.py --test-lrc                   # Probar parser LRC
uv run python main.py --test-fetch "Blinding Lights" "The Weeknd"
uv run python main.py --test-spotify               # Probar conexión Spotify
uv run python main.py --debug                      # Modo debug
```

---

## Controles

| Acción | Control |
|--------|---------|
| Mover ventana | Arrastrar con ratón |
| Menú opciones | Clic derecho |
| Buscar letra manualmente | Clic derecho → Buscar Letra... |
| Adelantar letra 0.5s | ↑ o → |
| Atrasar letra 0.5s | ↓ o ← |
| Cerrar | ESC |

---

## Estructura del proyecto

```
spotify_lyrics/
├── main.py                # Punto de entrada (CLI)
├── osd_window.py          # Ventana OSD principal (Tkinter)
├── spotify_connector.py   # Conector Spotify (API + fallback ventana)
├── lyrics_fetcher.py      # Buscador de letras (lrclib.net + NetEase)
├── lrc_parser.py          # Parser de archivos LRC
├── config.json            # Configuración visual (auto-generado)
├── requirements.txt       # Dependencias Python
├── pyproject.toml         # Configuración de proyecto (uv)
├── iniciar.bat            # Script de inicio
├── instalar.bat           # Script de instalación
└── testear.bat            # Script de tests
```

---

## Modos de operación

### Modo API (recomendado)
Requiere `CLIENT_ID` configurado en `spotify_connector.py`.

- Usa `spotipy` + OAuth PKCE (sin client secret)
- La primera vez abre el navegador para autenticarse
- El token se guarda en `.spotify_cache` para sesiones futuras
- Provee **posición real** de reproducción → letras perfectamente sincronizadas

### Modo Fallback (ventana Windows)
Funciona sin ninguna configuración adicional.

- Lee el título de la ventana de Spotify (`Artista - Título`)
- Detecta cambios de canción automáticamente
- **Sin posición**: muestra las letras pero no las sincroniza con el audio
- Útil para ver la letra mientras escuchas

---

## Caché de letras

Las letras descargadas se guardan en `C:\Lyrics\` como archivos `.lrc`:
```
C:\Lyrics\
├── The Weeknd - Blinding Lights.lrc
├── Queen - Bohemian Rhapsody.lrc
├── spotify_associations.json    ← recuerda tus selecciones manuales
└── ...
```

> La caché es **compartida con aimp_lyrics** — si ya descargaste letras con el módulo AIMP, Spotify las usará también (y viceversa).

---

## Diferencias respecto a aimp_lyrics

| Característica | aimp_lyrics | spotify_lyrics |
|---|---|---|
| Reproductor | AIMP Desktop | Spotify Desktop |
| Librería | `pyaimp` | `spotipy` (+ fallback ventana) |
| Posición | Siempre disponible | Solo con API configurada |
| Auth | No requiere | OAuth PKCE (o ninguna en fallback) |
| Color OSD | Amarillo `#FFE566` | Verde Spotify `#1DB954` |
| Caché | `associations.json` | `spotify_associations.json` |
