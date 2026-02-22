import os
import logging
import threading
from pathlib import Path

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Cargar credenciales desde .env
# ─────────────────────────────────────────────────────────────────────────────
_ENV_FILE = Path(__file__).parent / ".env"

def _load_env():
    """Carga variables desde .env (usa python-dotenv si está disponible)."""
    try:
        from dotenv import load_dotenv
        load_dotenv(_ENV_FILE)
    except ImportError:
        # Parseo manual si python-dotenv no está instalado
        if _ENV_FILE.exists():
            with open(_ENV_FILE, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        key, _, val = line.partition("=")
                        os.environ.setdefault(key.strip(), val.strip())

_load_env()

CLIENT_ID     = os.environ.get("SPOTIFY_CLIENT_ID", "").strip()
CLIENT_SECRET = os.environ.get("SPOTIFY_CLIENT_SECRET", "").strip()

REDIRECT_URI = "http://127.0.0.1:9090/callback"
SCOPE        = "user-read-playback-state user-read-currently-playing"
CACHE_PATH   = str(Path(__file__).parent / ".spotify_cache")
# ─────────────────────────────────────────────────────────────────────────────


class SpotifyConnector:
    """
    Conector con Spotify Desktop via Spotify Web API usando spotipy.

    Flujos de autenticación (en orden de preferencia):
      1. OAuth estándar  — si SPOTIFY_CLIENT_SECRET está en .env
      2. PKCE            — si solo SPOTIFY_CLIENT_ID está en .env (sin secret)
      3. Fallback ventana— si no hay CLIENT_ID o spotipy falla
    """

    def __init__(self):
        self._sp = None
        self._lock = threading.Lock()
        self._use_window_fallback = False
        self._try_connect()

    def _try_connect(self):
        """Intenta conectar con la Spotify Web API."""
        if not CLIENT_ID or CLIENT_ID == "TU_CLIENT_ID_AQUI":
            logger.warning(
                "SPOTIFY_CLIENT_ID no configurado en .env\n"
                "  → Usando fallback de ventana Windows (sin posición de reproducción).\n"
                "  Para activar letras sincronizadas:\n"
                "  1. Edita spotify_lyrics/.env\n"
                "  2. Agrega: SPOTIFY_CLIENT_ID=tu_client_id\n"
                "  3. Obtén el ID en: https://developer.spotify.com/dashboard"
            )
            self._use_window_fallback = True
            return

        try:
            import spotipy

            if CLIENT_SECRET:
                # Flujo OAuth estándar (con client secret)
                from spotipy.oauth2 import SpotifyOAuth
                auth = SpotifyOAuth(
                    client_id=CLIENT_ID,
                    client_secret=CLIENT_SECRET,
                    redirect_uri=REDIRECT_URI,
                    scope=SCOPE,
                    cache_path=CACHE_PATH,
                    open_browser=True,
                )
                logger.info("Usando autenticación OAuth estándar (con client secret).")
            else:
                # Flujo PKCE (sin client secret)
                from spotipy.oauth2 import SpotifyPKCE
                auth = SpotifyPKCE(
                    client_id=CLIENT_ID,
                    redirect_uri=REDIRECT_URI,
                    scope=SCOPE,
                    cache_path=CACHE_PATH,
                    open_browser=True,
                )
                logger.info("Usando autenticación PKCE (sin client secret).")

            with self._lock:
                self._sp = spotipy.Spotify(auth_manager=auth)
            self._sp.current_user()
            logger.info("Conectado a Spotify Web API ✓")

        except ImportError:
            logger.warning(
                "spotipy no está instalado. Usando fallback de ventana Windows.\n"
                "  Instala con: uv pip install spotipy"
            )
            self._use_window_fallback = True
        except Exception as e:
            logger.warning("Error conectando a Spotify API: %s. Usando fallback.", e)
            self._use_window_fallback = True

    @property
    def is_connected(self) -> bool:
        return self._sp is not None or self._use_window_fallback

    @property
    def has_position(self) -> bool:
        """True si la conexión provee posición de reproducción (API completa)."""
        return self._sp is not None

    def get_state(self):
        """
        Retorna (state_str, info_dict, position_ms).

        state_str: 'playing', 'paused', 'stopped', 'error'
        info_dict: dict con keys 'title', 'artist', 'album', 'duration'
        position_ms: posición en milisegundos (0 si no disponible)
        """
        if self._sp is not None:
            return self._get_state_api()
        elif self._use_window_fallback:
            return self._get_state_window()
        return 'error', {}, 0

    def _get_state_api(self):
        """Obtiene estado desde la Spotify Web API."""
        try:
            with self._lock:
                pb = self._sp.current_playback()

            if pb is None:
                return 'stopped', {}, 0

            is_playing = pb.get('is_playing', False)
            state = 'playing' if is_playing else 'paused'

            item = pb.get('item') or {}
            title = item.get('name', '')
            artists = item.get('artists', [])
            artist = ', '.join(a['name'] for a in artists) if artists else ''
            album_obj = item.get('album') or {}
            album = album_obj.get('name', '')
            duration = item.get('duration_ms', 0)
            position = pb.get('progress_ms', 0)

            info = {
                'title': title,
                'artist': artist,
                'album': album,
                'duration': duration
            }
            return state, info, position

        except Exception as e:
            logger.warning("Error obteniendo estado de Spotify API: %s", e)
            self._sp = None
            self._try_connect()
            return 'error', {}, 0

    def _get_state_window(self):
        """
        Fallback: lee SOLO la ventana principal de Spotify en Windows.
        1. Obtiene PIDs de Spotify.exe via tasklist
        2. Verifica exe con QueryFullProcessImageNameW (no requiere privilegios elevados)
        3. Acepta solo ventanas de nivel superior con formato "Artista - Título"
        No provee posición de reproducción.
        """
        try:
            import subprocess
            import ctypes
            import ctypes.wintypes
            import win32gui
            import win32process

            # ── 1. Obtener PIDs de Spotify.exe via tasklist ──────────────────
            si = subprocess.STARTUPINFO()
            si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            result = subprocess.run(
                ['tasklist', '/FI', 'IMAGENAME eq Spotify.exe', '/FO', 'CSV', '/NH'],
                capture_output=True, text=True, startupinfo=si
            )

            if 'Spotify.exe' not in result.stdout:
                return 'stopped', {}, 0

            # CSV: "Spotify.exe","PID","Console","1","N,NNN K"
            spotify_pids = set()
            for line in result.stdout.strip().splitlines():
                line = line.strip()
                if not line:
                    continue
                cols = line.split(',')
                if len(cols) >= 2:
                    try:
                        spotify_pids.add(int(cols[1].strip('"').strip()))
                    except ValueError:
                        pass

            if not spotify_pids:
                return 'stopped', {}, 0

            # ── 2. Helper: verificar exe usando QueryFullProcessImageNameW ────
            # PROCESS_QUERY_LIMITED_INFORMATION = 0x1000 (no requiere elevación)
            PROCESS_QUERY_LIMITED = 0x1000
            kernel32 = ctypes.windll.kernel32

            _verified_pids: set = set()   # cache de PIDs ya verificados como Spotify

            def _is_spotify_pid(pid: int) -> bool:
                if pid in _verified_pids:
                    return True
                try:
                    hproc = kernel32.OpenProcess(PROCESS_QUERY_LIMITED, False, pid)
                    if not hproc:
                        return False
                    buf = ctypes.create_unicode_buffer(1024)
                    size = ctypes.wintypes.DWORD(1024)
                    ok = kernel32.QueryFullProcessImageNameW(hproc, 0, buf, ctypes.byref(size))
                    kernel32.CloseHandle(hproc)
                    if ok and buf.value.lower().endswith('\\spotify.exe'):
                        _verified_pids.add(pid)
                        return True
                    return False
                except Exception:
                    return False

            # ── 3. Enumerar ventanas top-level de Spotify.exe ────────────────
            spotify_titles = []

            def _on_window(hwnd, _):
                try:
                    if not win32gui.IsWindowVisible(hwnd):
                        return True
                    # Solo ventanas de nivel superior (sin owner/parent)
                    if win32gui.GetParent(hwnd) or win32gui.GetWindow(hwnd, 4):  # GW_OWNER=4
                        return True

                    _, pid = win32process.GetWindowThreadProcessId(hwnd)
                    if pid not in spotify_pids:
                        return True  # proceso distinto → ignorar

                    if not _is_spotify_pid(pid):
                        return True  # exe no es Spotify.exe → ignorar

                    title = win32gui.GetWindowText(hwnd)
                    if not title or not title.strip():
                        return True

                    # ── Verificaciones de formato de título ─────────────────
                    # Spotify siempre muestra EXACTAMENTE "Artista - Título" (1 separador).
                    # Editores/navegadores siempre tienen 2+ separadores:
                    #   Cursor:  "archivo.ts - proyecto - Cursor"
                    #   VS Code: "archivo.py - carpeta - Visual Studio Code"
                    #   Chrome:  "Página - Sitio - Chrome"
                    sep_count = title.count(' - ')
                    if sep_count != 1:
                        return True  # 0 = "Spotify" (pausa), 2+ = editor/browser → skip

                    # Rechazar si termina con nombre de editor/navegador conocido
                    _BAD_SUFFIXES = (
                        ' - Cursor', ' - Visual Studio Code', ' - Code',
                        ' - Chrome', ' - Firefox', ' - Edge', ' - Brave',
                        ' - Opera', ' - Safari', ' - Notepad', ' - Notepad++',
                        ' - Sublime Text', ' - Atom', ' - IntelliJ IDEA',
                        ' - PyCharm', ' - WebStorm', ' - Explorer',
                    )
                    if any(title.endswith(s) for s in _BAD_SUFFIXES):
                        return True

                    logger.debug("Ventana Spotify: %r (pid=%d)", title, pid)
                    spotify_titles.append(title)
                except Exception:
                    pass
                return True

            win32gui.EnumWindows(_on_window, None)

            # ── 4. Interpretar resultado ─────────────────────────────────────
            if not spotify_titles:
                return 'paused', {}, 0

            raw_title = spotify_titles[0]
            segs = raw_title.split(' - ', 1)
            if len(segs) == 2:
                artist, title = segs[0].strip(), segs[1].strip()
            else:
                artist, title = '', raw_title.strip()

            info = {'title': title, 'artist': artist, 'album': '', 'duration': 0}
            return 'playing', info, 0

        except ImportError:
            logger.warning("pywin32 no instalado — fallback de ventana no disponible.")
            return 'error', {}, 0
        except Exception as e:
            logger.warning("Error leyendo ventana de Spotify: %s", e)
            return 'error', {}, 0

    def get_position(self) -> int:
        """
        Retorna la posición de reproducción en ms.
        Solo disponible con la API completa (no en fallback de ventana).
        """
        if self._sp is not None:
            try:
                with self._lock:
                    pb = self._sp.current_playback()
                return pb.get('progress_ms', 0) if pb else 0
            except Exception:
                pass
        return 0
