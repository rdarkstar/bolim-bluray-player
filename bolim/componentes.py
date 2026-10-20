"""
Bolim Bluray Player — revisión de componentes externos.

Bolim no incluye libaacs, libbdplus ni claves de discos por razones legales:
el programa solo detecta si están instalados y explica qué falta.
"""
import ctypes
import ctypes.util
import glob
import os
import shutil
import sys

OK, AVISO, ERROR = "ok", "aviso", "error"
LEGAL = "No se incluye con Bolim por razones legales."


def _hay_lib(nombres, buscar):
    for n in nombres:
        try:
            ctypes.CDLL(n)
            return True
        except OSError:
            pass
    encontrada = ctypes.util.find_library(buscar)
    if encontrada:
        try:
            ctypes.CDLL(encontrada)
            return True
        except OSError:
            pass
    return False


def _instalar(paquetes):
    return f"Instálalo con: sudo apt install {paquetes}" if sys.platform.startswith("linux") else ""


def revisar():
    """Lista de componentes: {clave, nombre, estado, detalle}."""
    from . import disco
    res = []

    def agregar(clave, nombre, estado, detalle):
        res.append({"clave": clave, "nombre": nombre, "estado": estado, "detalle": detalle})

    # Requeridos
    win = sys.platform == "win32"
    ok = _hay_lib(["libbluray.dll"] if win else ["libbluray.so.2"], "bluray")
    agregar("libbluray", "Lectura de Blu-ray (libbluray)", OK if ok else ERROR,
            "Instalado." if ok else "Necesario para leer discos. " + _instalar("libbluray2"))

    try:
        import mpv  # noqa: F401
        agregar("mpv", "Reproducción de video (mpv)", OK, "Instalado.")
    except ImportError:
        agregar("mpv", "Reproducción de video (mpv)", ERROR,
                "Falta el módulo de Python para mpv. " + _instalar("python3-mpv"))
    except OSError:
        agregar("mpv", "Reproducción de video (mpv)", ERROR,
                "Falta la biblioteca libmpv. " + _instalar("libmpv2"))

    try:
        import numpy  # noqa: F401
        agregar("numpy", "Gráficos de menús (numpy)", OK, "Instalado.")
    except ImportError:
        agregar("numpy", "Gráficos de menús (numpy)", ERROR, "Necesario. " + _instalar("python3-numpy"))

    # Opcionales (no incluidos por razones legales)
    ok = _hay_lib(["libaacs.dll"] if win else ["libaacs.so.0"], "aacs")
    agregar("libaacs", "Descifrado AACS (libaacs)", OK if ok else AVISO,
            "Instalado." if ok else
            f"Necesario para discos comerciales. {LEGAL} Sin él solo se reproducen discos sin cifrar. "
            + _instalar("libaacs0"))

    keydb, _ = disco.buscar_keydb()
    agregar("keydb", "Claves de discos (KEYDB.cfg)", OK if keydb else AVISO,
            keydb if keydb else
            f"No se encontró. {LEGAL} Colócalo en ~/.config/aacs/KEYDB.cfg para reproducir discos cifrados.")

    ok = _hay_lib(["libbdplus.dll"] if win else ["libbdplus.so.0"], "bdplus")
    agregar("libbdplus", "Protección BD+ (libbdplus)", OK if ok else AVISO,
            "Instalado." if ok else
            f"Solo algunos discos lo requieren. {LEGAL} " + _instalar("libbdplus0"))

    jar = os.environ.get("LIBBLURAY_CP") or next(iter(glob.glob("/usr/share/java/libbluray-j2se*.jar")), None)
    java = (os.environ.get("JAVA_HOME") or shutil.which("java")
            or os.path.isdir("/usr/lib/jvm/default-java"))
    if jar and java:
        agregar("bdj", "Menús Java (BD-J)", OK, "Instalado.")
    else:
        falta = " y ".join(x for x, hay in (("libbluray-bdj", jar), ("Java", java)) if not hay)
        agregar("bdj", "Menús Java (BD-J)", AVISO,
                f"Falta {falta}. Sin esto, los discos con menú Java usan el menú de Bolim. "
                + _instalar("libbluray-bdj default-jre"))

    if not win:
        ok = bool(shutil.which("eject"))
        agregar("eject", "Expulsar disco", OK if ok else AVISO,
                "Instalado." if ok else "Sin esto el botón Expulsar no abre la bandeja. " + _instalar("eject"))
    return res


def requeridos_faltantes(lista):
    return [c for c in lista if c["estado"] == ERROR]


def hay(lista, clave):
    return any(c["clave"] == clave and c["estado"] == OK for c in lista)
