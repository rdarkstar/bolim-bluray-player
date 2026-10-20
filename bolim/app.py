#!/usr/bin/env python3
"""
Bolim Bluray Player — interfaz (Qt Quick) y controlador.
"""
import argparse
import ctypes
import ctypes.util
import json
import locale
import os
import subprocess
import sys
import threading

os.environ.setdefault("QSG_RENDER_LOOP", "basic")   # video y controles en el mismo hilo: cierre limpio

from PySide6.QtCore import Property, QObject, QTimer, QUrl, Signal, Slot
from PySide6.QtGui import QGuiApplication, QOpenGLContext
from PySide6.QtQml import QQmlApplicationEngine, qmlRegisterType
from PySide6.QtQuick import QQuickFramebufferObject, QQuickWindow, QSGRendererInterface

try:
    from PySide6.QtQuick import QQuickOpenGLUtils
    _reset_gl = QQuickOpenGLUtils.resetOpenGLState
except ImportError:
    _reset_gl = None

import mpv

from . import menus as nav2
from . import componentes
from .menus import TECLAS_MENU, VK_MOUSE_ACTIVATE, VK_POPUP, Navegacion, etiqueta_idioma, info_playlist

DIR = os.path.dirname(os.path.abspath(__file__))


# --- Video de mpv dentro de QML (API de render OpenGL) ---
_gl = {}


def _cargar_gl(nombre, funcion, actual=None):
    try:
        lib = ctypes.CDLL(ctypes.util.find_library(nombre))
        f = getattr(lib, funcion)
        f.argtypes, f.restype = [ctypes.c_char_p], ctypes.c_void_p
        if actual:
            getattr(lib, actual).restype = ctypes.c_void_p
        return lib
    except Exception:
        return None


def _direccion_gl(_ctx, nombre):
    try:
        d = QOpenGLContext.currentContext().getProcAddress(nombre)
        if d:
            return int(d)
    except Exception:
        pass
    if not _gl:
        _gl["egl"] = _cargar_gl("EGL", "eglGetProcAddress", "eglGetCurrentContext")
        _gl["glx"] = _cargar_gl("GL", "glXGetProcAddressARB")
    egl, glx = _gl["egl"], _gl["glx"]
    if egl and egl.eglGetCurrentContext():
        return egl.eglGetProcAddress(nombre) or 0
    return (glx.glXGetProcAddressARB(nombre) or 0) if glx else 0


_DIR_GL = mpv.MpvGlGetProcAddressFn(_direccion_gl)


class Lienzo(QQuickFramebufferObject.Renderer):
    def __init__(self, item):
        super().__init__()
        self.item = item
        self.ctx = None

    def createFramebufferObject(self, size):
        if self.ctx is None and MpvVideo.player:
            self.ctx = mpv.MpvRenderContext(MpvVideo.player, "opengl",
                                            opengl_init_params={"get_proc_address": _DIR_GL})
            self.ctx.update_cb = self.item.pedir_cuadro.emit
        return super().createFramebufferObject(size)

    def render(self):
        it = self.item
        if it.liberar_pendiente:
            if self.ctx:
                self.ctx.free()
                self.ctx = None
            it.liberar_pendiente = False
            it.liberado.emit()
            return
        if self.ctx is None:
            return
        fbo = self.framebufferObject()
        self.ctx.render(flip_y=False, opengl_fbo={"fbo": fbo.handle(), "w": fbo.width(), "h": fbo.height()})
        if _reset_gl:
            _reset_gl()


class MpvVideo(QQuickFramebufferObject):
    player = None
    instancia = None
    pedir_cuadro = Signal()
    liberado = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        MpvVideo.instancia = self
        self.liberar_pendiente = False
        self._lienzo = None
        self.setMirrorVertically(False)
        self.pedir_cuadro.connect(self.update)

    def createRenderer(self):
        self._lienzo = Lienzo(self)
        return self._lienzo

    def liberar(self):
        self.liberar_pendiente = True
        self.update()


# --- Controlador: une el motor de la fase 2 con la interfaz ---
class DiscoVacio:
    """Sustituto cuando no hay disco en la unidad."""
    bd = None
    num_titulos = 0

    def nombre(self):
        return None

    def principal(self):
        return -1

    def titulos(self):
        return []

    def cerrar(self):
        pass


class _Motor(nav2.Reproductor):
    """PySide6 llama en cadena a los __init__ de las clases base (sin argumentos):
    esa llamada se ignora y el motor se inicia explícitamente con los argumentos."""

    def __init__(self, args=None):
        if args is None:
            return
        original = nav2.base.Disco

        def abrir(*a):                      # sin disco: arrancar igual, en la pantalla "Sin disco"
            try:
                return original(*a)
            except RuntimeError:
                return DiscoVacio()
        nav2.base.Disco = abrir
        try:
            super().__init__(args)
        finally:
            nav2.base.Disco = original


class Control(QObject, _Motor):
    cambio = Signal()

    def __init__(self, args, lista_componentes=None, registro=""):
        QObject.__init__(self)
        self._comp = lista_componentes or []
        self._lock_e = threading.Lock()
        self._e = dict(titulo="", modo="inicio", posicion=0.0, duracion=0.0, pausado=False, velocidad=1.0,
                       volumen=100.0, silencio=False, capitulos=[], menuVisible=False, inactivo=True,
                       audio=[], subs=[], aviso="", avisoN=0, duracionPrincipal=0.0,
                       inicioCapitulos=[], inicioAudio=[], inicioSubs=[], inicioAudioSel=0, inicioSubSel=0,
                       hayDisco=True, cargando=False, reanudarPos=0.0, enPeliculaDisco=False,
                       inicioTitulos=[], sinClave=False, claveMensaje="",
                       componentes=self._comp, registro=registro,
                       avisosComp=sum(1 for c in self._comp if c["estado"] != componentes.OK))
        self._falta_clave = False
        self._nav_fallo = False
        self._errores_lectura = 0
        self._otros = []
        self._pelis = {}
        self._reanudar = None
        self._pl = None
        self._disp_original = args.dispositivo
        self._ultima_pos = -1.0
        self._saliendo = False
        self._terminado = False
        _Motor.__init__(self, args)
        self.lib.bd_tell_time.argtypes, self.lib.bd_tell_time.restype = [ctypes.c_void_p], ctypes.c_uint64
        self._preparar_inicio()
        for p in ("time-pos", "duration", "pause", "speed", "volume", "mute", "chapter-list",
                  "idle-active", "track-list", "aid", "sid"):
            self.mpv.observe_property(p, self._prop)

        @self.mpv.event_callback("file-loaded")
        def _cargado(_ev):
            try:
                self.mpv["start"] = "none"
            except Exception:
                pass

        @self.mpv.register_stream_protocol("bdotro")
        def _otro(uri):
            return nav2.base.StreamBD(self.disco, int(uri.rsplit("/", 1)[1]))

        self._carga = QTimer(self)
        self._carga.timeout.connect(self._intentar_carga)
        self._intentos = 0
        self._revision = QTimer(self)
        self._revision.timeout.connect(self._revisar)
        self._revision.start(300)

    # Estado para QML
    def _get_e(self):
        return self._e

    e = Property("QVariantMap", _get_e, notify=cambio)

    def _set(self, **cambios):
        with self._lock_e:
            self._e = {**self._e, **cambios}
        self.cambio.emit()

    # Reemplazos de la fase 2b
    def _crear_mpv(self):
        p = mpv.MPV(vo="libmpv", config=False, ytdl=False, osc=False, hwdec="auto-safe", idle="yes",
                    keep_open="yes", input_default_bindings=False, osd_on_seek="no",
                    demuxer_lavf_analyzeduration=1.5)
        MpvVideo.player = p
        return p

    def _atajos(self):
        pass                                # el teclado lo maneja la interfaz

    def _modo_menu(self, activo):
        self._set(menuVisible=bool(activo))

    def _aviso(self, texto):
        self._set(aviso=texto, avisoN=self._e["avisoN"] + 1)

    # Datos de la pantalla de inicio
    def _preparar_inicio(self):
        if not self.disco or not self.disco.bd:
            self._pl = None
            self._set(hayDisco=False, titulo="Sin disco", reanudarPos=0.0)
            return
        self._pelis = {}
        info = next((t for t in self.disco.titulos() if t[0] == self.principal), None)
        pl = info[3] if info else None
        caps, audio, subs = info_playlist(self.lib, self.aux.bd, pl) if pl is not None else ([], [], [])
        self._inicio = (caps, audio, subs)
        self._pl = pl
        total = info[1] if info else 0
        self._otros = [t for t in self.disco.titulos()
                       if t[0] != self.principal and t[1] >= 20 and not (total and abs(t[1] - total) < total * 0.03)]
        self._clave = f"{self.nombre}|{int(info[1]) if info else 0}"
        self._reanudar = self._leer_reanudar().get(self._clave)
        error = self.disco.probar_lectura(self.principal) if self.principal >= 0 else None
        self._set(sinClave=bool(error), claveMensaje=self._mensaje_clave() if error else "")
        if error:
            print("Aviso: no se puede descifrar este disco (" + error + ").")
        self._set(titulo=self.nombre, hayDisco=True,
                  reanudarPos=self._reanudar["pos"] if self._reanudar else 0.0,
                  duracionPrincipal=info[1] if info else 0.0,
                  inicioCapitulos=[f"Capítulo {n}   ·   {nav2.base.hms(ini)}" for n, (ini, _) in enumerate(caps, 1)],
                  inicioAudio=[" · ".join(x for x in (etiqueta_idioma(a, audio), a[2]) if x) for a in audio],
                  inicioSubs=["Desactivados"] + [etiqueta_idioma(s, subs) for s in subs],
                  inicioAudioSel=next((i for i, a in enumerate(audio) if a[1] == self.idioma), 0),
                  inicioSubSel=0,
                  inicioTitulos=[f"Título {n}   ·   {nav2.base.hms(dur)}" + (f"   ·   {c} capítulos" if c > 1 else "")
                                 for n, (_, dur, c, _) in enumerate(self._otros, 1)])

    # Propiedades de mpv
    def _prop(self, nombre, v):
        if nombre == "time-pos":
            if v is None or abs(v - self._ultima_pos) < 0.25:
                return
            self._ultima_pos = v
            self._set(posicion=max(0.0, v))
        elif nombre == "duration":
            self._set(duracion=v or 0.0)
        elif nombre == "pause":
            self._set(pausado=bool(v))
        elif nombre == "speed":
            self._set(velocidad=v or 1.0)
        elif nombre == "volume":
            self._set(volumen=v or 0.0)
        elif nombre == "mute":
            self._set(silencio=bool(v))
        elif nombre == "chapter-list":
            self._set(capitulos=[c.get("time", 0.0) for c in (v or [])])
        elif nombre == "idle-active":
            self._set(inactivo=bool(v))
        else:
            self._set(**self._listas_pistas())

    def _listas_pistas(self):
        try:
            pistas = self.mpv.track_list or []
        except Exception:
            pistas = []
        audio = [{"id": t["id"], "nombre": self._nombre_pista("aid", t), "sel": bool(t.get("selected"))}
                 for t in pistas if t.get("type") == "audio"]
        subs = [{"id": t["id"], "nombre": self._nombre_pista("sid", t), "sel": bool(t.get("selected"))}
                for t in pistas if t.get("type") == "sub"]
        subs.insert(0, {"id": 0, "nombre": "Desactivados", "sel": not any(s["sel"] for s in subs)})
        return {"audio": audio, "subs": subs}

    # Acciones desde la interfaz
    @Slot(int)
    def elegirAudioInicio(self, i):
        self._set(inicioAudioSel=i)

    @Slot(int)
    def elegirSubInicio(self, i):
        self._set(inicioSubSel=i)

    @Slot(int)
    def reproducirPelicula(self, capitulo):
        caps, audio, subs = self._inicio
        a, s = self._e["inicioAudioSel"], self._e["inicioSubSel"]
        aid = audio[a][0] if 0 <= a < len(audio) else None
        sid = subs[s - 1][0] if 1 <= s <= len(subs) else None
        self._iniciar_pelicula(caps[capitulo][0] if 0 <= capitulo < len(caps) else 0.0, aid, sid)

    @Slot(int)
    def reproducirTitulo(self, i):
        """Reproduce un extra (escenas eliminadas, tráileres…) en modo directo."""
        if not (0 <= i < len(self._otros)) or not self._e["hayDisco"]:
            return
        if self._e["sinClave"]:
            self._aviso("No hay clave para descifrar este disco. Revisa tu archivo KEYDB.cfg.")
            return
        idx, _, _, pl = self._otros[i]
        self._cerrar_nav()
        caps, self.audio, self.subs = info_playlist(self.lib, self.aux.bd, pl)
        ruta = f"bdotro://titulo/{idx}"
        aid = next((a[0] for a in self.audio if a[1] == self.idioma), None)
        with self.lock_sel:
            self.sel.update(ruta=ruta, aid=aid, sid=None, subs_on=False, pendiente=True)
        self.mpv["chapters-file"] = self._capitulos(caps)
        self.mpv["start"] = "none"
        self.mpv.command_async("loadfile", ruta, "replace")
        self.mpv.pause = False
        self._set(modo="extra")

    @Slot()
    def reanudar(self):
        r = self._reanudar
        if r:
            self._iniciar_pelicula(r["pos"], r.get("aid"), r.get("sid"))

    def _iniciar_pelicula(self, inicio, aid, sid):
        if not self._e["hayDisco"]:
            return
        if self._e["sinClave"]:
            self._aviso("No hay clave para descifrar este disco. Revisa tu archivo KEYDB.cfg.")
            return
        self._cerrar_nav()
        caps, audio, subs = self._inicio
        self.audio, self.subs = audio, subs
        with self.lock_sel:
            self.sel.update(ruta="bdtit://principal", aid=aid, sid=sid, subs_on=sid is not None, pendiente=True)
        self.mpv["chapters-file"] = self._capitulos(caps)
        self.mpv["start"] = str(inicio) if inicio > 0 else "none"
        self.mpv.command_async("loadfile", "bdtit://principal", "replace")
        self.mpv.pause = False
        self._set(modo="pelicula")

    @Slot()
    def menuDisco(self):
        if not self._e["hayDisco"]:
            return
        self._recordar_posicion()
        if self.nav:
            self.lib.bd_menu_call(self.nav.bd, -1)
            return
        self.mpv.command_async("stop")
        self._falta_clave = self._nav_fallo = False
        self._errores_lectura = 0
        try:
            self.nav = Navegacion(self)
            self._set(modo="disco")
        except RuntimeError as err:
            self._aviso(f"Menú del disco no disponible: {err}")

    @Slot()
    def detener(self):
        self._recordar_posicion()
        self._cerrar_nav()
        self.mpv.command_async("stop")
        self.mpv.speed = 1
        self._set(modo="inicio", posicion=0.0, duracion=0.0)

    @Slot()
    def pausa(self):
        self.mpv.pause = not self.mpv.pause

    @Slot(float)
    def buscar(self, segundos):
        self.mpv.command("seek", segundos, "relative")

    @Slot(float)
    def irA(self, fraccion):
        self.mpv.command("seek", max(0.0, min(100.0, fraccion * 100)), "absolute-percent")

    @Slot(int)
    def capituloRel(self, n):
        self.mpv.command("add", "chapter", n)

    @Slot(float)
    def velocidad(self, v):
        self.mpv.speed = max(0.25, min(8.0, v))

    @Slot()
    def velocidadNormal(self):
        self.mpv.speed = 1

    @Slot(float)
    def volumen(self, v):
        self.mpv.volume = max(0.0, min(100.0, v))

    @Slot()
    def silencio(self):
        self.mpv.mute = not self.mpv.mute

    @Slot(str, int)
    def pista(self, prop, tid):
        setattr(self.mpv, prop, "no" if (prop == "sid" and tid == 0) else tid)

    @Slot(str)
    def tecla(self, nombre):
        if self.nav and self.capas.visible and nombre in TECLAS_MENU:
            self.nav.entrada(TECLAS_MENU[nombre][0])
            return
        acciones = {
            "LEFT": lambda: self.buscar(-5), "RIGHT": lambda: self.buscar(5),
            "UP": lambda: self.buscar(60), "DOWN": lambda: self.buscar(-60),
            "SPACE": self.pausa, "F2": self.menuDisco, "M": self.silencio,
            "F3": lambda: self.nav and self.nav.entrada(VK_POPUP),
            "BACKSPACE": self.velocidadNormal,
            "[": lambda: self.velocidad(self.mpv.speed / 2), "]": lambda: self.velocidad(self.mpv.speed * 2),
            "PGUP": lambda: self.capituloRel(-1), "PGDOWN": lambda: self.capituloRel(1),
            "R": self.reanudarAqui,
            "A": lambda: self.mpv.command("cycle", "audio"), "S": lambda: self.mpv.command("cycle", "sub"),
        }
        if nombre in acciones and self._e["modo"] != "inicio":
            acciones[nombre]()

    @Slot(float, float, bool)
    def ratonMenu(self, fx, fy, clic):
        if not self.nav:
            return
        try:
            d = self.mpv.osd_dimensions
            pos = self.capas.a_video(fx * d["w"], fy * d["h"])
        except Exception:
            return
        if pos:
            self.lib.bd_mouse_select(self.nav.bd, -1, *pos)
            if clic:
                self.nav.entrada(VK_MOUSE_ACTIVATE)

    @Slot()
    def salir(self):
        if self._saliendo:
            return
        self._saliendo = True
        self._recordar_posicion()
        if self.nav:
            self.nav.detener()              # sin esperar al hilo: el proceso termina enseguida
        self.capas.apagado = True
        v = MpvVideo.instancia
        if v and v._lienzo and v._lienzo.ctx:
            v.liberar()
            try:
                w = v.window()
                if w:
                    w.grabWindow()          # fuerza un cuadro para liberar el video de forma ordenada
            except Exception:
                pass
        self._terminar()

    @Slot()
    def expulsar(self):
        self._recordar_posicion()
        self._cerrar_nav()
        self.mpv.command_async("stop")
        self._set(modo="inicio", hayDisco=False, reanudarPos=0.0, posicion=0.0, duracion=0.0, titulo="Sin disco")
        QTimer.singleShot(600, self._expulsar_fisico)

    def _expulsar_fisico(self):
        if not self._e["inactivo"]:                 # esperar a que mpv suelte el disco
            QTimer.singleShot(300, self._expulsar_fisico)
            return
        for d in (self.disco, self.aux):
            if d:
                d.cerrar()
        self.disco = self.aux = None
        threading.Thread(target=self._abrir_bandeja, daemon=True).start()

    def _abrir_bandeja(self):
        try:
            if sys.platform == "win32":
                mci, letra = ctypes.windll.winmm.mciSendStringW, self.dispositivo[:2]
                mci(f"open {letra} type cdaudio alias bdp", None, 0, None)
                mci("set bdp door open", None, 0, None)
                mci("close bdp", None, 0, None)
            elif subprocess.run(["eject", self.dispositivo], capture_output=True, timeout=30).returncode:
                self._aviso("No se pudo expulsar el disco (¿lo está usando otro programa?)")
        except Exception:
            self._aviso("No se pudo expulsar el disco.")

    @Slot()
    def reintentar(self):
        """Releer el archivo de claves y el disco (por ejemplo, después de agregar la clave)."""
        self._cerrar_nav()
        for d in (self.disco, self.aux):
            if d:
                d.cerrar()
        self.disco = self.aux = None
        self.keydb, _ = nav2.base.buscar_keydb()
        self._comp = componentes.revisar()
        self._set(sinClave=False, hayDisco=False, reanudarPos=0.0, componentes=self._comp,
                  avisosComp=sum(1 for c in self._comp if c["estado"] != componentes.OK))
        self.cargarDisco()

    @Slot()
    def cargarDisco(self):
        if self._e["cargando"]:
            return
        self._set(cargando=True)
        if sys.platform != "win32":                 # cerrar la bandeja si está abierta
            subprocess.Popen(["eject", "-t", self.dispositivo],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self._intentos = 0
        self._carga.start(2000)

    def _intentar_carga(self):
        self._intentos += 1
        if self._intentos == 1:
            self.keydb, _ = nav2.base.buscar_keydb()
        try:
            disco = nav2.base.Disco(self.lib, self.dispositivo, self.keydb)
            if not disco.num_titulos:
                disco.cerrar()
                raise RuntimeError
        except RuntimeError:
            if self._intentos >= 20:                # unos 40 segundos
                self._carga.stop()
                self._set(cargando=False)
                self._aviso("No se detectó un Blu-ray en la unidad.")
            return
        self._carga.stop()
        self.disco = disco
        self.aux = nav2.base.Disco(self.lib, self.dispositivo, self.keydb)
        self.nombre = disco.nombre() or nav2.nombre_volumen(self._disp_original) or "Blu-ray"
        self.principal = disco.principal()
        self.capas.limpiar()
        self._preparar_inicio()
        self._set(cargando=False)

    def _mensaje_clave(self):
        if self._comp and not componentes.hay(self._comp, "libaacs"):
            return ("Este disco está cifrado y falta libaacs, que no se incluye con Bolim por razones "
                    "legales. Instálalo (sudo apt install libaacs0) y vuelve a intentar.")
        if not self.keydb:
            return ("No se encontró el archivo de claves KEYDB.cfg, que no se incluye con Bolim por razones "
                    "legales. Colócalo en ~/.config/aacs/KEYDB.cfg y vuelve a intentar.")
        return ("Tu archivo KEYDB.cfg no tiene la clave de este disco, así que el video no se puede "
                "descifrar. Agrégala y vuelve a cargar el disco.")

    def error_lectura(self, e):
        """Llamado desde el lector del menú del disco (otro hilo)."""
        if e == nav2.EV_ENCRYPTED or self._e["sinClave"]:
            self._falta_clave = True
        elif e == -1:
            self._nav_fallo = True
        else:
            self._errores_lectura += 1
            if self._errores_lectura == 10:
                self._aviso("Hay partes del disco que no se pueden leer. ¿Está sucio o rayado?")

    def _archivo_reanudar(self):
        base = os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config")
        return os.path.join(base, "bolim", "reanudar.json")

    def _leer_reanudar(self):
        try:
            with open(self._archivo_reanudar(), encoding="utf-8") as f:
                return json.load(f)
        except (OSError, ValueError):
            return {}

    def _es_pelicula(self, playlist):
        """¿La playlist que reproduce el menú del disco es la película? (los menús suelen usar
        una copia equivalente de la playlist principal, con otro número)."""
        if playlist is None or self._pl is None or not self.aux:
            return False
        if playlist == self._pl:
            return True
        if playlist not in self._pelis:
            p = self.lib.bd_get_playlist_info(self.aux.bd, playlist, 0)
            dur = p.contents.duration / 90000 if p else 0
            if p:
                self.lib.bd_free_title_info(p)
            total = self._e["duracionPrincipal"]
            self._pelis[playlist] = bool(total) and abs(dur - total) < max(60, total * 0.03)
        return self._pelis[playlist]

    def nueva_playlist(self, playlist, seg, continua=False):
        super().nueva_playlist(playlist, seg, continua)
        self._set(enPeliculaDisco=self._es_pelicula(playlist))

    @Slot()
    def reanudarAqui(self):
        """Dentro del menú del disco: saltar a donde se quedó la película."""
        if self._reanudar and self._e.get("enPeliculaDisco"):
            self.mpv.command_async("seek", self._reanudar["pos"], "absolute")

    def _recordar_posicion(self):
        """Guarda dónde se quedó la película (y sus pistas) para poder reanudar."""
        if not self._e["hayDisco"] or self._pl is None:
            return
        modo = self._e["modo"]
        if modo == "pelicula":
            pos = self._e["posicion"]
        elif modo == "disco" and self.nav and self._es_pelicula(self.nav.playlist_actual):
            pos = self.lib.bd_tell_time(self.nav.bd) / 90000 - 2   # posición real en la película
        else:
            return
        dur = self._e["duracionPrincipal"]
        if pos < 30 or (dur and pos > dur - 120):   # recién empezada o ya terminada
            r = None
        else:
            aid = sid = None
            try:
                for t in self.mpv.track_list or []:
                    if t.get("selected") and t.get("type") == "audio":
                        aid = t.get("src-id")
                    elif t.get("selected") and t.get("type") == "sub":
                        sid = t.get("src-id")
            except Exception:
                pass
            r = {"pos": pos, "aid": aid, "sid": sid}
        self._reanudar = r
        datos = self._leer_reanudar()
        if r:
            datos[self._clave] = r
        else:
            datos.pop(self._clave, None)
        try:
            os.makedirs(os.path.dirname(self._archivo_reanudar()), exist_ok=True)
            with open(self._archivo_reanudar(), "w", encoding="utf-8") as f:
                json.dump(datos, f, ensure_ascii=False, indent=1)
        except OSError:
            pass
        self._set(reanudarPos=r["pos"] if r else 0.0)

    # Internos
    def _cerrar_nav(self):
        if self.nav:
            nav, self.nav = self.nav, None
            nav.cerrar()
            self.capas.limpiar()
        self._set(menuVisible=False, enPeliculaDisco=False)

    def _revisar(self):
        if self.nav and (self._falta_clave or self._nav_fallo):
            clave = self._falta_clave
            self._falta_clave = self._nav_fallo = False
            self._cerrar_nav()
            self.mpv.command_async("stop")
            if clave:
                self._set(sinClave=True, claveMensaje=self._mensaje_clave())
            self._set(modo="inicio")
            self._aviso("No hay clave para descifrar este disco. Revisa tu archivo KEYDB.cfg." if clave
                        else "No se pudo seguir leyendo el disco.")
            return
        if self.nav and self.nav.error_bdj:
            self._cerrar_nav()
            self.mpv.command_async("stop")
            self._set(modo="inicio")
            self._aviso("El menú del disco (Java) no se pudo ejecutar. Usa este menú para elegir.")

    def _terminar(self):
        if self._terminado:
            return
        self._terminado = True
        for ruta in self.temporales:
            try:
                os.unlink(ruta)
            except OSError:
                pass
        v = MpvVideo.instancia
        if not (v and v._lienzo and v._lienzo.ctx):
            try:
                self.mpv.terminate()        # apagado ordenado de mpv (el video ya se liberó)
            except Exception:
                pass
        # Salida directa: en Qt 6, quit() se cancela si la ventana rechaza cerrarse,
        # y la ventana rechaza el cierre para poder apagar mpv antes.
        sys.stdout.flush()
        os._exit(0)
