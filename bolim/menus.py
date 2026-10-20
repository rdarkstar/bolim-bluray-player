#!/usr/bin/env python3
"""
Bolim Bluray Player — navegación con menús del disco (HDMV y BD-J).

Lee el disco en modo menú con libbluray, dibuja los gráficos de los menús
sobre el video y reparte el stream por playlist hacia mpv.
"""
import ctypes
import os
import subprocess
import sys
import tempfile
import threading
import time
import warnings
from collections import deque
from ctypes import (CFUNCTYPE, POINTER, Structure, c_char_p, c_int, c_int64, c_uint, c_uint8,
                    c_uint16, c_uint32, c_void_p)

import numpy as np

from . import disco as base

# Aviso inofensivo de python-mpv al quitar atajos de ratón mientras llega un evento
warnings.filterwarnings("ignore", message=r"Unhandled exception on python-mpv event loop: 'py_kb_",
                        category=RuntimeWarning)

# --- Estructuras de libbluray ---
class Evento(Structure):
    _fields_ = [("event", c_uint32), ("param", c_uint32)]


class Paleta(Structure):
    _fields_ = [("Y", c_uint8), ("Cr", c_uint8), ("Cb", c_uint8), ("T", c_uint8)]


class Rle(Structure):
    _fields_ = [("len", c_uint16), ("color", c_uint16)]


class Overlay(Structure):  # menús HDMV (paleta + RLE)
    _fields_ = [("pts", c_int64), ("plane", c_uint8), ("cmd", c_uint8), ("palette_update_flag", c_uint8),
                ("x", c_uint16), ("y", c_uint16), ("w", c_uint16), ("h", c_uint16),
                ("palette", POINTER(Paleta)), ("img", POINTER(Rle))]


class OverlayARGB(Structure):  # menús BD-J (ARGB)
    _fields_ = [("pts", c_int64), ("plane", c_uint8), ("cmd", c_uint8),
                ("x", c_uint16), ("y", c_uint16), ("w", c_uint16), ("h", c_uint16),
                ("stride", c_uint16), ("argb", POINTER(c_uint32))]


class InfoPista(Structure):
    _fields_ = [("coding_type", c_uint8), ("format", c_uint8), ("rate", c_uint8), ("char_code", c_uint8),
                ("lang", ctypes.c_char * 4), ("pid", c_uint16), ("aspect", c_uint8), ("subpath_id", c_uint8)]


class InfoClip(Structure):
    _fields_ = [("pkt_count", c_uint32), ("still_mode", c_uint8), ("still_time", c_uint16),
                ("video_stream_count", c_uint8), ("audio_stream_count", c_uint8),
                ("pg_stream_count", c_uint8), ("ig_stream_count", c_uint8),
                ("sec_audio_stream_count", c_uint8), ("sec_video_stream_count", c_uint8),
                ("video_streams", POINTER(InfoPista)), ("audio_streams", POINTER(InfoPista)),
                ("pg_streams", POINTER(InfoPista))]


PROC_OV = CFUNCTYPE(None, c_void_p, POINTER(Overlay))
PROC_ARGB = CFUNCTYPE(None, c_void_p, POINTER(OverlayARGB))

EV_ERROR, EV_READ_ERROR, EV_ENCRYPTED, EV_PLAYLIST = 1, 2, 3, 6
EV_AUDIO_STREAM, EV_PG_TEXTST_STREAM, EV_PG_TEXTST = 11, 13, 17
EV_STILL, EV_STILL_TIME, EV_IDLE = 25, 26, 28
OV_INIT, OV_CLOSE, OV_CLEAR, OV_DRAW, OV_WIPE, OV_HIDE, OV_FLUSH = range(7)
VK_POPUP, VK_MOUSE_ACTIVATE = 11, 17
# tecla: (código para el menú del disco, comando de mpv fuera del menú)
TECLAS_MENU = {"UP": (12, "seek 60"), "DOWN": (13, "seek -60"), "LEFT": (14, "seek -5"),
               "RIGHT": (15, "seek 5"), "ENTER": (16, None), "KP_ENTER": (16, None)}
SET_AUDIO_LANG, SET_PG_LANG, SET_MENU_LANG, SET_COUNTRY, SET_REGION, SET_DECODE_PG = 16, 17, 18, 19, 20, 0x100
MIN_BUSCABLE = 64 * 1024 * 1024   # playlists más chicas (menús) se tratan como no buscables
LIMITE_FINAL = 32 * 1024 * 1024   # lecturas al final del archivo se sirven sin activar la navegación
COLA_MAX = 4 * 1024 * 1024

IDIOMAS = {"spa": "Español", "eng": "Inglés", "fra": "Francés", "fre": "Francés", "deu": "Alemán",
           "ger": "Alemán", "ita": "Italiano", "por": "Portugués", "jpn": "Japonés", "zho": "Chino",
           "chi": "Chino", "kor": "Coreano", "rus": "Ruso", "nld": "Neerlandés", "dut": "Neerlandés",
           "pol": "Polaco", "cat": "Catalán", "tha": "Tailandés", "ara": "Árabe", "heb": "Hebreo",
           "hin": "Hindi", "swe": "Sueco", "dan": "Danés", "fin": "Finés", "nor": "Noruego",
           "ces": "Checo", "cze": "Checo", "hun": "Húngaro", "tur": "Turco", "ell": "Griego", "gre": "Griego"}
FORMATOS = {0x80: "PCM", 0x81: "Dolby Digital", 0x82: "DTS", 0x83: "Dolby TrueHD",
            0x84: "Dolby Digital Plus", 0x85: "DTS-HD HR", 0x86: "DTS-HD MA", 0xA1: "Dolby Digital Plus",
            0xA2: "DTS-HD"}
CANALES = {1: "Mono", 2: "Estéreo", 6: "5.1", 7: "6.1", 8: "7.1"}


def firmar_extra(lib):
    def f(nombre, args, res):
        fn = getattr(lib, nombre)
        fn.argtypes, fn.restype = args, res
    f("bd_play", [c_void_p], c_int)
    f("bd_read_ext", [c_void_p, c_char_p, c_int, POINTER(Evento)], c_int)
    f("bd_user_input", [c_void_p, c_int64, c_uint32], c_int)
    f("bd_mouse_select", [c_void_p, c_int64, c_uint16, c_uint16], c_int)
    f("bd_menu_call", [c_void_p, c_int64], c_int)
    f("bd_set_player_setting", [c_void_p, c_uint32, c_uint32], c_int)
    f("bd_set_player_setting_str", [c_void_p, c_uint32, c_char_p], c_int)
    f("bd_register_overlay_proc", [c_void_p, c_void_p, PROC_OV], None)
    f("bd_register_argb_overlay_proc", [c_void_p, c_void_p, PROC_ARGB, c_void_p], None)
    f("bd_select_playlist", [c_void_p, c_uint32], c_int)
    f("bd_get_playlist_info", [c_void_p, c_uint32, c_uint], POINTER(base.TitleInfo))


# --- Nombres ---
def nombre_volumen(dispositivo):
    try:
        if os.path.isdir(dispositivo):
            etiqueta = os.path.basename(os.path.normpath(dispositivo))
        elif sys.platform == "win32":
            buf = ctypes.create_unicode_buffer(261)
            ctypes.windll.kernel32.GetVolumeInformationW(dispositivo, buf, 261, None, None, None, None, 0)
            etiqueta = buf.value
        else:
            etiqueta = subprocess.run(["lsblk", "-no", "LABEL", dispositivo], capture_output=True,
                                      text=True, timeout=5).stdout.strip()
    except Exception:
        etiqueta = ""
    return etiqueta.replace("_", " ").strip().title() or None


def etiqueta_idioma(info, lista):
    nombre = IDIOMAS.get(info[1].lower(), info[1] or "Desconocido")
    iguales = [x for x in lista if x[1] == info[1]]
    return f"{nombre} {iguales.index(info) + 1}" if len(iguales) > 1 else nombre


def info_playlist(lib, bd, playlist):
    """(capítulos, audio [(pid, idioma, formato)], subtítulos [(pid, idioma)])"""
    p = lib.bd_get_playlist_info(bd, playlist, 0)
    if not p:
        return [], [], []
    t = p.contents
    caps = [(t.chapters[i].start / 90000, t.chapters[i].duration / 90000) for i in range(t.chapter_count)]
    audio, subs = [], []
    if t.clip_count and t.clips:
        c = ctypes.cast(t.clips, POINTER(InfoClip)).contents
        audio = [(s.pid, s.lang.decode("ascii", "ignore"), FORMATOS.get(s.coding_type, ""))
                 for s in (c.audio_streams[i] for i in range(c.audio_stream_count))]
        subs = [(s.pid, s.lang.decode("ascii", "ignore"))
                for s in (c.pg_streams[i] for i in range(c.pg_stream_count))]
    lib.bd_free_title_info(p)
    return caps, audio, subs


# --- Gráficos de menú ---
class Capas:
    """Compone los planos de menú (HDMV y BD-J) y los muestra en mpv como overlay."""

    def __init__(self, player):
        self.player = player
        self.lock = threading.RLock()
        self.ig = None                      # [índices HxW, máscara HxW]
        self.paleta = np.zeros((256, 4), np.uint8)
        self.argb = None                    # BGRA premultiplicado HxW
        self.final = None
        self.mostrado = None
        self.visible = False
        self.apagado = False
        self.on_visible = None

    def hdmv(self, _h, p):
        with self.lock:
            if self.apagado:
                return
            if not p:
                self.ig = None
                return self._mostrar()
            ov = p.contents
            if ov.plane != 1:               # solo gráficos interactivos; subtítulos los dibuja mpv
                return
            if ov.cmd == OV_INIT:
                self.ig = [np.zeros((ov.h, ov.w), np.uint8), np.zeros((ov.h, ov.w), bool)]
            elif self.ig is None:
                return
            elif ov.cmd == OV_CLOSE:
                self.ig = None
                self._mostrar()
            elif ov.cmd in (OV_CLEAR, OV_HIDE):
                self.ig[1][:] = False
                if ov.cmd == OV_HIDE:
                    self._mostrar()
            elif ov.cmd == OV_WIPE:
                self.ig[1][ov.y:ov.y + ov.h, ov.x:ov.x + ov.w] = False
            elif ov.cmd == OV_DRAW:
                if ov.palette:
                    self._paleta(ov.palette)
                if ov.img:
                    self._rle(ov)
            elif ov.cmd == OV_FLUSH:
                self._mostrar()

    def _paleta(self, pal):
        a = np.ctypeslib.as_array(ctypes.cast(pal, POINTER(c_uint8)), shape=(1024,))
        a = a.reshape(256, 4).astype(np.float32)
        y, cr, cb, t = (a[:, 0] - 16) * 1.164, a[:, 1] - 128, a[:, 2] - 128, a[:, 3]
        bgr = np.stack([y + 2.112 * cb, y - 0.213 * cb - 0.533 * cr, y + 1.793 * cr], 1)
        bgr = np.clip(bgr, 0, 255) * (t[:, None] / 255)
        self.paleta = np.concatenate([bgr, t[:, None]], 1).astype(np.uint8)

    def _rle(self, ov):
        idx, mask = self.ig
        alto, ancho = idx.shape
        img, k = ov.img, 0
        for fila in range(ov.y, ov.y + ov.h):
            x = 0
            while x < ov.w:
                e = img[k]
                k += 1
                if e.len == 0:              # marca de fin de línea
                    continue
                fin = min(x + e.len, ov.w)
                c0, c1 = ov.x + x, min(ov.x + fin, ancho)
                if fila < alto and c0 < c1:
                    idx[fila, c0:c1] = e.color & 0xFF
                    mask[fila, c0:c1] = True
                x = fin

    def bdj(self, _h, p):
        with self.lock:
            if self.apagado:
                return
            if not p:
                self.argb = None
                return self._mostrar()
            ov = p.contents
            if ov.cmd == OV_INIT:
                self.argb = np.zeros((ov.h, ov.w, 4), np.uint8)
            elif self.argb is None:
                return
            elif ov.cmd == OV_CLOSE:
                self.argb = None
                self._mostrar()
            elif ov.cmd == OV_DRAW and ov.argb and ov.w and ov.h:
                src = np.ctypeslib.as_array(ov.argb, shape=((ov.h - 1) * ov.stride + ov.w,))
                filas = np.lib.stride_tricks.as_strided(src, (ov.h, ov.w), (ov.stride * 4, 4))
                region = np.ascontiguousarray(filas).view(np.uint8).reshape(ov.h, ov.w, 4)
                alfa = region[..., 3:4].astype(np.uint16)
                prem = region.copy()
                prem[..., :3] = (region[..., :3] * alfa // 255).astype(np.uint8)
                self.argb[ov.y:ov.y + ov.h, ov.x:ov.x + ov.w] = prem
            elif ov.cmd == OV_FLUSH:
                self._mostrar()

    def _mostrar(self):
        capa = None
        if self.ig is not None and self.ig[1].any():
            capa = np.where(self.ig[1][..., None], self.paleta[self.ig[0]], 0).astype(np.uint8)
        if self.argb is not None and self.argb[..., 3].any():
            if capa is None or capa.shape != self.argb.shape:
                capa = self.argb.copy()
            else:
                alfa = self.argb[..., 3:4].astype(np.uint16)
                capa = (self.argb + capa.astype(np.uint16) * (255 - alfa) // 255).astype(np.uint8)
        self.final = capa
        visible = capa is not None
        if visible != self.visible:
            self.visible = visible
            if self.on_visible:
                self.on_visible(visible)
        self.redibujar()

    def redibujar(self):
        with self.lock:
            if self.apagado:
                return
            try:
                if self.final is None:
                    self.player.command("overlay-remove", 0)
                    self.mostrado = None
                    return
                d = self.player.osd_dimensions
                x, y = int(d["ml"]), int(d["mt"])
                w, h = int(d["w"] - d["ml"] - d["mr"]), int(d["h"] - d["mt"] - d["mb"])
                if w <= 0 or h <= 0:
                    return
                img = self.final
                filas = np.arange(h) * img.shape[0] // h
                cols = np.arange(w) * img.shape[1] // w
                self.mostrado = np.ascontiguousarray(img[filas][:, cols])
                self.player.command("overlay-add", 0, x, y, "&%d" % self.mostrado.ctypes.data,
                                    0, "bgra", w, h, w * 4)
            except Exception:
                pass

    def a_video(self, mx, my):
        """Coordenadas de ventana → coordenadas del plano de menú."""
        img = self.final
        try:
            d = self.player.osd_dimensions
            w, h = d["w"] - d["ml"] - d["mr"], d["h"] - d["mt"] - d["mb"]
            ancho, alto = (img.shape[1], img.shape[0]) if img is not None else (1920, 1080)
            vx, vy = int((mx - d["ml"]) * ancho / w), int((my - d["mt"]) * alto / h)
        except Exception:
            return None
        return (vx, vy) if 0 <= vx < ancho and 0 <= vy < alto else None

    def limpiar(self):
        with self.lock:
            self.ig = self.argb = None
            self._mostrar()


# --- Navegación con menús ---
class Navegacion:
    """Lee el disco en modo menú (bd_play) en un hilo propio y reparte el stream por playlist."""

    def __init__(self, rep):
        self.rep, self.lib = rep, rep.lib
        self.bd = self.lib.bd_open(rep.dispositivo.encode(), rep.keydb.encode() if rep.keydb else None)
        if not self.bd:
            raise RuntimeError("no se pudo abrir el disco en modo menú")
        idioma = rep.idioma.encode()
        for ajuste in (SET_AUDIO_LANG, SET_PG_LANG, SET_MENU_LANG):
            self.lib.bd_set_player_setting_str(self.bd, ajuste, idioma)
        self.lib.bd_set_player_setting_str(self.bd, SET_COUNTRY, b"mx")
        self.lib.bd_set_player_setting(self.bd, SET_REGION, 1)       # región A
        self.lib.bd_set_player_setting(self.bd, SET_DECODE_PG, 0)    # subtítulos: mpv
        # Solo esta sesión dibuja: un menú Java de un disco anterior que siga vivo queda ignorado
        def hdmv(h, p):
            if self.activo:
                rep.capas.hdmv(h, p)

        def bdj(h, p):
            if self.activo:
                rep.capas.bdj(h, p)
        self.activo = True
        self._cb = (PROC_OV(hdmv), PROC_ARGB(bdj))
        self.lib.bd_register_overlay_proc(self.bd, None, self._cb[0])
        self.lib.bd_register_argb_overlay_proc(self.bd, None, self._cb[1], None)

        self.cond = threading.Condition()
        self.bdlock = threading.Lock()
        self.datos = deque()                # (segmento, bytes)
        self.en_cola = 0
        self.gen = 0
        self.seg = 0
        self.segmentos = {}                 # segmento → (playlist, tamaño)
        self.activo = True
        self.error_bdj = False
        self.en_pausa = False             # imagen fija o menú esperando
        self.cortado = False              # el segmento se cerró por imagen fija
        self.playlist_actual = None

        if not self.lib.bd_play(self.bd):
            self.lib.bd_close(self.bd)
            raise RuntimeError("el disco no permite arrancar con menú")
        self.hilo = threading.Thread(target=self._leer, daemon=True)
        self.hilo.start()

    def _leer(self):
        buf = ctypes.create_string_buffer(base.BLOQUE * 32)
        ev = Evento()
        while self.activo:
            with self.cond:
                while self.activo and self.en_cola > COLA_MAX:
                    self.cond.wait(0.2)
            with self.bdlock:
                gen = self.gen
                r = self.lib.bd_read_ext(self.bd, buf, len(buf), ctypes.byref(ev))
            if ev.event:
                self._evento(ev.event, ev.param)
            if r > 0:
                nuevo = None
                with self.cond:
                    if gen == self.gen:
                        self.en_pausa = False
                        if self.cortado:            # sigue la misma playlist tras una imagen fija
                            self.cortado = False
                            self.seg += 1
                            self.segmentos[self.seg] = (self.playlist_actual, 0)
                            nuevo = self.seg
                        self.datos.append((self.seg, buf.raw[:r]))
                        self.en_cola += r
                        self.cond.notify_all()
                if nuevo:
                    self.rep.nueva_playlist(self.playlist_actual, nuevo, continua=True)
            elif r < 0:
                self.rep.error_lectura(-1)
                break
            elif not ev.event or ev.event == EV_IDLE:
                if ev.event == EV_IDLE:
                    self.en_pausa = True
                time.sleep(0.04)            # imagen fija o menú sin video: esperar

    def _evento(self, e, p):
        if e == EV_PLAYLIST:
            with self.cond:
                self.seg += 1
                self.playlist_actual, self.cortado, self.en_pausa = p, False, False
                self.segmentos[self.seg] = (p, self.lib.bd_get_title_size(self.bd))
                self.cond.notify_all()
            self.rep.nueva_playlist(p, self.seg)
        elif e == EV_STILL:
            self.en_pausa = bool(p)
        elif e == EV_STILL_TIME:
            self.en_pausa = True
        elif e == EV_ERROR:
            if p == 2:
                self.error_bdj = True
            print(f"Error de navegación del disco ({'BD-J' if p == 2 else 'HDMV'}).")
        elif e in (EV_ENCRYPTED, EV_READ_ERROR):
            self.rep.error_lectura(e)
        else:
            self.rep.evento_pista(e, p)

    def entrada(self, tecla):
        self.lib.bd_user_input(self.bd, -1, tecla)

    def detener(self):
        self.activo = False
        with self.cond:
            self.cond.notify_all()

    def cerrar(self):
        self.detener()
        self.hilo.join(2)
        if not self.hilo.is_alive():
            self.lib.bd_close(self.bd)


class Segmento:
    """Una playlist del modo menú vista por mpv como archivo."""

    def __init__(self, nav, n, aux):
        self.nav, self.n, self.aux = nav, n, aux
        self.playlist, tam = nav.segmentos.get(n, (None, 0))
        self.size = tam if tam >= MIN_BUSCABLE else None
        self.pend = b""
        self.saltar = 0
        self.en_aux = False

    def read(self, tam):
        while True:
            if self.pend:
                d, self.pend = self.pend[:tam], self.pend[tam:]
                return d
            if self.en_aux:
                return self._leer_aux(tam)
            nav = self.nav
            with nav.cond:
                espera = 0.0
                while True:
                    if not nav.activo:
                        return b""
                    if nav.datos:
                        seg, d = nav.datos[0]
                        if seg > self.n:
                            return b""      # fin de esta playlist
                        nav.datos.popleft()
                        nav.en_cola -= len(d)
                        nav.cond.notify_all()
                        if seg == self.n:
                            break
                    elif nav.seg > self.n:
                        return b""
                    elif nav.en_pausa and espera >= 0.3:
                        nav.cortado = True  # imagen fija: cerrar para que mpv muestre el último cuadro
                        return b""
                    else:
                        nav.cond.wait(0.1)
                        espera += 0.1
            if self.saltar:
                q = min(self.saltar, len(d))
                d, self.saltar = d[q:], self.saltar - q
            self.pend = d

    def seek(self, pos):
        self.pend = b""
        if self.size and pos >= self.size - LIMITE_FINAL:
            # mpv lee el final para calcular la duración: se sirve desde otra conexión al disco
            self.en_aux = True
            self.aux.lib.bd_select_playlist(self.aux.bd, self.playlist)
            real = self.aux.lib.bd_seek(self.aux.bd, pos - pos % base.BLOQUE)
            self.saltar = max(0, pos - real)
            return pos
        self.en_aux = False
        nav = self.nav
        with nav.bdlock:
            with nav.cond:
                if nav.seg != self.n:
                    raise ValueError("la playlist ya no está activa")
                nav.gen += 1
                nav.datos.clear()
                nav.en_cola = 0
                nav.cond.notify_all()
            real = nav.lib.bd_seek(nav.bd, pos - pos % base.BLOQUE)
        self.saltar = max(0, pos - real)
        return pos

    def _leer_aux(self, tam):
        buf = ctypes.create_string_buffer(max(tam, base.BLOQUE))
        while True:
            r = self.aux.lib.bd_read(self.aux.bd, buf, len(buf))
            if r <= 0:
                return b""
            d = buf.raw[:r]
            if self.saltar:
                q = min(self.saltar, len(d))
                d, self.saltar = d[q:], self.saltar - q
            if d:
                self.pend = d[tam:]
                return d[:tam]

    def close(self):
        pass


# --- Reproductor ---
class Reproductor:
    def __init__(self, args):
        self.dispositivo = args.dispositivo
        if sys.platform == "win32" and len(self.dispositivo) == 2 and self.dispositivo[1] == ":":
            self.dispositivo += "\\"
        self.idioma = args.idioma
        self.keydb, origen = base.buscar_keydb()
        print(f"KEYDB.cfg: {self.keydb} ({origen})" if self.keydb else "KEYDB.cfg: no encontrado.")
        self.lib = base.cargar_libbluray()
        firmar_extra(self.lib)
        self.disco = base.Disco(self.lib, self.dispositivo, self.keydb)   # modo título (respaldo)
        self.aux = base.Disco(self.lib, self.dispositivo, self.keydb)     # información y lecturas auxiliares
        self.nombre = self.disco.nombre() or nombre_volumen(args.dispositivo) or "Blu-ray"
        self.principal = self.disco.principal()
        print(f"Disco: {self.nombre}")

        self.audio, self.subs = [], []
        self.sel = {"ruta": None, "aid": None, "sid": None, "subs_on": None, "pendiente": False}
        self.lock_sel = threading.Lock()
        self.temporales = []
        self.nav = None
        self.teclas_menu = False
        self.fin = threading.Event()

        self.mpv = self._crear_mpv()
        self.capas = Capas(self.mpv)
        self.capas.on_visible = self._modo_menu

        @self.mpv.register_stream_protocol("bdpy")
        def _nav(uri):
            return Segmento(self.nav, int(uri.rsplit("/", 1)[1]), self.aux)

        @self.mpv.register_stream_protocol("bdtit")
        def _tit(uri):
            return base.StreamBD(self.disco, self.principal)

        @self.mpv.event_callback("shutdown")
        def _fin(_ev):
            self.fin.set()

        self.mpv.observe_property("osd-dimensions", lambda *_: self.capas.redibujar())
        self.mpv.observe_property("track-list", lambda *_: self.aplicar_pistas())
        self.mpv.observe_property("aid", lambda _n, v: self._osd_pista("aid", v))
        self.mpv.observe_property("sid", lambda _n, v: self._osd_pista("sid", v))
        self._atajos()

    def _crear_mpv(self):
        import mpv
        return mpv.MPV(config=False, ytdl=False, osc=True, hwdec="auto", idle="yes",
                       force_window="yes", keep_open="yes", autofit_larger="90%x85%",
                       input_default_bindings=True, input_vo_keyboard=True, title=self.nombre)

    def _atajos(self):
        for tecla in ("q", "Q", "CLOSE_WIN"):
            self.mpv.register_key_binding(tecla, self.salir)
        for tecla, (vk, comando) in TECLAS_MENU.items():
            self.mpv.register_key_binding(tecla, self._tecla(vk, comando))
        self.mpv.register_key_binding("F2", self._pulsacion(lambda: self.nav and
                                                             self.lib.bd_menu_call(self.nav.bd, -1)))
        self.mpv.register_key_binding("F3", self._pulsacion(lambda: self.nav and self.nav.entrada(VK_POPUP)))

    # Teclado y ratón
    @staticmethod
    def _pulsacion(accion):
        def cb(estado, *_):
            if estado and estado[0] in "dp":
                accion()
        return cb

    def _tecla(self, vk, comando):
        """Con un menú en pantalla la tecla va al disco; si no, hace su acción normal."""
        def cb(estado, *_):
            if not estado or estado[0] not in "dpr":
                return
            if self.nav and self.capas.visible:
                if estado[0] != "r":
                    self.nav.entrada(vk)
            elif comando:
                self.mpv.command(*comando.split())
        return cb

    def _modo_menu(self, activo):
        """Con un menú en pantalla, el ratón va al disco."""
        if not self.nav or activo == self.teclas_menu:
            return
        self.teclas_menu = activo
        teclas = {}
        teclas["MOUSE_MOVE"] = lambda *_: self._raton(False)
        teclas["MBTN_LEFT"] = self._pulsacion(lambda: self._raton(True))
        for tecla, cb in teclas.items():
            try:
                if activo:
                    self.mpv.register_key_binding(tecla, cb)
                else:
                    self.mpv.unregister_key_binding(tecla)
            except Exception:
                pass

    def _raton(self, clic):
        if not self.nav:
            return
        try:
            m = self.mpv.mouse_pos
            pos = self.capas.a_video(m["x"], m["y"])
        except Exception:
            return
        if pos:
            self.lib.bd_mouse_select(self.nav.bd, -1, *pos)
            if clic:
                self.nav.entrada(VK_MOUSE_ACTIVATE)

    def salir(self, estado="p-", *_):
        if estado and estado[0] in "dp":
            if self.nav:
                self.nav.detener()
            self.mpv.command("quit")

    # Playlists y pistas
    def _capitulos(self, caps):
        if not caps:
            return ""
        f = tempfile.NamedTemporaryFile("w", suffix=".ffmeta", delete=False, encoding="utf-8")
        f.write(";FFMETADATA1\n")
        for n, (ini, dur) in enumerate(caps, 1):
            f.write(f"[CHAPTER]\nTIMEBASE=1/1000\nSTART={int(ini * 1000)}\n"
                    f"END={int((ini + dur) * 1000)}\ntitle=Capítulo {n}\n")
        f.close()
        self.temporales.append(f.name)
        return f.name

    def nueva_playlist(self, playlist, seg, continua=False):
        ruta = f"bdpy://seg/{seg}"
        if continua:    # misma playlist tras una imagen fija: conservar pistas elegidas
            with self.lock_sel:
                s = self.sel
                s.update(ruta=ruta, pendiente=s["aid"] is not None or s["subs_on"] is not None)
        else:
            caps, self.audio, self.subs = info_playlist(self.lib, self.aux.bd, playlist)
            with self.lock_sel:
                self.sel.update(ruta=ruta, aid=None, sid=None, subs_on=None, pendiente=False)
            self.mpv["chapters-file"] = self._capitulos(caps)
        self._cargar(ruta)

    def _cargar(self, ruta):
        try:
            terminado = self.mpv.idle_active or self.mpv.eof_reached
        except Exception:
            terminado = True
        if terminado:   # nada reproduciéndose (o detenido en el último cuadro): cargar ya
            self.mpv.command("loadfile", ruta, "replace")
            self.mpv.pause = False
        else:           # al terminar lo que se reproduce
            self.mpv.command("loadfile", ruta, "append-play")

    def error_lectura(self, e):
        """e: EV_ENCRYPTED (falta la clave), EV_READ_ERROR (bloque ilegible) o -1 (lectura detenida)."""
        if not getattr(self, "_avisado_lectura", False):
            self._avisado_lectura = True
            print("No se pudo leer o descifrar parte del disco"
                  + (" (falta la clave de este disco en KEYDB.cfg)." if e == EV_ENCRYPTED else "."))

    def evento_pista(self, e, p):
        with self.lock_sel:
            if e == EV_AUDIO_STREAM and 1 <= p <= len(self.audio):
                self.sel["aid"] = self.audio[p - 1][0]
            elif e == EV_PG_TEXTST_STREAM and 1 <= p <= len(self.subs):
                self.sel["sid"] = self.subs[p - 1][0]
            elif e == EV_PG_TEXTST:
                self.sel["subs_on"] = bool(p)
            else:
                return
            self.sel["pendiente"] = True
        self.aplicar_pistas()

    def aplicar_pistas(self):
        """Aplica en mpv las pistas que eligió el disco (o su menú de idiomas)."""
        with self.lock_sel:
            s = self.sel
            if not s["pendiente"]:
                return
            try:
                if self.mpv.path != s["ruta"]:
                    return
                pistas = self.mpv.track_list or []
            except Exception:
                return
            if not pistas:
                return
            buscar = lambda tipo, pid: next((t["id"] for t in pistas if t.get("type") == tipo
                                             and t.get("src-id") == pid), None)
            if s["aid"] is not None and buscar("audio", s["aid"]):
                self.mpv.aid = buscar("audio", s["aid"])
            if s["subs_on"] is False:
                self.mpv.sid = "no"
            elif s["subs_on"] and s["sid"] is not None and buscar("sub", s["sid"]):
                self.mpv.sid = buscar("sub", s["sid"])
            s["pendiente"] = False

    def _aviso(self, texto):
        self.mpv.command("show-text", texto, 2500)

    def _nombre_pista(self, prop, t):
        lista = self.audio if prop == "aid" else self.subs
        info = next((x for x in lista if x[0] == t.get("src-id")), None)
        partes = [etiqueta_idioma(info, lista) if info else f"Pista {t.get('id')}"]
        if prop == "aid":
            if info and info[2]:
                partes.append(info[2])
            canales = t.get("demux-channel-count")
            if canales:
                partes.append(CANALES.get(canales, f"{canales} canales"))
        return " · ".join(partes)

    def _osd_pista(self, prop, valor):
        if valor in (None, "auto"):
            return
        if valor in (False, "no"):
            if prop == "sid":
                self._aviso("Subtítulos: desactivados")
            return
        try:
            tipo = "audio" if prop == "aid" else "sub"
            t = next(t for t in self.mpv.track_list if t["type"] == tipo and t["id"] == valor)
        except Exception:
            return
        self._aviso(("Audio: " if prop == "aid" else "Subtítulos: ") + self._nombre_pista(prop, t))

    def reproducir_titulo(self):
        pl = next((t[3] for t in self.disco.titulos() if t[0] == self.principal), None)
        caps, self.audio, self.subs = info_playlist(self.lib, self.aux.bd, pl) if pl is not None else ([], [], [])
        preferido = next((a[0] for a in self.audio if a[1] == self.idioma), None)
        with self.lock_sel:
            self.sel.update(ruta="bdtit://principal", aid=preferido, sid=None, subs_on=None,
                            pendiente=preferido is not None)
        self.mpv["chapters-file"] = self._capitulos(caps)
        self.mpv.command("loadfile", "bdtit://principal", "replace")
        self.mpv.pause = False

    def ejecutar(self, sin_menu):
        if not sin_menu:
            try:
                self.nav = Navegacion(self)
                print("Modo: menú del disco (F2 menú principal, F3 menú emergente)")
            except RuntimeError as e:
                print(f"Sin menú: {e}.")
        if not self.nav:
            print("Modo: película directa")
            self.reproducir_titulo()
        try:
            while not self.fin.wait(0.3):
                if self.nav and self.nav.error_bdj:
                    print("El menú Java no se pudo ejecutar; se reproduce la película directamente.")
                    self.nav.cerrar()
                    self.nav = None
                    self._modo_menu(False)
                    self.capas.limpiar()
                    self.reproducir_titulo()
        finally:
            self.capas.apagado = True
            if self.nav:
                self.nav.cerrar()
            self.mpv.terminate()
            self.disco.cerrar()
            self.aux.cerrar()
            for ruta in self.temporales:
                try:
                    os.unlink(ruta)
                except OSError:
                    pass
