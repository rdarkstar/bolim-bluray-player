#!/bin/sh
# Construye Bolim_Bluray_Player-<versión>-<arquitectura>.AppImage en esta máquina.
# Funciona en Debian/Ubuntu x86_64 o aarch64 (por ejemplo, Raspberry Pi OS de 64 bits).
# La AppImage resultante funciona en sistemas con una versión de glibc igual o más nueva
# que la de la máquina donde se construye.
#
# Requiere: curl, python3 (con pip), y los paquetes:
#   sudo apt install libmpv2 libbluray2 libbluray-bdj libxcb-cursor0 libxcb-icccm4 \
#        libxcb-keysyms1 libxcb-render-util0 libxcb-image0 libxkbcommon-x11-0 binutils
set -e
FUENTE=$(cd "$(dirname "$0")" && pwd)
E="$FUENTE/empaquetado/appimage"
VERSION=$(sed -n 's/^__version__ = "\(.*\)"/\1/p' "$FUENTE/bolim/__init__.py")
ARCH=$(uname -m)                                     # x86_64 o aarch64
MULTI=$(gcc -dumpmachine 2>/dev/null || echo "$ARCH-linux-gnu")
case "$MULTI" in *-pc-*|*-unknown-*) MULTI="$ARCH-linux-gnu";; esac
PYSIDE=6.12.0
PYVER=3.12
T=$(mktemp -d); A="$T/AppDir"; mkdir -p "$A/usr"
echo "Construyendo Bolim $VERSION para $ARCH en $T"

# 1) Python portátil
URL=$(curl -s https://api.github.com/repos/astral-sh/python-build-standalone/releases/latest | python3 -c "
import json,sys
for a in json.load(sys.stdin)['assets']:
    n=a['name']
    if n.startswith('cpython-$PYVER.') and n.endswith('$ARCH-unknown-linux-gnu-install_only.tar.gz'):
        print(a['browser_download_url']); break" 2>/dev/null || true)
# Si la API de GitHub no responde (límite de consultas), usar una versión conocida
[ -n "$URL" ] || URL="https://github.com/astral-sh/python-build-standalone/releases/download/20261013/cpython-3.12.15%2B20261013-$ARCH-unknown-linux-gnu-install_only.tar.gz"
curl -sfL "$URL" | tar xz -C "$A/usr"
mv "$A/usr/python" "$A/usr/python3"
PY="$A/usr/python3/bin/python3"
"$PY" -m pip install -q --no-cache-dir --no-warn-script-location \
      "PySide6_Essentials==$PYSIDE" "shiboken6==$PYSIDE" numpy python-mpv

# 2) Recortar lo que no se usa
SP="$A/usr/python3/lib/python$PYVER/site-packages"; P="$SP/PySide6"; Q="$P/Qt"
rm -rf "$P"/assistant "$P"/designer "$P"/doc "$P"/include "$P"/linguist "$P"/lrelease "$P"/lupdate \
       "$P"/qmlformat "$P"/qmllint "$P"/qmlls "$P"/svgtoqml "$P"/typesystems "$P"/scripts "$P"/glue \
       "$P"/*.pyi "$Q"/translations "$Q"/metatypes "$Q"/libexec \
       "$P"/QtDesigner* "$P"/QtHelp* "$P"/QtTest* "$P"/QtUiTools* "$P"/QtQuickTest* \
       "$Q"/plugins/designer "$Q"/plugins/qmltooling "$Q"/plugins/sqldrivers "$Q"/plugins/printsupport \
       "$Q"/plugins/wayland-graphics-integration-server "$Q"/plugins/platformthemes/libqgtk3.so "$Q"/qml/QtTest
for l in Designer DesignerComponents Help QmlCompiler QuickTest Test UiTools QmlDesignSupport \
         QuickShapesDesignHelpers WaylandCompositor WaylandEglCompositorHwIntegration; do
    rm -f "$Q/lib/libQt6$l.so.6"
done
L="$A/usr/python3/lib"
rm -rf "$L/python$PYVER/test" "$L/python$PYVER/idlelib" "$L/python$PYVER/tkinter" "$L/python$PYVER/turtledemo" \
       "$L/python$PYVER/ensurepip" "$L"/tcl* "$L"/tk* "$L"/itcl* "$L"/thread* "$L"/libtcl* "$L"/libtk* \
       "$A/usr/python3/include" "$A/usr/python3/share" "$SP"/pip* "$SP/numpy/tests" "$SP"/numpy/*/tests \
       "$A"/usr/python3/bin/idle* "$A"/usr/python3/bin/pip* "$A"/usr/python3/bin/pydoc* "$A"/usr/python3/bin/2to3* \
       "$L/python$PYVER"/lib-dynload/_tkinter*
strip --strip-unneeded "$L"/libpython*.so.* 2>/dev/null || true
find "$L" -name "*.so*" -type f -exec strip --strip-unneeded {} + 2>/dev/null || true

# 3) Bolim, menús Java y bibliotecas del sistema (mpv, libbluray y dependencias)
mkdir -p "$A/usr/share/bolim" "$A/usr/share/java"
cp -r "$FUENTE/bolim" "$A/usr/share/bolim/"
cp "$E/arranque.py" "$A/usr/share/bolim/"
cp /usr/share/java/libbluray-j2se*.jar "$A/usr/share/java/" 2>/dev/null || echo "Aviso: sin libbluray-bdj, no habrá menús Java"
cp "$E/AppRun" "$E/bolim.desktop" "$E/bolim.svg" "$A/"
chmod +x "$A/AppRun"; ln -sf bolim.svg "$A/.DirIcon"
curl -sL -o "$T/excludelist" https://raw.githubusercontent.com/AppImageCommunity/pkg2appimage/master/excludelist
python3 "$E/recolectar.py" "$A" "$MULTI" "$T/excludelist"
find "$A" -name __pycache__ -prune -exec rm -rf {} +

# 4) Empaquetar
curl -sL -o "$T/appimagetool" "https://github.com/AppImage/appimagetool/releases/download/continuous/appimagetool-$ARCH.AppImage"
chmod +x "$T/appimagetool"
(cd "$T" && ./appimagetool --appimage-extract >/dev/null)
SALIDA="$FUENTE/Bolim_Bluray_Player-$VERSION-$ARCH.AppImage"
ARCH=$ARCH "$T/squashfs-root/AppRun" --comp zstd -n "$A" "$SALIDA"
rm -rf "$T"
echo "Listo: $SALIDA"
