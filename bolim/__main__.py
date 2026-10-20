"""
Bolim Bluray Player — punto de entrada.

  bolim                 detecta la unidad y abre el reproductor
  bolim /dev/sr1        usa una unidad concreta (o una carpeta con BDMV)
  bolim --consola       mensajes en la terminal en lugar del registro
"""
import argparse
import glob
import locale
import os
import sys

NOMBRE = "Bolim Bluray Player"
DIR = os.path.dirname(os.path.abspath(__file__))

VENTANA_ERROR = b'''
import QtQuick
import QtQuick.Controls.Basic
ApplicationWindow {
    visible: true; width: 660; height: 420; color: "#15161a"; title: "Bolim Bluray Player"
    Column {
        anchors.centerIn: parent; width: parent.width - 80; spacing: 14
        Text { text: "Faltan componentes necesarios"; color: "#e8a33d"; font.pixelSize: 22; font.bold: true }
        Repeater {
            model: faltantes
            Text { width: parent.width; wrapMode: Text.WordWrap; color: "#f2f2f2"; font.pixelSize: 14
                   text: "\\u2022 " + modelData.nombre + ": " + modelData.detalle }
        }
        Text { text: "Inst\\u00e1lalos y vuelve a abrir Bolim."; color: "#9aa0a6"; font.pixelSize: 13 }
        Button { text: "Cerrar"; onClicked: Qt.quit() }
    }
}
'''


def detectar_unidad():
    if sys.platform == "win32":
        import ctypes
        for letra in "DEFGHIJKLMNOPQRSTUVWXYZ":
            if ctypes.windll.kernel32.GetDriveTypeW(f"{letra}:\\") == 5:   # unidad óptica
                return f"{letra}:"
        return "D:"
    unidades = sorted(glob.glob("/dev/sr[0-9]*"))
    return unidades[0] if unidades else "/dev/sr0"


def preparar_registro(consola):
    """Envía los mensajes (incluidos los de libbluray, mpv y Java) a un archivo de registro."""
    base = os.environ.get("XDG_STATE_HOME") or os.path.expanduser("~/.local/state")
    carpeta = os.path.join(base, "bolim")
    os.makedirs(carpeta, exist_ok=True)
    ruta = os.path.join(carpeta, "bolim.log")
    if consola:
        return "terminal"
    if os.path.exists(ruta):
        os.replace(ruta, ruta + ".anterior")
    f = open(ruta, "a", buffering=1, encoding="utf-8", errors="replace")
    os.dup2(f.fileno(), 1)
    os.dup2(f.fileno(), 2)
    sys.stdout = sys.stderr = f
    return ruta


def main():
    ap = argparse.ArgumentParser(prog="bolim", description=NOMBRE)
    ap.add_argument("dispositivo", nargs="?",
                    help="Unidad (D:), dispositivo (/dev/sr0) o carpeta del disco. Si se omite, se detecta.")
    ap.add_argument("--idioma", default="spa", help="Idioma preferido: spa, eng, fra…")
    ap.add_argument("--consola", action="store_true", help="Mostrar los mensajes en la terminal")
    args = ap.parse_args()
    args.dispositivo = args.dispositivo or detectar_unidad()
    registro = preparar_registro(args.consola)
    print(f"{NOMBRE} — unidad: {args.dispositivo}")

    os.environ.setdefault("QSG_RENDER_LOOP", "basic")
    from PySide6.QtGui import QGuiApplication, QIcon
    from PySide6.QtQml import QQmlApplicationEngine, qmlRegisterType
    from PySide6.QtQuick import QQuickWindow, QSGRendererInterface

    from . import componentes

    QQuickWindow.setGraphicsApi(QSGRendererInterface.GraphicsApi.OpenGL)
    app = QGuiApplication(sys.argv)
    app.setApplicationName(NOMBRE)
    app.setDesktopFileName("bolim")
    app.setWindowIcon(QIcon.fromTheme("org.xfce.parole", QIcon.fromTheme("media-optical")))
    locale.setlocale(locale.LC_NUMERIC, "C")   # requisito de mpv

    lista = componentes.revisar()
    for c in lista:
        print(f"[{c['estado']}] {c['nombre']}: {c['detalle']}")
    engine = QQmlApplicationEngine()
    faltan = componentes.requeridos_faltantes(lista)
    if faltan:
        engine.rootContext().setContextProperty("faltantes", faltan)
        engine.loadData(VENTANA_ERROR)
        sys.exit(app.exec())

    from .app import Control, MpvVideo
    ctl = Control(args, lista, registro)
    qmlRegisterType(MpvVideo, "Bolim", 1, 0, "MpvVideo")
    engine.rootContext().setContextProperty("ctl", ctl)
    engine.load(os.path.join(DIR, "interfaz.qml"))
    if not engine.rootObjects():
        print("No se pudo cargar la interfaz.")
        ctl._terminar()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
