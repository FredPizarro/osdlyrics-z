# -*- coding: utf-8 -*-
"""
Parser de archivos LRC (letras sincronizadas).
Adaptado del módulo aimp_lyrics para spotify_lyrics.
"""

import re


LINE_PATTERN = re.compile(r'(\[[^\[]*?\])')
TIMESTAMP_PATTERN = re.compile(r'^\[(\d+(:\d+){0,2}(\.\d+)?)\]$')
ATTR_PATTERN = re.compile(r'^\[([\w\d]+):(.*)\]$')


class AttrToken:
    """Tag con la forma [key:value]"""
    def __init__(self, key, value):
        self.key = key.strip()
        self.value = value.strip()

    def __repr__(self):
        return '{%s: %s}' % (self.key, self.value)


class StringToken:
    """Una línea de texto de letra"""
    def __init__(self, text):
        self.text = text.strip()

    def __repr__(self):
        return '"%s"' % self.text


class TimeToken:
    """Tag con la forma [h:m:s.ms] — el tiempo está en milisegundos"""
    def __init__(self, string):
        parts = string.split(':')
        parts.reverse()
        factor = 1000
        ms = int(float(parts[0]) * factor)
        for s in parts[1:]:
            factor = factor * 60
            ms = ms + factor * int(s)
        self.time = ms

    def __repr__(self):
        return '[%dms]' % self.time


def tokenize(content):
    """Divide el contenido de un archivo LRC en tokens."""
    def parse_tag(tag):
        m = TIMESTAMP_PATTERN.match(tag)
        if m:
            return TimeToken(m.group(1))
        m = ATTR_PATTERN.match(tag)
        if m:
            return AttrToken(m.group(1), m.group(2))
        return None

    def tokenize_line(line):
        pos = 0
        tokens = []
        while pos < len(line) and line[pos] == '[':
            has_tag = False
            m = LINE_PATTERN.search(line, pos)
            if m and m.start() == pos:
                tag = m.group()
                token = parse_tag(tag)
                if token:
                    tokens.append(token)
                    has_tag = True
                    pos = m.end()
            if not has_tag:
                break
        tokens.append(StringToken(line[pos:]))
        return tokens

    lines = content.splitlines()
    tokens = []
    for line in lines:
        tokens.extend(tokenize_line(line))
    return tokens


def parse_lrc(content):
    """
    Parsea un archivo LRC.

    Retorna:
        attrs (dict): atributos del LRC (ti, ar, al, etc.)
        lyrics (list): lista de dicts con 'timestamp' (ms) e 'text'.
                       Ordenados ascendentemente por timestamp.
    """
    tokens = tokenize(content)
    attrs = {}
    lyrics = []
    timetags = []

    for token in tokens:
        if isinstance(token, AttrToken):
            attrs[token.key] = token.value
        elif isinstance(token, TimeToken):
            timetags.append(token.time)
        else:
            # StringToken: asociar timetags acumulados al texto
            for timestamp in timetags:
                if token.text:  # ignorar líneas vacías
                    lyrics.append({
                        'timestamp': timestamp,
                        'text': token.text
                    })
            timetags = []

    lyrics.sort(key=lambda a: a['timestamp'])
    for i, lyric in enumerate(lyrics):
        lyric['id'] = i

    return attrs, lyrics


def get_line_at(lyrics, position_ms):
    """
    Dado un tiempo en ms, retorna el índice de la línea activa y la línea siguiente.

    Args:
        lyrics: lista de dicts con 'timestamp' y 'text'
        position_ms: posición actual en milisegundos

    Returns:
        (current_idx, next_idx) — índices en la lista lyrics, o None si no aplica
    """
    if not lyrics:
        return None, None

    current_idx = None
    for i, line in enumerate(lyrics):
        if line['timestamp'] <= position_ms:
            current_idx = i
        else:
            break

    if current_idx is None:
        return None, None

    next_idx = current_idx + 1 if current_idx + 1 < len(lyrics) else None
    return current_idx, next_idx


if __name__ == '__main__':
    test = """[ti:Test Song][ar:Test Artist]
[00:01.00]Primera línea
[00:05.50]Segunda línea
[00:10.00]Tercera línea
"""
    attrs, lrc = parse_lrc(test)
    print("Attrs:", attrs)
    for l in lrc:
        print(f"  [{l['timestamp']}ms] {l['text']}")
    print("Línea a 6000ms:", get_line_at(lrc, 6000))
