# -*- coding: utf-8 -*-
"""
Buscador y descargador de letras LRC.
Soporta múltiples fuentes:
  1. lrclib.net  (API pública, sin key)
  2. NetEase Music (music.163.com)

La caché local se guarda en C:\Lyrics (compartida con aimp_lyrics)
"""

import hashlib
import json
import logging
import os
import re
import urllib.parse
import urllib.request
import urllib.error
from pathlib import Path

logger = logging.getLogger(__name__)

# Directorio de caché (compartida con aimp_lyrics)
CACHE_DIR = Path(r'C:\Lyrics')
CACHE_DIR.mkdir(parents=True, exist_ok=True)

# Archivo de asociaciones: mapea "title||artist" del reproductor -> ruta de archivo LRC
ASSOCIATIONS_FILE = CACHE_DIR / 'spotify_associations.json'

HEADERS = {
    'User-Agent': 'OSDLyricsSpotify/1.0 (Windows; compatible)',
    'Accept': 'application/json',
}


def sanitize_filename(name: str) -> str:
    """Elimina caracteres inválidos para nombres de archivo en Windows."""
    return re.sub(r'[<>:"/\\|?*]', '_', name).strip()

def _cache_path(title: str, artist: str) -> Path:
    if artist:
        name = f"{artist} - {title}"
    else:
        name = title
    return CACHE_DIR / (sanitize_filename(name) + '.lrc')

def _cache_key(title: str, artist: str) -> str:
    raw = f"{title.lower().strip()}||{artist.lower().strip()}"
    return hashlib.md5(raw.encode('utf-8')).hexdigest()

def _load_associations() -> dict:
    if ASSOCIATIONS_FILE.exists():
        try:
            return json.loads(ASSOCIATIONS_FILE.read_text(encoding='utf-8'))
        except Exception:
            pass
    return {}

def _save_associations(assoc: dict):
    try:
        ASSOCIATIONS_FILE.write_text(json.dumps(assoc, indent=2, ensure_ascii=False), encoding='utf-8')
    except Exception as e:
        logger.warning("Error guardando asociaciones: %s", e)

def save_association(title: str, artist: str, lrc_path: str):
    """Asocia una pista de Spotify con una ruta de archivo LRC."""
    key = f"{title}||{artist}"
    assoc = _load_associations()
    assoc[key] = lrc_path
    _save_associations(assoc)
    logger.info("Asociación guardada: '%s' -> %s", key, lrc_path)

def _load_from_association(title: str, artist: str):
    """Intenta cargar LRC desde asociación previa (última selección manual)."""
    key = f"{title}||{artist}"
    assoc = _load_associations()
    lrc_path = assoc.get(key)
    if lrc_path:
        p = Path(lrc_path)
        if p.exists():
            try:
                content = p.read_text(encoding='utf-8')
                logger.info("Letras cargadas desde asociación: '%s' -> %s", key, lrc_path)
                return content
            except Exception as e:
                logger.warning("Error leyendo asociación: %s", e)
        else:
            logger.info("Archivo asociado ya no existe, limpiando: %s", lrc_path)
            del assoc[key]
            _save_associations(assoc)
    return None

def _load_cache(title: str, artist: str):
    # 0. Intentar cargar desde asociación (última selección manual)
    from_assoc = _load_from_association(title, artist)
    if from_assoc:
        return from_assoc

    # 1. Intentar cargar con nombre legible
    path = _cache_path(title, artist)
    if path.exists():
        try:
            return path.read_text(encoding='utf-8')
        except Exception as e:
            logger.warning("Error leyendo caché legible: %s", e)

    # 2. Fallback: intentar cargar formato antiguo (MD5 hash)
    old_hash = _cache_key(title, artist)
    old_path = CACHE_DIR / (old_hash + '.lrc')
    if old_path.exists():
        try:
            return old_path.read_text(encoding='utf-8')
        except: pass

    return None


def search_local_lyrics(query: str) -> list[dict]:
    """Busca archivos LRC locales (por nombre o contenido)."""
    results = []
    query_norm = query.lower().strip()
    if not CACHE_DIR.exists(): return []

    try:
        for file in CACHE_DIR.glob("*.lrc"):
            # 1. Buscar por nombre de archivo (rápido)
            if query_norm in file.stem.lower():
                parts = file.stem.split(' - ', 1)
                if len(parts) == 2:
                    ar, ti = parts[0], parts[1]
                else:
                    ar, ti = "Desconocido", file.stem

                results.append({
                    'source': 'Local',
                    'artist': ar,
                    'title': ti,
                    'id': str(file),
                    'album': ''
                })
                continue

            # 2. Buscar en contenido
            try:
                content = file.read_text(encoding='utf-8', errors='ignore')
                if query_norm in content.lower():
                    ti = "Desconocido"
                    ar = "Desconocido"
                    for line in content.splitlines()[:10]:
                        if line.startswith('[ti:'): ti = line[4:-1]
                        if line.startswith('[ar:'): ar = line[4:-1]

                    results.append({
                        'source': 'Local',
                        'artist': ar,
                        'title': ti,
                        'id': str(file),
                        'album': ''
                    })
            except: pass
    except Exception as e:
        logger.error("Error buscando local: %s", e)
    return results


def save_cache_file(title: str, artist: str, lrc_content: str):
    try:
        path = _cache_path(title, artist)
        path.write_text(lrc_content, encoding='utf-8')
        logger.info("Letras guardadas en caché: %s", path)
    except Exception as e:
        logger.warning("Error guardando caché: %s", e)


def _http_get(url: str, extra_headers: dict = None, timeout: int = 10):
    """HTTP GET simple con manejo de errores."""
    headers = dict(HEADERS)
    if extra_headers:
        headers.update(extra_headers)
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, resp.read()
    except urllib.error.HTTPError as e:
        return e.code, b''
    except Exception as e:
        logger.error("Error HTTP GET %s: %s", url, e)
        return 0, b''


def _http_post(url: str, data: bytes, extra_headers: dict = None, timeout: int = 10):
    """HTTP POST simple."""
    headers = dict(HEADERS)
    headers['Content-Type'] = 'application/x-www-form-urlencoded'
    if extra_headers:
        headers.update(extra_headers)
    req = urllib.request.Request(url, data=data, headers=headers, method='POST')
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, resp.read()
    except urllib.error.HTTPError as e:
        return e.code, b''
    except Exception as e:
        logger.error("Error HTTP POST %s: %s", url, e)
        return 0, b''


# ──────────────────────────────────────────────────────────────
# Fuente 1: lrclib.net (API pública, retorna LRC sincronizado)
# ──────────────────────────────────────────────────────────────

def fetch_from_lrclib(title: str, artist: str, album: str = '', duration_s: int = 0) -> str | None:
    """
    Busca letras en lrclib.net.
    Retorna el contenido LRC (str) o None si no se encuentra.
    """
    params = {'track_name': title, 'artist_name': artist}
    if album:
        params['album_name'] = album
    if duration_s > 0:
        params['duration'] = duration_s

    url = 'https://lrclib.net/api/get?' + urllib.parse.urlencode(params)
    logger.info("[lrclib] GET %s", url)
    status, body = _http_get(url)

    if status == 200:
        try:
            data = json.loads(body.decode('utf-8'))
            synced_lrc = data.get('syncedLyrics') or data.get('plainLyrics')
            if synced_lrc:
                logger.info("[lrclib] Letras encontradas para '%s - %s'", artist, title)
                return synced_lrc
        except Exception as e:
            logger.warning("[lrclib] Error parseando respuesta: %s", e)
    elif status == 404:
        logger.info("[lrclib] No encontrado: '%s - %s'", artist, title)
    else:
        logger.warning("[lrclib] Respuesta inesperada %d para '%s - %s'", status, artist, title)

    return None


# ──────────────────────────────────────────────────────────────
# Fuente 2: NetEase Music (music.163.com)
# ──────────────────────────────────────────────────────────────

NETEASE_SEARCH_URL = 'https://music.163.com/api/search/get'
NETEASE_LYRIC_URL  = 'https://music.163.com/api/song/lyric'
NETEASE_HEADERS    = {
    'Referer': 'https://music.163.com/',
    'Origin':  'https://music.163.com',
}


def _netease_search(title: str, artist: str) -> list[dict]:
    params = f's={urllib.parse.quote(title + " " + artist)}&type=1&limit=10'
    status, body = _http_post(
        NETEASE_SEARCH_URL,
        params.encode('utf-8'),
        extra_headers=NETEASE_HEADERS
    )
    if status != 200:
        return []
    try:
        parsed = json.loads(body.decode('utf-8'))
        return parsed.get('result', {}).get('songs', [])
    except Exception as e:
        logger.warning("[netease] Error parseando búsqueda: %s", e)
        return []


def _netease_get_lyric(song_id: int) -> str | None:
    url = f"{NETEASE_LYRIC_URL}?id={song_id}&lv=-1&kv=-1&tv=-1"
    status, body = _http_get(url, extra_headers=NETEASE_HEADERS)
    if status != 200:
        return None
    try:
        parsed = json.loads(body.decode('utf-8'))
        if 'nolyric' in parsed or 'uncollected' in parsed:
            return None
        return parsed.get('lrc', {}).get('lyric')
    except Exception as e:
        logger.warning("[netease] Error parseando letra: %s", e)
        return None


def fetch_from_netease(title: str, artist: str) -> str | None:
    """
    Busca letras en NetEase Music.
    Retorna el contenido LRC o None.
    """
    songs = _netease_search(title, artist)
    if not songs:
        logger.info("[netease] Sin resultados para '%s - %s'", artist, title)
        return None

    best = None
    for song in songs:
        song_title = song.get('name', '').lower()
        song_artist = ''
        if song.get('artists'):
            song_artist = song['artists'][0].get('name', '').lower()
        if title.lower() in song_title and artist.lower() in song_artist:
            best = song
            break
    if best is None:
        best = songs[0]

    lrc = _netease_get_lyric(best['id'])
    if lrc:
        logger.info("[netease] Letras encontradas para '%s - %s'", artist, title)
    return lrc


# ──────────────────────────────────────────────────────────────
# Función principal de búsqueda
# ──────────────────────────────────────────────────────────────

def get_lyrics(title: str, artist: str, album: str = '',
               duration_ms: int = 0, use_cache: bool = True) -> str | None:
    """
    Busca letras LRC para una canción.

    Orden de búsqueda:
      1. Caché local
      2. lrclib.net
      3. NetEase Music

    Args:
        title:       Título de la canción
        artist:      Artista
        album:       Álbum (opcional, mejora búsqueda en lrclib)
        duration_ms: Duración en ms (opcional)
        use_cache:   Si True, consulta la caché local primero

    Returns:
        Contenido LRC como str, o None si no se encontraron letras.
    """
    if not title:
        return None

    # 1. Caché local
    if use_cache:
        cached = _load_cache(title, artist)
        if cached:
            logger.info("Letras cargadas desde caché para '%s - %s'", artist, title)
            return cached

    duration_s = duration_ms // 1000 if duration_ms > 0 else 0

    # 2. lrclib.net
    lrc = fetch_from_lrclib(title, artist, album, duration_s)

    # 3. NetEase
    if lrc is None:
        lrc = fetch_from_netease(title, artist)

    # Guardar en caché si se encontró algo
    if lrc and use_cache:
        save_cache_file(title, artist, lrc)

    return lrc


# ──────────────────────────────────────────────────────────────
# Funciones de Búsqueda Manual (para el diálogo de búsqueda)
# ──────────────────────────────────────────────────────────────

def search_online_lyrics(query: str) -> list[dict]:
    """Busca en múltiples fuentes y retorna lista unificada."""
    results = []

    # 1. LRCLIB
    try:
        url = f"https://lrclib.net/api/search?q={urllib.parse.quote(query)}"
        status, body = _http_get(url)
        if status == 200:
            data = json.loads(body)
            for item in data:
                if not item.get('syncedLyrics'): continue
                results.append({
                    'source': 'LRCLIB',
                    'artist': item.get('artistName'),
                    'title': item.get('trackName'),
                    'album': item.get('albumName'),
                    'duration': item.get('duration'),
                    'id': f"lrclib:{item.get('id')}",
                    'rating': '-',
                    'downloads': '-'
                })
    except Exception as e:
        logger.error("Error buscando LRCLIB: %s", e)

    # 2. NetEase
    try:
        netease_songs = _netease_search(query, "")
        for song in netease_songs:
            ar = song['artists'][0]['name'] if song.get('artists') else 'Unknown'
            al = song['album']['name'] if song.get('album') else ''

            results.append({
                'source': 'NetEase',
                'artist': ar,
                'title': song.get('name'),
                'album': al,
                'duration': song.get('duration', 0) / 1000,
                'id': f"netease:{song.get('id')}",
                'rating': '★' * (song.get('popularity', 0) // 20),
                'downloads': '-'
            })
    except Exception as e:
        logger.error("Error buscando NetEase: %s", e)

    return results

def download_lyric_by_id(lyric_id: str) -> str | None:
    """Descarga por ID prefijado (lrclib:123 o netease:456)."""
    try:
        source, real_id = lyric_id.split(':', 1)

        if source == 'lrclib':
            url = f"https://lrclib.net/api/get/{real_id}"
            status, body = _http_get(url)
            if status == 200:
                data = json.loads(body)
                return data.get('syncedLyrics')

        elif source == 'netease':
            return _netease_get_lyric(int(real_id))

    except Exception as e:
        logger.error("Error descargando ID %s: %s", lyric_id, e)
    return None
