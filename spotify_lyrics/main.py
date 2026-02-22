# -*- coding: utf-8 -*-
"""
main.py — Punto de entrada para OSD Lyrics + Spotify Desktop en Windows.

Uso:
    python main.py [opciones]

Opciones:
    --test-lrc          Testea el parser LRC
    --test-fetch TITLE ARTIST
                        Busca letras de una canción y las imprime
    --no-cache          Desactiva la caché de letras
    --debug             Activa logging detallado
    (sin argumentos)    Lanza la ventana OSD
"""

import argparse
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))


def cmd_test_lrc():
    """Prueba básica del parser LRC."""
    from lrc_parser import parse_lrc, get_line_at
    test_content = """\
[ti:Test Song]
[ar:Test Artist]
[al:Test Album]
[00:01.00]Primera línea de prueba
[00:05.50]Segunda línea de prueba
[00:10.00]Tercera línea de prueba
[00:15.25]Cuarta línea de prueba
[00:20.00]Fin de la canción
"""
    print("=== Test del Parser LRC ===")
    attrs, lyrics = parse_lrc(test_content)
    print(f"Atributos: {attrs}")
    print(f"Total líneas: {len(lyrics)}")
    for line in lyrics:
        ts = line['timestamp']
        m  = ts // 60000
        s  = (ts % 60000) / 1000
        print(f"  [{m:02d}:{s:05.2f}] {line['text']}")

    print()
    for pos_s in [0, 3, 7, 12, 18, 25]:
        pos_ms = pos_s * 1000
        idx, nxt = get_line_at(lyrics, pos_ms)
        curr_text = lyrics[idx]['text'] if idx is not None else '(antes de inicio)'
        next_text = lyrics[nxt]['text'] if nxt is not None else '(fin)'
        print(f"  @ {pos_s:2d}s → actual: \"{curr_text}\" | siguiente: \"{next_text}\"")
    print()
    print("✓ Parser LRC OK")


def cmd_test_fetch(title: str, artist: str, no_cache: bool = False):
    """Busca y muestra letras de una canción."""
    from lyrics_fetcher import get_lyrics
    from lrc_parser import parse_lrc

    print(f"=== Buscando letras para: '{artist} — {title}' ===")
    lrc_content = get_lyrics(title, artist, use_cache=not no_cache)

    if lrc_content is None:
        print("✗ No se encontraron letras.")
        return

    print(f"✓ Letras encontradas ({len(lrc_content)} bytes)")
    print()

    attrs, lyrics = parse_lrc(lrc_content)
    if attrs:
        print("Atributos LRC:")
        for k, v in attrs.items():
            print(f"  [{k}] {v}")
        print()

    print(f"Total líneas: {len(lyrics)}")
    print("Primeras 10 líneas:")
    for line in lyrics[:10]:
        ts = line['timestamp']
        m  = ts // 60000
        s  = (ts % 60000) / 1000
        print(f"  [{m:02d}:{s:05.2f}] {line['text']}")
    if len(lyrics) > 10:
        print(f"  ... ({len(lyrics) - 10} líneas más)")


def cmd_test_spotify():
    """Prueba la conexión con Spotify."""
    from spotify_connector import SpotifyConnector, CLIENT_ID
    print("=== Test de Conexión Spotify ===")
    if CLIENT_ID == "TU_CLIENT_ID_AQUI":
        print("⚠ CLIENT_ID no configurado — usando modo fallback (ventana Windows)")
    conn = SpotifyConnector()
    print(f"  Conectado: {conn.is_connected}")
    print(f"  Con posición: {conn.has_position}")
    state, info, pos = conn.get_state()
    print(f"  Estado: {state}")
    if info:
        print(f"  Canción: {info.get('artist', '')} — {info.get('title', '')}")
        print(f"  Álbum: {info.get('album', '')}")
        print(f"  Duración: {info.get('duration', 0)/1000:.1f}s")
        print(f"  Posición: {pos/1000:.1f}s")
    print()
    print("✓ Test Spotify OK" if conn.is_connected else "✗ Spotify no está corriendo")


def cmd_launch_osd():
    """Lanza la ventana OSD."""
    try:
        import tkinter  # noqa: F401
    except ImportError:
        print("ERROR: tkinter no está disponible.")
        print("Instala Python con soporte de Tk (incluido en la instalación estándar de Windows).")
        sys.exit(1)

    from osd_window import main
    print("Iniciando OSD Lyrics para Spotify...")
    print()
    print("  MODOS DE OPERACIÓN:")
    print("  • Con Spotify Web API (CLIENT_ID configurado en spotify_connector.py):")
    print("    → Letras sincronizadas al milisegundo")
    print("  • Sin API (modo fallback):")
    print("    → Detecta canción por título de ventana, sin sincronía de posición")
    print()
    print("  CONTROLES:")
    print("  • Arrastra la ventana para moverla")
    print("  • Clic derecho → menú de opciones")
    print("  • Flechas ↑↓←→ para ajustar sincronización")
    print("  • ESC para cerrar")
    print()
    main()


def parse_args():
    parser = argparse.ArgumentParser(
        description='OSD Lyrics para Spotify — Letras sincronizadas en Windows',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Ejemplos:
  python main.py                                  # Lanzar OSD
  python main.py --test-lrc                       # Probar parser
  python main.py --test-fetch "Blinding Lights" "The Weeknd"
  python main.py --test-spotify                   # Probar conexión Spotify
  python main.py --debug                          # Lanzar OSD en modo debug
""")
    parser.add_argument('--test-lrc', action='store_true',
                        help='Probar el parser LRC y salir')
    parser.add_argument('--test-fetch', nargs=2, metavar=('TITLE', 'ARTIST'),
                        help='Buscar letras de una canción y mostrarlas')
    parser.add_argument('--test-spotify', action='store_true',
                        help='Probar la conexión con Spotify y salir')
    parser.add_argument('--no-cache', action='store_true',
                        help='Ignorar la caché local al buscar letras')
    parser.add_argument('--debug', action='store_true',
                        help='Activar logging detallado')
    return parser.parse_args()


def main():
    args = parse_args()

    level = logging.DEBUG if args.debug else logging.INFO
    logging.basicConfig(
        level=level,
        format='[%(asctime)s] %(levelname)s %(name)s: %(message)s',
        datefmt='%H:%M:%S',
    )

    if args.test_lrc:
        cmd_test_lrc()

    elif args.test_fetch:
        title, artist = args.test_fetch
        cmd_test_fetch(title, artist, no_cache=args.no_cache)

    elif args.test_spotify:
        cmd_test_spotify()

    else:
        cmd_launch_osd()


if __name__ == '__main__':
    main()
