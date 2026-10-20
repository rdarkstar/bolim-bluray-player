# Bolim Bluray Player

Reproductor de discos Blu-ray con sus menús (HDMV y Java), menú propio de respaldo,
reanudar, otros títulos, nombres de pistas y avisos claros cuando falta algo.

## Abrirlo
Desde el menú de aplicaciones (Multimedia → Bolim Bluray Player) o con `bolim`.
La unidad se detecta sola; para otra: `bolim /dev/sr1` (o una carpeta con BDMV).

## Lo que NO incluye (por razones legales)
- **libaacs**: descifrado de discos comerciales → `sudo apt install libaacs0`
- **libbdplus**: solo para discos con BD+ → `sudo apt install libbdplus0`
- **KEYDB.cfg**: claves de los discos → colócalo en `~/.config/aacs/KEYDB.cfg`

Para menús Java (BD-J): `sudo apt install libbluray-bdj default-jre`.
La opción **Componentes** de la pantalla de inicio muestra qué está instalado y qué falta.

## Teclado
Espacio pausa · ←/→ 5 s · ↑/↓ 1 min · Re Pág/Av Pág capítulos · A/S audio/subtítulos ·
M silencio · [ ] velocidad · Retroceso velocidad 1× · F pantalla completa ·
F2 menú del disco · F3 menú emergente · R reanudar (en el menú del disco) · Q salir

## Archivos
- Registro: `~/.local/state/bolim/bolim.log` (el anterior: `bolim.log.anterior`)
- Posiciones para reanudar: `~/.config/bolim/reanudar.json`
- Mensajes en la terminal en lugar del registro: `bolim --consola`

## Licencias
Incluye PySide6 / Qt 6 (LGPLv3), en `/opt/bolim/lib`.
Usa del sistema: libbluray (LGPL), mpv/libmpv y python-mpv.

## Construir el paquete
`./construir.sh` genera `bolim_<versión>_amd64.deb` (la versión se toma de `bolim/__init__.py`).
Para probar sin instalar: `PYTHONPATH=. python3 -m bolim --consola` (requiere PySide6 disponible).

## AppImage (cualquier distribución, sin instalar)
`./construir-appimage.sh` genera `Bolim_Bluray_Player-<versión>-<arquitectura>.AppImage`.
Funciona en sistemas con glibc igual o más nueva que la del equipo donde se construye
(construida en Ubuntu 24.04: Ubuntu 24.04+, Debian 13/testing y similares).
En una Raspberry Pi (64 bits) se construye en la propia Pi con el mismo script.
Incluye mpv, libbluray y el soporte de menús Java; usa del sistema OpenGL, libaacs,
libbdplus, Java y KEYDB.cfg.
