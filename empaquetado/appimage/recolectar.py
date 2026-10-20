import os, re, shutil, subprocess, sys
APP = os.path.abspath(sys.argv[1])
MULTI = sys.argv[2]                       # p. ej. x86_64-linux-gnu o aarch64-linux-gnu
EXCLUDELIST = sys.argv[3]
LIB = os.path.join(APP, "usr/lib")
os.makedirs(LIB, exist_ok=True)
excl = {l.split("#")[0].strip() for l in open(EXCLUDELIST) if l.split("#")[0].strip()}
raices = [f"/usr/lib/{MULTI}/libmpv.so.2", f"/usr/lib/{MULTI}/libbluray.so.2",
          f"/usr/lib/{MULTI}/libxcb-cursor.so.0", f"/usr/lib/{MULTI}/libxcb-icccm.so.4",
          f"/usr/lib/{MULTI}/libxcb-keysyms.so.1", f"/usr/lib/{MULTI}/libxcb-render-util.so.0",
          f"/usr/lib/{MULTI}/libxcb-image.so.0", f"/usr/lib/{MULTI}/libxcb-shape.so.0",
          f"/usr/lib/{MULTI}/libxkbcommon-x11.so.0", f"/usr/lib/{MULTI}/libxcb-xkb.so.1",
          f"/usr/lib/{MULTI}/libxkbcommon.so.0"]
for r in raices:
    if os.path.basename(r) in ("libxcb-shape.so.0", "libxcb-xkb.so.1"):
        continue
    shutil.copy2(r, os.path.join(LIB, os.path.basename(r)))
import fnmatch
# Bibliotecas que el sistema siempre trae y que comparten los controladores gráficos (Mesa):
# empaquetar versiones viejas puede romper OpenGL en sistemas más nuevos.
EXTRA = ["libX*.so*", "libxcb*.so*", "libwayland-*.so*", "libzstd.so*", "libelf.so*", "libLLVM*",
         "libsensors.so*", "libgcrypt.so*", "libudev.so*", "libsystemd.so*", "libdbus-1.so*",
         "libxshmfence.so*", "libvulkan.so*"]
QT_XCB = {"libxcb-cursor.so.0", "libxcb-icccm.so.4", "libxcb-keysyms.so.1", "libxcb-render-util.so.0",
          "libxcb-image.so.0", "libxcb-util.so.1", "libxkbcommon-x11.so.0"}
def excluir_extra(nombre):
    return nombre not in QT_XCB and any(fnmatch.fnmatch(nombre, p) for p in EXTRA)
faltan = set()
while True:
    nuevos = 0
    objetos = []
    for d, _, fs in os.walk(APP):
        for f in fs:
            if ".so" in f and not os.path.islink(os.path.join(d, f)):
                objetos.append(os.path.join(d, f))
    env = dict(os.environ, LD_LIBRARY_PATH=LIB)
    for o in objetos:
        try:
            out = subprocess.run(["ldd", o], capture_output=True, text=True, env=env, timeout=20).stdout
        except Exception:
            continue
        for linea in out.splitlines():
            m = re.match(r"\s*(\S+) => (\S+)", linea)
            if not m:
                continue
            nombre, ruta = m.groups()
            if nombre in excl or ruta.startswith(APP) or excluir_extra(nombre):
                continue
            if ruta == "not":
                faltan.add((nombre, os.path.relpath(o, APP)))
                continue
            destino = os.path.join(LIB, nombre)
            if not os.path.exists(destino):
                shutil.copy2(os.path.realpath(ruta), destino)
                nuevos += 1
    if not nuevos:
        break
print("bibliotecas en usr/lib:", len(os.listdir(LIB)))
print("no encontradas:", sorted({f for f, _ in faltan})[:30])
