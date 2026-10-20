#!/bin/sh
# Construye bolim_<versión>_amd64.deb a partir de esta carpeta.
# Requiere: python3, pip y dpkg-deb. Descarga PySide6 (LGPLv3) para incluirlo.
set -e
FUENTE=$(cd "$(dirname "$0")" && pwd)
VERSION=$(sed -n 's/^__version__ = "\(.*\)"/\1/p' "$FUENTE/bolim/__init__.py")
PYSIDE=6.12.0
T=$(mktemp -d); R="$T/raiz"; LIB="$R/opt/bolim/lib"
mkdir -p "$LIB" "$R/usr/bin" "$R/usr/share/applications" "$R/usr/share/doc/bolim" "$R/DEBIAN"

python3 -m pip download "PySide6_Essentials==$PYSIDE" "shiboken6==$PYSIDE" --no-deps --only-binary=:all: -q -d "$T/w"
for w in "$T"/w/*.whl; do python3 -m zipfile -e "$w" "$LIB"; done
rm -rf "$LIB"/*.dist-info
P="$LIB/PySide6"
rm -rf "$P"/assistant "$P"/designer "$P"/doc "$P"/include "$P"/linguist "$P"/lrelease "$P"/lupdate \
       "$P"/qmlformat "$P"/qmllint "$P"/qmlls "$P"/svgtoqml "$P"/typesystems "$P"/scripts "$P"/glue \
       "$P"/*.pyi "$P"/Qt/translations "$P"/Qt/metatypes "$P"/Qt/libexec \
       "$P"/QtDesigner* "$P"/QtHelp* "$P"/QtTest* "$P"/QtUiTools* "$P"/QtQuickTest*
for l in Designer DesignerComponents Help QmlCompiler QuickTest Test UiTools QmlDesignSupport \
         QuickShapesDesignHelpers WaylandCompositor WaylandEglCompositorHwIntegration; do
    rm -f "$P/Qt/lib/libQt6$l.so.6"
done

cp -r "$FUENTE/bolim" "$R/opt/bolim/"
find "$R" -name __pycache__ -prune -exec rm -rf {} +
install -m 755 "$FUENTE/empaquetado/bolim" "$R/usr/bin/bolim"
install -m 644 "$FUENTE/empaquetado/bolim.desktop" "$R/usr/share/applications/"
install -m 644 "$FUENTE/README.md" "$R/usr/share/doc/bolim/"
install -m 644 "$FUENTE/LICENSE" "$R/usr/share/doc/bolim/copyright"
install -m 755 "$FUENTE/empaquetado/DEBIAN/postinst" "$FUENTE/empaquetado/DEBIAN/prerm" "$R/DEBIAN/"
sed "s/^Version: .*/Version: $VERSION/" "$FUENTE/empaquetado/DEBIAN/control" > "$R/DEBIAN/control"
echo "Installed-Size: $(du -sk --exclude=DEBIAN "$R" | cut -f1)" >> "$R/DEBIAN/control"

dpkg-deb --root-owner-group -Zxz --build "$R" "$FUENTE/bolim_${VERSION}_amd64.deb"
rm -rf "$T"
echo "Listo: $FUENTE/bolim_${VERSION}_amd64.deb"
