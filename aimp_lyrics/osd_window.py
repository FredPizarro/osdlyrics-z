# -*- coding: utf-8 -*-
"""
OSD Lyrics para Windows — Visualizador de letras sincronizadas con AIMP

Ventana OSD siempre encima, transparente, estilo karaoke.
Incluye menú de configuración (+ clic derecho), animaciones y buscador avanzado.
"""

import json
import logging
import os
import sys
import threading
import time
import math
import tkinter as tk
from tkinter import ttk
from tkinter import font as tkfont
from tkinter import colorchooser
from pathlib import Path

# Asegurarse de que el directorio padre esté en el PATH
sys.path.insert(0, str(Path(__file__).parent))

from lrc_parser import parse_lrc, get_line_at
from lyrics_fetcher import (
    get_lyrics, save_cache_file, _cache_path, save_association,
    search_online_lyrics, search_local_lyrics, download_lyric_by_id
)

logger = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] %(levelname)s %(name)s: %(message)s',
    datefmt='%H:%M:%S',
)

POLL_INTERVAL_MS    = 50     
ANIM_FPS            = 60
ANIM_DURATION_MS    = 1000   
TRACK_POLL_MS       = 1000
CHROMA_KEY          = '#010101'
CONFIG_FILE         = Path("config.json")

DEFAULT_CONFIG = {
    "font_size": 40,
    "color_text": "#FFE566",
    "color_shadow": "#000000",
    "align": "center",
    "opacity": 0.9,
    "window_y": -1
}

def load_config():
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, 'r') as f:
                cfg = json.load(f)
                for k, v in DEFAULT_CONFIG.items():
                    if k not in cfg:
                        cfg[k] = v
                return cfg
        except Exception:
            pass
    return DEFAULT_CONFIG.copy()

def save_config(cfg):
    try:
        with open(CONFIG_FILE, 'w') as f:
            json.dump(cfg, f, indent=4)
    except Exception as e:
        logger.error("Error guardando config: %s", e)

# Helper para interpolación de color
def hex_to_rgb(hex_color):
    hex_color = hex_color.lstrip('#')
    return tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))

def rgb_to_hex(rgb):
    return '#{:02x}{:02x}{:02x}'.format(int(rgb[0]), int(rgb[1]), int(rgb[2]))

def blend_color(color1, color2, t):
    try:
        r1, g1, b1 = hex_to_rgb(color1)
        r2, g2, b2 = hex_to_rgb(color2)
        r = r1 + (r2 - r1) * t
        g = g1 + (g2 - g1) * t
        b = b1 + (b2 - b1) * t
        return rgb_to_hex((r, g, b))
    except:
        return color1

class AimpConnector:
    def __init__(self):
        self._client = None
        self._lock = threading.Lock()
        self._try_connect()

    def _try_connect(self):
        try:
            import pyaimp
            with self._lock:
                self._client = pyaimp.Client()
            logger.info("Conectado a AIMP.")
        except Exception as e:
            self._client = None

    @property
    def is_connected(self) -> bool:
        return self._client is not None

    def get_state(self):
        import pyaimp
        if not self.is_connected:
            self._try_connect()
            if not self.is_connected:
                return 'error', {}, 0
        try:
            with self._lock:
                state = self._client.get_playback_state()
                state_str = 'playing' if state == pyaimp.PlayBackState.Playing else \
                            'paused' if state == pyaimp.PlayBackState.Paused else 'stopped'
                info = self._client.get_current_track_info()
            return state_str, info
        except Exception:
            self._client = None
            return 'error', {}

    def get_position(self):
        if self.is_connected:
            try:
                with self._lock:
                    return self._client.get_player_position()
            except: pass
        return 0

class LyricsState:
    def __init__(self):
        self.reset()

    def reset(self):
        self.title = ''
        self.artist = ''
        self.lyrics = []
        self.attrs = {}
        self.current_idx = None
        self.loading = False
        self.player_state = 'stopped'
        self.no_lyrics = False
        self.offset_ms = 0

    def load(self, title, artist, album, duration):
        self.title = title
        self.artist = artist
        self.loading = True
        self.lyrics = []
        self.attrs = {}
        self.current_idx = None
        self.no_lyrics = False

        def _fetch():
            content = get_lyrics(title, artist, album, duration)
            if content:
                self._parse_and_set(content)
            else:
                self.no_lyrics = True
            self.loading = False
        
        threading.Thread(target=_fetch, daemon=True).start()

    def load_manual_content(self, content):
        """Carga contenido LRC manualmente."""
        self._parse_and_set(content)
        # Guardar inmediatamente asociación
        if self.title and self.artist:
            save_cache_file(self.title, self.artist, content)
            # Guardar asociación para que la próxima vez cargue automáticamente
            lrc_path = str(_cache_path(self.title, self.artist))
            save_association(self.title, self.artist, lrc_path)
        self.no_lyrics = False
        self.loading = False

    def _parse_and_set(self, content):
        attrs, lyrics = parse_lrc(content)
        self.lyrics = lyrics
        self.attrs = attrs

    def update_pos(self, pos):
        if self.lyrics:
            idx, _ = get_line_at(self.lyrics, pos)
            changed = (idx != self.current_idx)
            self.current_idx = idx
            return changed
        return False

    def apply_offset(self, delta_ms):
        if not self.lyrics: return
        self.offset_ms += delta_ms
        for line in self.lyrics:
            line['timestamp'] = max(0, line['timestamp'] + delta_ms)
        self.lyrics.sort(key=lambda x: x['timestamp'])
        self._save_lrc_to_disk()

    def _save_lrc_to_disk(self):
        lines = []
        if self.attrs:
            for k, v in self.attrs.items():
                lines.append(f"[{k}:{v}]")
        
        for line in self.lyrics:
            ts = line['timestamp']
            m = ts // 60000
            s = (ts % 60000) / 1000.0
            ts_str = f"[{m:02d}:{s:05.2f}]"
            lines.append(f"{ts_str}{line['text']}")
            
        content = "\n".join(lines)
        save_cache_file(self.title, self.artist, content)


import subprocess

class PlaylistDialog(tk.Toplevel):
    def __init__(self, parent):
        super().__init__(parent)
        self.title("Generar Playlist YouTube")
        self.geometry("500x250")
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()
        
        # Centrar
        x = (self.winfo_screenwidth() // 2) - 250
        y = (self.winfo_screenheight() // 2) - 125
        self.geometry(f"+{x}+{y}")
        
        self._build_ui()

    def _build_ui(self):
        tk.Label(self, text="URL de Playlist de YouTube:", font=("Segoe UI", 10, "bold")).pack(pady=(20, 5))
        
        self.entry_url = tk.Entry(self, width=60)
        self.entry_url.pack(pady=5, padx=20)
        self.entry_url.focus()
        
        self.lbl_status = tk.Label(self, text="Se requiere yt-dlp_x86.exe o yt-dlp instalado", fg="gray")
        self.lbl_status.pack(pady=5)

        btn_frame = tk.Frame(self)
        btn_frame.pack(pady=20)
        
        tk.Button(btn_frame, text="Generar .m3u8", command=self._generate, bg="#dddddd", width=15).pack(side='left', padx=10)
        tk.Button(btn_frame, text="Cancelar", command=self.destroy, width=10).pack(side='left', padx=10)

    def _find_ytdlp(self):
        # Buscar en orden: local x86, local normal, PATH
        candidates = ["yt-dlp_x86.exe", "yt-dlp.exe", "yt-dlp"]
        for c in candidates:
            if Path(c).exists():
                return str(Path(c).absolute())
            
            # Chequear PATH para 'yt-dlp'
            if c == "yt-dlp":
                from shutil import which
                if which("yt-dlp"): return "yt-dlp"
        return None

    def _generate(self):
        url = self.entry_url.get().strip()
        if not url:
            self.lbl_status.config(text="Por favor ingresa una URL.", fg="red")
            return

        exe = self._find_ytdlp()
        if not exe:
            self.lbl_status.config(text="ERROR: No se encontró yt-dlp_x86.exe ni yt-dlp.", fg="red")
            return

        self.lbl_status.config(text="Procesando... (esto puede tardar)", fg="blue")
        self.update_idletasks()
        
        threading.Thread(target=self._run_process, args=(exe, url), daemon=True).start()

    def _run_process(self, exe, url):
        try:
            # Opción robusta: Obtener JSON para formatear nosotros el M3U perfecto (utf-8)
            # yt-dlp --flat-playlist -J <url>
            cmd = [exe, "--flat-playlist", "-J", url]
            
            # En Windows subprocess puede necesitar shell=True o flags para ocultar consola
            si = None
            if os.name == 'nt':
                si = subprocess.STARTUPINFO()
                si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            
            process = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', startupinfo=si)
            
            if process.returncode != 0:
                self.after(0, lambda: self.lbl_status.config(text="Error al ejecutar yt-dlp.", fg="red"))
                logger.error("yt-dlp error: %s", process.stderr)
                return

            data = json.loads(process.stdout)
            
            if 'entries' not in data:
                # A veces devuelve solo un video
                entries = [data]
            else:
                entries = data['entries']

            filename = "playlist.m3u8"
            if 'title' in data and data['title']:
                # Sanitize filename
                safe_title = "".join(x for x in data['title'] if x.isalnum() or x in " -_")
                filename = f"{safe_title}.m3u8"

            # Escribir M3U8
            with open(filename, 'w', encoding='utf-8') as f:
                f.write("#EXTM3U\n")
                count = 0
                for entry in entries:
                    title = entry.get('title', 'Unknown Title')
                    url   = entry.get('url', '')
                    if url:
                        f.write(f"#EXTINF:-1,{title}\n")
                        f.write(f"{url}\n")
                        count += 1
            
            msg = f"Playlist guardada: {filename} ({count} canciones)"
            self.after(0, lambda: self.lbl_status.config(text=msg, fg="green"))
            
        except Exception as e:
            logger.error("Error generando playlist: %s", e)
            self.after(0, lambda: self.lbl_status.config(text=f"Error: {e}", fg="red"))
            self.after(0, lambda: self.lbl_status.config(text=f"Error: {e}", fg="red"))


class SettingsDialog(tk.Toplevel):
    def __init__(self, parent, config, callback):
        super().__init__(parent)
        self.title("Configuración")
        self.geometry("380x500")
        self.resizable(False, False)
        self.config = config.copy()
        self.callback = callback
        self.transient(parent)
        self.grab_set()
        self._build_ui()
        self.update_idletasks()
        try:
            x = (self.winfo_screenwidth() // 2) - (self.winfo_width() // 2)
            y = (self.winfo_screenheight() // 2) - (self.winfo_height() // 2)
            self.geometry(f"+{x}+{y}")
        except: pass

    def _build_ui(self):
        pad = {'padx': 15, 'pady': 10}
        
        lbl_frame = tk.LabelFrame(self, text="Apariencia")
        lbl_frame.pack(fill='x', **pad)
        
        tk.Label(lbl_frame, text="Tamaño Fuente:").grid(row=0, column=0, sticky='e', padx=5)
        self.spin_size = tk.Spinbox(lbl_frame, from_=20, to=120, width=5)
        self.spin_size.delete(0, 'end')
        self.spin_size.insert(0, self.config['font_size'])
        self.spin_size.grid(row=0, column=1, sticky='w', padx=5)

        tk.Button(lbl_frame, text="Color Texto...", command=self._pick_text).grid(row=1, column=0, columnspan=2, pady=5)
        self.lbl_text = tk.Label(lbl_frame, text=" ABC ", bg='gray', fg=self.config['color_text'], font=('Arial', 12, 'bold'))
        self.lbl_text.grid(row=1, column=2)

        tk.Button(lbl_frame, text="Color Sombra...", command=self._pick_shadow).grid(row=2, column=0, columnspan=2, pady=5)
        self.lbl_shadow = tk.Label(lbl_frame, text=" ABC ", bg='white', fg=self.config['color_shadow'], font=('Arial', 12, 'bold'))
        self.lbl_shadow.grid(row=2, column=2)

        align_frame = tk.LabelFrame(self, text="Alineación")
        align_frame.pack(fill='x', **pad)
        self.var_align = tk.StringVar(value=self.config['align'])
        for a in ['left', 'center', 'right']:
            tk.Radiobutton(align_frame, text=a.capitalize(), variable=self.var_align, value=a).pack(anchor='w', padx=10)

        op_frame = tk.LabelFrame(self, text="Opacidad")
        op_frame.pack(fill='x', **pad)
        self.scale_op = tk.Scale(op_frame, from_=0.1, to=1.0, resolution=0.05, orient='horizontal')
        self.scale_op.set(self.config['opacity'])
        self.scale_op.pack(fill='x', padx=10)

        btn_frame = tk.Frame(self)
        btn_frame.pack(fill='x', pady=20)
        tk.Button(btn_frame, text="Guardar", command=self._save, bg='#dddddd').pack(side='right', padx=15)
        tk.Button(btn_frame, text="Cancelar", command=self.destroy).pack(side='right')

    def _pick_text(self):
        c = colorchooser.askcolor(self.config['color_text'])[1]
        if c: 
            self.config['color_text'] = c
            self.lbl_text.config(fg=c)

    def _pick_shadow(self):
        c = colorchooser.askcolor(self.config['color_shadow'])[1]
        if c: 
            self.config['color_shadow'] = c
            self.lbl_shadow.config(fg=c)

    def _save(self):
        try:
            self.config['font_size'] = int(self.spin_size.get())
            self.config['align'] = self.var_align.get()
            self.config['opacity'] = self.scale_op.get()
            self.callback(self.config)
            self.destroy()
        except: pass


class SearchDialog(tk.Toplevel):
    def __init__(self, parent, initial_query, callback):
        super().__init__(parent)
        self.title("Buscar Letras")
        self.geometry("800x500") # Más ancho para metadata
        self.callback = callback
        self.initial_query = initial_query
        
        # Centrar
        x = (self.winfo_screenwidth() // 2) - 400
        y = (self.winfo_screenheight() // 2) - 250
        self.geometry(f"+{x}+{y}")
        
        self.transient(parent)
        self.grab_set()
        
        self._build_ui()
        self.after(200, lambda: self._search(initial_query))

    def _build_ui(self):
        # Header
        top_frame = tk.Frame(self)
        top_frame.pack(fill='x', padx=10, pady=10)
        
        tk.Label(top_frame, text="Buscar:").pack(side='left')
        self.entry_search = tk.Entry(top_frame)
        self.entry_search.pack(side='left', fill='x', expand=True, padx=5)
        if self.initial_query:
            self.entry_search.insert(0, self.initial_query)
        self.entry_search.bind('<Return>', lambda e: self._search(self.entry_search.get()))
        
        tk.Button(top_frame, text="Buscar", command=lambda: self._search(self.entry_search.get())).pack(side='right')

        # Tabla de resultados
        cols = ('source', 'artist', 'title', 'album', 'rating', 'downloads')
        self.tree = ttk.Treeview(self, columns=cols, show='headings')
        self.tree.heading('source', text='Fuente')
        self.tree.heading('artist', text='Artista')
        self.tree.heading('title', text='Título')
        self.tree.heading('album', text='Álbum')
        self.tree.heading('rating', text='Pop')
        self.tree.heading('downloads', text='Dls')
        
        # Anchos
        self.tree.column('source', width=70, anchor='center')
        self.tree.column('artist', width=150)
        self.tree.column('title', width=200)
        self.tree.column('album', width=150)
        self.tree.column('rating', width=80, anchor='center')
        self.tree.column('downloads', width=50, anchor='center')
        
        # Scrollbar
        scroll = ttk.Scrollbar(self, orient='vertical', command=self.tree.yview)
        self.tree.configure(yscroll=scroll.set)
        
        self.tree.pack(side='left', fill='both', expand=True, padx=(10,0), pady=5)
        scroll.pack(side='right', fill='y', padx=(0,10), pady=5)
        
        # Binding Doble Click para descargar
        self.tree.bind("<Double-1>", lambda e: self._on_select())
        
        # Botones inferiores
        btn_frame = tk.Frame(self)
        btn_frame.pack(fill='x', padx=10, pady=10)
        
        tk.Button(btn_frame, text="Cancelar", command=self.destroy).pack(side='right', padx=5)
        tk.Button(btn_frame, text="Descargar y Usar", command=self._on_select).pack(side='right', padx=5)

    def _search(self, query):
        if not query: return
        
        # Limpiar
        self.tree.delete(*self.tree.get_children())
        self.title("Buscando...")
        
        def _do_search():
            # 1. Local
            local_results = search_local_lyrics(query)
                
            # 2. Online
            online_results = search_online_lyrics(query)
            
            # Insertar en el hilo principal de tkinter
            def _insert_results():
                try:
                    if not self.winfo_exists():
                        return
                    for l in local_results:
                        self.tree.insert('', 'end', values=('Local', l['artist'], l['title'], '', '-', '-'), tags=(l['id'], 'local'))
                    for o in online_results:
                        r = o.get('rating', '-')
                        d = o.get('downloads', '-')
                        src = o.get('source', 'Online')
                        self.tree.insert('', 'end', values=(src, o['artist'], o['title'], o['album'], r, d), tags=(str(o['id']), 'online'))
                    self.title("Buscar Letras (Resultados cargados)")
                except Exception:
                    pass  # Diálogo cerrado durante inserción
            
            self.after(0, _insert_results)
                
        threading.Thread(target=_do_search, daemon=True).start()

    def _on_select(self):
        sel = self.tree.selection()
        if not sel: return
        
        item = self.tree.item(sel[0])
        lyric_id = item['tags'][0]
        source_type = item['tags'][1]
        
        self.title("Descargando...")
        
        def _download():
            content = None
            if source_type == 'local':
                try: content = Path(lyric_id).read_text(encoding='utf-8')
                except: pass
            elif source_type == 'online':
                content = download_lyric_by_id(lyric_id)
                
            def _apply():
                try:
                    if content:
                        self.callback(content)
                        self.destroy()
                    else:
                        if self.winfo_exists():
                            self.title("Error al descargar")
                except Exception:
                    pass
            
            self.after(0, _apply)

        threading.Thread(target=_download, daemon=True).start()


class OSDWindow:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.config = load_config()
        self.aimp = AimpConnector()
        self.state = LyricsState()
        self._last_track_key = ''

        # Animación
        self._animating = False
        self._anim_start_time = 0
        self._anim_text_old = ""
        self._anim_text_new = ""
        
        # Colores
        self._curr_text_color   = self.config['color_text']
        self._curr_shadow_color = self.config['color_shadow']

        self._setup_window()
        self._build_ui()
        self._setup_menu()
        
        # Shortcuts
        self.root.bind('<Up>', lambda e: self._adjust_sync(-500))
        self.root.bind('<Down>', lambda e: self._adjust_sync(500))
        self.root.bind('<Left>', lambda e: self._adjust_sync(-200))
        self.root.bind('<Right>', lambda e: self._adjust_sync(200))
        
        self.root.after(500, self._poll_track)
        self.root.after(POLL_INTERVAL_MS, self._poll_position)

    def _setup_window(self):
        self.root.title("OSD Lyrics")
        self.root.overrideredirect(True)
        self.root.attributes('-topmost', True)
        self.root.attributes('-transparentcolor', CHROMA_KEY)
        self.root.configure(bg=CHROMA_KEY)
        self.root.attributes('-alpha', self.config['opacity'])
        
        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        w, h = sw - 100, 200
        x = 50
        y = self.config['window_y'] if self.config['window_y'] != -1 else sh - h - 80
        
        self.root.geometry(f"{w}x{h}+{x}+{y}")
        self._win_w, self._win_h = w, h

        self.root.bind('<ButtonPress-1>', self._start_move)
        self.root.bind('<B1-Motion>', self._do_move)
        self.root.bind('<Escape>', lambda e: self.root.destroy())
        self._drag_data = {'x': 0, 'y': 0}

    def _build_ui(self):
        self.canvas = tk.Canvas(self.root, bg=CHROMA_KEY, highlightthickness=0)
        self.canvas.pack(fill='both', expand=True)

        self.items = {
            'old_s': self.canvas.create_text(0,0, text="", state='hidden'),
            'old_t': self.canvas.create_text(0,0, text="", state='hidden'),
            'new_s': self.canvas.create_text(0,0, text="", state='hidden'),
            'new_t': self.canvas.create_text(0,0, text="", state='hidden'),
            'info':  self.canvas.create_text(10, 10, text="", fill="white", anchor="nw", font=("Arial", 10), state='hidden')
        }
        self._apply_config()

    def _setup_menu(self):
        self.menu = tk.Menu(self.root, tearoff=0)
        
        self.menu.add_command(label="Buscar Letra...", command=self._open_search)
        self.menu.add_command(label="Generar Playlist YouTube...", command=self._open_playlist)
        self.menu.add_separator()
        
        sync_menu = tk.Menu(self.menu, tearoff=0)
        sync_menu.add_command(label="Adelantar 0.5s", command=lambda: self._adjust_sync(-500))
        sync_menu.add_command(label="Atrasar 0.5s", command=lambda: self._adjust_sync(500))
        self.menu.add_cascade(label="Sincronización", menu=sync_menu)
        
        self.menu.add_separator()
        self.menu.add_command(label="Configuración...", command=self._open_settings)
        self.menu.add_command(label="Salir", command=self.root.destroy)
        
        self.root.bind("<Button-3>", lambda e: self.menu.post(e.x_root, e.y_root))

    def _open_playlist(self):
        PlaylistDialog(self.root)

    def _open_search(self):
        query = f"{self.state.artist} {self.state.title}" if self.state.title else ""
        
        def on_lyric_selected(content):
            if content:
                self.state.load_manual_content(content)
                self._show_info_toast("Letra cargada y guardada")
            else:
                self._show_info_toast("Error al cargar letra")

        SearchDialog(self.root, query, on_lyric_selected)

    # ... Settings restored ...

    def _adjust_sync(self, delta_ms):
        self.state.apply_offset(delta_ms)
        sign = "+" if delta_ms > 0 else ""
        self._show_info_toast(f"Sync: {sign}{delta_ms}ms (Total: {self.state.offset_ms}ms)")
        try:
            pos = self.aimp.get_position()
            if self.state.update_pos(pos): self._update_lyric_display()
        except: pass

    def _show_info_toast(self, text):
        self.canvas.itemconfigure(self.items['info'], text=text, state='normal')
        self.root.after(3000, lambda: self.canvas.itemconfigure(self.items['info'], state='hidden'))

    def _open_settings(self):
        def on_save(cfg):
            self.config = cfg
            save_config(cfg)
            self._apply_config()
            self._set_static_text(self._anim_text_old)
        
        SettingsDialog(self.root, self.config, on_save)

    def _apply_config(self):
        self.root.attributes('-alpha', self.config['opacity'])
        fs = self.config['font_size']
        f = tkfont.Font(family="Segoe UI", size=fs, weight="bold")
        self.current_font = f
        self.shadow_offset = max(2, fs // 15)
        self._curr_text_color   = self.config['color_text']
        self._curr_shadow_color = self.config['color_shadow']
        
        if self.config['align'] == 'left':
            self.anchor_x = 40
            self.anchor_mode = 'w'
        elif self.config['align'] == 'right':
            self.anchor_x = self._win_w - 40
            self.anchor_mode = 'e'
        else:
            self.anchor_x = self._win_w // 2
            self.anchor_mode = 'center'

        for key in self.items:
            if key == 'info': continue
            color = self._curr_shadow_color if '_s' in key else self._curr_text_color
            self.canvas.itemconfigure(self.items[key], font=f, fill=color, anchor=self.anchor_mode)

    def _animate_step(self):
        if not self._animating: return
        elapsed = (time.time() - self._anim_start_time) * 1000
        progress = elapsed / ANIM_DURATION_MS
        if progress >= 1.0:
            self._animating = False
            self._set_static_text(self._anim_text_new)
            return

        t = progress
        ease = 1 - math.pow(1 - t, 3)
        cy = self._win_h // 2
        dist = 50 
        y_old = cy - (dist * ease)
        y_new = (cy + dist) - (dist * ease)
        
        old_color_t = blend_color(self._curr_text_color, CHROMA_KEY, float(t))
        old_color_s = blend_color(self._curr_shadow_color, CHROMA_KEY, float(t))
        new_color_t = blend_color(CHROMA_KEY, self._curr_text_color, float(t))
        new_color_s = blend_color(CHROMA_KEY, self._curr_shadow_color, float(t))
        
        self._update_item('old', y_old, old_color_t, old_color_s)
        self._update_item('new', y_new, new_color_t, new_color_s)
        self.root.after(int(1000/ANIM_FPS), self._animate_step)

    def _trigger_animation(self, old_text, new_text):
        if old_text == new_text: return
        self._anim_text_old = old_text
        self._anim_text_new = new_text
        self._anim_start_time = time.time()
        self._animating = True
        
        self.canvas.itemconfigure(self.items['old_t'], text=old_text, state='normal')
        self.canvas.itemconfigure(self.items['old_s'], text=old_text, state='normal')
        self.canvas.itemconfigure(self.items['new_t'], text=new_text, state='normal')
        self.canvas.itemconfigure(self.items['new_s'], text=new_text, state='normal')
        self._animate_step()

    def _update_item(self, prefix, y, color_t, color_s):
        self.canvas.coords(self.items[f'{prefix}_t'], self.anchor_x, y)
        self.canvas.coords(self.items[f'{prefix}_s'], self.anchor_x + self.shadow_offset, y + self.shadow_offset)
        self.canvas.itemconfigure(self.items[f'{prefix}_t'], fill=color_t)
        self.canvas.itemconfigure(self.items[f'{prefix}_s'], fill=color_s)

    def _set_static_text(self, text):
        cy = self._win_h // 2
        self.canvas.itemconfigure(self.items['old_t'], state='hidden')
        self.canvas.itemconfigure(self.items['old_s'], state='hidden')
        self._update_item('new', cy, self._curr_text_color, self._curr_shadow_color)
        self.canvas.itemconfigure(self.items['new_t'], text=text, state='normal')
        self.canvas.itemconfigure(self.items['new_s'], text=text, state='normal')
        self._anim_text_old = text 

    def _poll_track(self):
        try:
            state, info = self.aimp.get_state()
            self.state.player_state = state
            if state in ['stopped', 'error']:
                if self._anim_text_old != "⏹ Detenido": self._set_static_text("⏹ Detenido")
            else:
                title = info.get('title', '')
                artist = info.get('artist', '')
                key = f"{title}||{artist}"
                if key != self._last_track_key:
                    self._last_track_key = key
                    self.state.reset()
                    self.state.load(title, artist, info.get('album', ''), info.get('duration', 0))
                    d = f"▶ {title}"
                    if artist: d += f" - {artist}"
                    self._set_static_text(d)
        except: pass
        self.root.after(TRACK_POLL_MS, self._poll_track)

    def _poll_position(self):
        if self.state.player_state == 'playing':
            try:
                pos = self.aimp.get_position()
                if self.state.update_pos(pos): self._update_lyric_display()
            except: pass
        self.root.after(POLL_INTERVAL_MS, self._poll_position)

    def _update_lyric_display(self):
        if self.state.loading: return
        if self.state.no_lyrics:
            self._trigger_animation(self._anim_text_old, "♪ (Sin letra) ♪")
            return
        idx = self.state.current_idx
        if idx is not None:
            new_text = self.state.lyrics[idx]['text']
            if new_text != self._anim_text_old:
                self._trigger_animation(self._anim_text_old, new_text)
        else:
            intro = f"♪ {self.state.title} ♪"
            if intro != self._anim_text_old:
                self._trigger_animation(self._anim_text_old, intro)

    def _start_move(self, event):
        self._drag_data['x'] = event.x
        self._drag_data['y'] = event.y

    def _do_move(self, event):
        dx = event.x - self._drag_data['x']
        dy = event.y - self._drag_data['y']
        nx, ny = self.root.winfo_x() + dx, self.root.winfo_y() + dy
        self.root.geometry(f"+{nx}+{ny}")
        self.config['window_y'] = ny

def main():
    root = tk.Tk()
    OSDWindow(root)
    root.mainloop()

if __name__ == '__main__':
    main()
