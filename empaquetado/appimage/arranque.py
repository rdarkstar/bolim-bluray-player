"""Arranque de Bolim dentro de la AppImage."""
import ctypes.util
import glob
import os
import sys

APP = os.environ.get("BOLIM_APPDIR", os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
LIB = os.path.join(APP, "usr", "lib")
_buscar = ctypes.util.find_library


def find_library(nombre):
    """Primero las bibliotecas incluidas (mpv, libbluray); libaacs y demás, del sistema."""
    propias = sorted(glob.glob(os.path.join(LIB, f"lib{nombre}.so*")))
    return propias[0] if propias else _buscar(nombre)


ctypes.util.find_library = find_library
# Los programas externos (eject, lsblk) deben usar las bibliotecas del sistema, no las incluidas.
os.environ.pop("LD_LIBRARY_PATH", None)
sys.path.insert(0, os.path.join(APP, "usr", "share", "bolim"))

from bolim.__main__ import main  # noqa: E402

main()
