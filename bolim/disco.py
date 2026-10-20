#!/usr/bin/env python3
"""
Bolim Bluray Player — acceso al disco con libbluray (ctypes).

Abre el disco, lista títulos y capítulos, busca KEYDB.cfg y entrega el stream
de un título a mpv con tamaño y búsqueda por bytes.
"""
import ctypes
import ctypes.util
import os
import sys
from ctypes import POINTER, Structure, c_char_p, c_int, c_uint, c_uint8, c_uint32, c_uint64, c_void_p

APP_DIR = os.path.dirname(os.path.abspath(__file__))
LIB_DIR = os.path.join(APP_DIR, "lib")
TITLES_RELEVANT = 0x03  # filtra títulos duplicados
BLOQUE = 6144           # unidad alineada de Blu-ray (32 paquetes de 192 bytes)

# DLLs locales en ./lib (libbluray, libaacs, libmpv)
if os.path.isdir(LIB_DIR):
    if sys.platform == "win32":
        os.add_dll_directory(LIB_DIR)
    os.environ["PATH"] = LIB_DIR + os.pathsep + os.environ.get("PATH", "")


# --- Estructuras de libbluray (solo los campos iniciales que usamos) ---
class Capitulo(Structure):
    _fields_ = [("idx", c_uint32), ("start", c_uint64), ("duration", c_uint64),
                ("offset", c_uint64), ("clip_ref", c_uint)]


class TitleInfo(Structure):
    _fields_ = [("idx", c_uint32), ("playlist", c_uint32), ("duration", c_uint64),
                ("clip_count", c_uint32), ("angle_count", c_uint8), ("chapter_count", c_uint32),
                ("mark_count", c_uint32), ("clips", c_void_p), ("chapters", POINTER(Capitulo)),
                ("marks", c_void_p), ("mvc_base_view_r_flag", c_uint8)]


class MetaDL(Structure):
    _fields_ = [("language_code", ctypes.c_char * 4), ("filename", c_char_p), ("di_name", c_char_p)]


def buscar_keydb():
    local = os.path.join(APP_DIR, "config", "aacs", "KEYDB.cfg")
    if os.path.isfile(local):
        return local, "carpeta del programa"
    if sys.platform == "win32":
        std = os.path.join(os.environ.get("APPDATA", ""), "aacs", "KEYDB.cfg")
    elif sys.platform == "darwin":
        std = os.path.expanduser("~/Library/Preferences/aacs/KEYDB.cfg")
    else:
        base = os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config")
        std = os.path.join(base, "aacs", "KEYDB.cfg")
    if os.path.isfile(std):
        return std, "ruta estándar de libaacs"
    return None, None


def cargar_libbluray():
    nombres = ["libbluray.dll", "libbluray-2.dll"] if sys.platform == "win32" else []
    sistema = ctypes.util.find_library("bluray")
    if sistema:
        nombres.append(sistema)
    nombres += ["libbluray.so.2", "libbluray.2.dylib", "libbluray.dylib"]
    for n in nombres:
        for ruta in (os.path.join(LIB_DIR, n), n):
            try:
                lib = ctypes.CDLL(ruta)
                break
            except OSError:
                lib = None
        if lib:
            break
    else:
        raise RuntimeError("No se encontró libbluray")

    lib.bd_open.argtypes, lib.bd_open.restype = [c_char_p, c_char_p], c_void_p
    lib.bd_close.argtypes, lib.bd_close.restype = [c_void_p], None
    lib.bd_get_titles.argtypes, lib.bd_get_titles.restype = [c_void_p, c_uint8, c_uint32], c_uint32
    lib.bd_get_main_title.argtypes, lib.bd_get_main_title.restype = [c_void_p], c_int
    lib.bd_get_title_info.argtypes = [c_void_p, c_uint32, c_uint]
    lib.bd_get_title_info.restype = POINTER(TitleInfo)
    lib.bd_free_title_info.argtypes, lib.bd_free_title_info.restype = [POINTER(TitleInfo)], None
    lib.bd_select_title.argtypes, lib.bd_select_title.restype = [c_void_p, c_uint32], c_int
    lib.bd_read.argtypes, lib.bd_read.restype = [c_void_p, c_char_p, c_int], c_int
    lib.bd_get_meta.argtypes, lib.bd_get_meta.restype = [c_void_p], POINTER(MetaDL)
    lib.bd_seek.argtypes, lib.bd_seek.restype = [c_void_p, c_uint64], ctypes.c_int64
    lib.bd_get_title_size.argtypes, lib.bd_get_title_size.restype = [c_void_p], c_uint64
    return lib


class Disco:
    def __init__(self, lib, dispositivo, keydb):
        self.lib = lib
        self.bd = lib.bd_open(dispositivo.encode(), keydb.encode() if keydb else None)
        if not self.bd:
            raise RuntimeError(f"No se pudo abrir el disco en {dispositivo}")
        self.num_titulos = lib.bd_get_titles(self.bd, TITLES_RELEVANT, 0)

    def cerrar(self):
        if self.bd:
            self.lib.bd_close(self.bd)
            self.bd = None

    def nombre(self):
        try:
            m = self.lib.bd_get_meta(self.bd)
            if m and m.contents.di_name:
                return m.contents.di_name.decode("utf-8", "replace")
        except (OSError, ValueError):
            pass
        return None

    def principal(self):
        return self.lib.bd_get_main_title(self.bd)

    def titulos(self):
        for i in range(self.num_titulos):
            p = self.lib.bd_get_title_info(self.bd, i, 0)
            if not p:
                continue
            t = p.contents
            datos = (i, t.duration / 90000, t.chapter_count, t.playlist)
            self.lib.bd_free_title_info(p)
            yield datos

    def probar_lectura(self, idx):
        """Lee un bloque y verifica que los paquetes TS estén en claro."""
        if not self.lib.bd_select_title(self.bd, idx):
            return "no se pudo seleccionar el título"
        buf = ctypes.create_string_buffer(BLOQUE)
        n = self.lib.bd_read(self.bd, buf, BLOQUE)
        self.lib.bd_select_title(self.bd, idx)  # regresa al inicio
        if n <= 0:
            return "error de lectura (¿disco cifrado sin clave válida?)"
        datos = buf.raw[:n]
        cifrados = sum(1 for k in range(1, 32) if 4 + 192 * k < n and datos[4 + 192 * k] != 0x47)
        return None if cifrados == 0 else "los datos siguen cifrados (falta la clave de este disco)"

    def capitulos(self, idx):
        """Lista de (inicio, duración) en segundos, relativos al inicio del título."""
        p = self.lib.bd_get_title_info(self.bd, idx, 0)
        if not p:
            return []
        t = p.contents
        caps = [(t.chapters[i].start / 90000, t.chapters[i].duration / 90000)
                for i in range(t.chapter_count)]
        self.lib.bd_free_title_info(p)
        return caps


class StreamBD:
    """Stream del título para mpv, con tamaño conocido y búsqueda por bytes."""

    def __init__(self, disco, idx):
        self.lib, self.bd = disco.lib, disco.bd
        self.lib.bd_select_title(self.bd, idx)
        self.size = self.lib.bd_get_title_size(self.bd)
        self.buf = ctypes.create_string_buffer(BLOQUE * 32)
        self.pendiente = b""

    def read(self, n):
        if self.pendiente:
            datos, self.pendiente = self.pendiente[:n], self.pendiente[n:]
            return datos
        r = self.lib.bd_read(self.bd, self.buf, min(n, len(self.buf)))
        return self.buf.raw[:r] if r > 0 else b""

    def seek(self, pos):
        # libbluray busca en múltiplos de 6144; se lee y descarta hasta la posición exacta
        real = self.lib.bd_seek(self.bd, pos - pos % BLOQUE)
        self.pendiente = b""
        while 0 <= real < pos:
            r = self.lib.bd_read(self.bd, self.buf, len(self.buf))
            if r <= 0:
                break
            if real + r > pos:
                self.pendiente = self.buf.raw[pos - real:r]
                real = pos
            else:
                real += r
        return real

    def close(self):
        pass


def hms(seg):
    seg = int(seg)
    return f"{seg // 3600}:{seg % 3600 // 60:02d}:{seg % 60:02d}"
