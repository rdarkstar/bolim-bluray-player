import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import QtQuick.Window
import Bolim 1.0

ApplicationWindow {
    id: win
    width: Math.min(1280, Screen.desktopAvailableWidth * 0.9)
    height: Math.min(760, Screen.desktopAvailableHeight * 0.85)
    minimumWidth: 720
    minimumHeight: 440
    visible: true
    color: "black"
    title: e.hayDisco && e.titulo ? e.titulo + "  ·  Bolim" : "Bolim Bluray Player"

    readonly property var e: ctl.e
    readonly property color acento: "#e8a33d"
    readonly property color texto: "#f2f2f2"
    readonly property color tenue: "#9aa0a6"
    readonly property bool enInicio: e.modo === "inicio"
    property bool controlesVisibles: true
    readonly property bool ocupado: sobreBarra.hovered || sobreArriba.hovered || popAudio.visible || popSubs.visible
    property int avisoN: e.avisoN

    function hms(s) {
        s = Math.max(0, Math.floor(s || 0))
        var h = Math.floor(s / 3600), m = Math.floor(s % 3600 / 60), x = s % 60
        return h + ":" + (m < 10 ? "0" : "") + m + ":" + (x < 10 ? "0" : "") + x
    }
    function mostrar() { controlesVisibles = true; ocultar.restart() }
    function alternarPantalla() {
        win.visibility = (win.visibility === Window.FullScreen) ? Window.Windowed : Window.FullScreen
    }
    function nombreTecla(k) {
        switch (k) {
        case Qt.Key_Up: return "UP"
        case Qt.Key_Down: return "DOWN"
        case Qt.Key_Left: return "LEFT"
        case Qt.Key_Right: return "RIGHT"
        case Qt.Key_Return: case Qt.Key_Enter: return "ENTER"
        case Qt.Key_Space: return "SPACE"
        case Qt.Key_F2: return "F2"
        case Qt.Key_F3: return "F3"
        case Qt.Key_M: return "M"
        case Qt.Key_Backspace: return "BACKSPACE"
        case Qt.Key_BracketLeft: return "["
        case Qt.Key_BracketRight: return "]"
        case Qt.Key_PageUp: return "PGUP"
        case Qt.Key_PageDown: return "PGDOWN"
        case Qt.Key_R: return "R"
        case Qt.Key_A: return "A"
        case Qt.Key_S: return "S"
        }
        return ""
    }

    onClosing: function(close) { close.accepted = false; ctl.salir() }
    function enfocarInicio() {
        if (!e.hayDisco) opCargar.forceActiveFocus()
        else if (e.sinClave) opReintentar.forceActiveFocus()
        else if (e.reanudarPos > 0) opReanudar.forceActiveFocus()
        else opcion1.forceActiveFocus()
    }
    onEnInicioChanged: enInicio ? enfocarInicio() : teclas.forceActiveFocus()
    property bool hayDisco: e.hayDisco
    onHayDiscoChanged: if (enInicio) enfocarInicio()
    property bool sinClave: e.sinClave
    onSinClaveChanged: if (enInicio) enfocarInicio()
    onAvisoNChanged: animAviso.restart()
    Component.onCompleted: enfocarInicio()

    Shortcut { sequences: ["F", "F11"]; onActivated: alternarPantalla() }
    Shortcut { sequence: "Q"; onActivated: ctl.salir() }
    Shortcut { sequence: "Esc"; onActivated: if (win.visibility === Window.FullScreen) win.visibility = Window.Windowed }

    Timer {
        id: ocultar
        interval: 3000
        onTriggered: if (!e.pausado && !ocupado && !enInicio) controlesVisibles = false
    }

    // ---------- Componentes ----------
    component Icono: Canvas {
        property string tipo
        property color tinta: "#f2f2f2"
        onTipoChanged: requestPaint()
        onTintaChanged: requestPaint()
        onPaint: {
            var c = getContext("2d"), w = width, h = height
            c.reset()
            c.fillStyle = tinta; c.strokeStyle = tinta
            c.lineWidth = Math.max(1.5, w * 0.09); c.lineCap = "round"; c.lineJoin = "round"
            function poli(p) { c.beginPath(); c.moveTo(p[0] * w, p[1] * h)
                for (var i = 2; i < p.length; i += 2) c.lineTo(p[i] * w, p[i + 1] * h)
                c.closePath(); c.fill() }
            function rect(x, y, a, b) { c.fillRect(x * w, y * h, a * w, b * h) }
            function linea(x0, y0, x1, y1) { c.beginPath(); c.moveTo(x0 * w, y0 * h); c.lineTo(x1 * w, y1 * h); c.stroke() }
            function bocina() { rect(.14, .38, .14, .24); poli([.28, .38, .48, .2, .48, .8, .28, .62]) }
            switch (tipo) {
            case "play": poli([.3, .18, .3, .82, .84, .5]); break
            case "pausa": rect(.26, .2, .16, .6); rect(.58, .2, .16, .6); break
            case "stop": rect(.27, .27, .46, .46); break
            case "expulsar": poli([.5, .2, .82, .56, .18, .56]); rect(.18, .66, .64, .12); break
            case "atras": poli([.5, .26, .5, .74, .16, .5]); poli([.84, .26, .84, .74, .5, .5]); break
            case "adelante": poli([.16, .26, .16, .74, .5, .5]); poli([.5, .26, .5, .74, .84, .5]); break
            case "anterior": rect(.2, .26, .1, .48); poli([.78, .26, .78, .74, .32, .5]); break
            case "siguiente": rect(.7, .26, .1, .48); poli([.22, .26, .22, .74, .68, .5]); break
            case "menu": linea(.24, .32, .76, .32); linea(.24, .5, .76, .5); linea(.24, .68, .76, .68); break
            case "volver": linea(.72, .5, .28, .5); linea(.46, .3, .28, .5); linea(.46, .7, .28, .5); break
            case "audio": bocina(); c.beginPath(); c.arc(.5 * w, .5 * h, .2 * w, -0.9, 0.9); c.stroke()
                c.beginPath(); c.arc(.5 * w, .5 * h, .34 * w, -0.9, 0.9); c.stroke(); break
            case "silencio": bocina(); linea(.62, .38, .84, .62); linea(.84, .38, .62, .62); break
            case "subs": c.strokeRect(.14 * w, .24 * h, .72 * w, .52 * h)
                linea(.28, .44, .5, .44); linea(.6, .44, .72, .44); linea(.28, .58, .72, .58); break
            case "pantalla": linea(.2, .38, .2, .2); linea(.2, .2, .38, .2); linea(.62, .2, .8, .2); linea(.8, .2, .8, .38)
                linea(.8, .62, .8, .8); linea(.8, .8, .62, .8); linea(.38, .8, .2, .8); linea(.2, .8, .2, .62); break
            }
        }
    }

    component Boton: Rectangle {
        id: b
        property string icono
        property real tam: 40
        property bool principal: false
        signal pulsado
        signal presionado
        signal soltado
        width: tam; height: tam; radius: tam / 2
        color: principal ? "#e8a33d" : (area.containsMouse ? "#2effffff" : "transparent")
        scale: area.pressed ? 0.92 : 1
        Behavior on color { ColorAnimation { duration: 120 } }
        Behavior on scale { NumberAnimation { duration: 80 } }
        Icono { anchors.centerIn: parent; width: b.tam * 0.56; height: width; tipo: b.icono; tinta: b.principal ? "#141414" : "#f2f2f2" }
        MouseArea {
            id: area
            anchors.fill: parent
            hoverEnabled: true
            onClicked: b.pulsado()
            onPressed: b.presionado()
            onReleased: b.soltado()
            onCanceled: b.soltado()
        }
    }

    component OpcionInicio: Rectangle {
        id: o
        property string etiqueta
        property string detalle
        property bool principal: false
        signal elegida
        activeFocusOnTab: true
        implicitWidth: 400; implicitHeight: win.height < 760 ? 44 : 52; radius: implicitHeight / 2
        color: principal ? (zonaO.containsMouse || activeFocus ? Qt.lighter("#e8a33d", 1.12) : "#e8a33d")
                         : (zonaO.containsMouse || activeFocus ? "#26ffffff" : "transparent")
        border.width: activeFocus && !principal ? 2 : 0
        border.color: "#e8a33d"
        Behavior on color { ColorAnimation { duration: 120 } }
        Text {
            x: 26; anchors.verticalCenter: parent.verticalCenter
            text: o.etiqueta; color: o.principal ? "#141414" : "#f2f2f2"
            font.pixelSize: 19; font.weight: Font.Medium
        }
        Text {
            anchors.right: parent.right; anchors.rightMargin: 24; anchors.verticalCenter: parent.verticalCenter
            width: 190; horizontalAlignment: Text.AlignRight; elide: Text.ElideRight
            text: o.detalle; color: o.principal ? "#3a3a3a" : "#9aa0a6"; font.pixelSize: 14
        }
        MouseArea { id: zonaO; anchors.fill: parent; hoverEnabled: true; onClicked: o.elegida() }
        Keys.onReturnPressed: o.elegida()
        Keys.onEnterPressed: o.elegida()
        Keys.onDownPressed: nextItemInFocusChain(true).forceActiveFocus()
        Keys.onUpPressed: nextItemInFocusChain(false).forceActiveFocus()
    }

    component ListaPistas: Popup {
        id: lp
        property var modelo: []
        property string prop
        width: 340
        padding: 8
        background: Rectangle { color: "#f0151619"; radius: 12; border.color: "#22ffffff" }
        contentItem: ListView {
            implicitHeight: Math.min(contentHeight, 340)
            model: lp.modelo
            clip: true
            delegate: Rectangle {
                width: ListView.view.width; height: 42; radius: 8
                color: zonaP.containsMouse ? "#22ffffff" : "transparent"
                Rectangle { x: 10; anchors.verticalCenter: parent.verticalCenter; width: 6; height: 6; radius: 3
                            color: "#e8a33d"; visible: modelData.sel }
                Text { x: 26; anchors.verticalCenter: parent.verticalCenter; width: parent.width - 36; elide: Text.ElideRight
                       text: modelData.nombre; color: modelData.sel ? "#e8a33d" : "#f2f2f2"; font.pixelSize: 15 }
                MouseArea { id: zonaP; anchors.fill: parent; hoverEnabled: true
                            onClicked: { ctl.pista(lp.prop, modelData.id); lp.close() } }
            }
        }
    }

    // ---------- Video ----------
    MpvVideo { anchors.fill: parent }

    MouseArea {
        anchors.fill: parent
        hoverEnabled: true
        cursorShape: (controlesVisibles || enInicio || e.menuVisible) ? Qt.ArrowCursor : Qt.BlankCursor
        onPositionChanged: function(m) {
            mostrar()
            if (e.menuVisible) ctl.ratonMenu(m.x / width, m.y / height, false)
        }
        onClicked: function(m) { if (e.menuVisible) ctl.ratonMenu(m.x / width, m.y / height, true) }
        onDoubleClicked: if (!e.menuVisible) alternarPantalla()
    }

    Text {
        anchors.centerIn: parent
        visible: e.modo === "disco" && e.inactivo && !e.menuVisible
        text: "Cargando el menú del disco…"
        color: tenue; font.pixelSize: 18
    }

    Item {
        id: teclas
        anchors.fill: parent
        Keys.onPressed: function(k) {
            var n = nombreTecla(k.key)
            if (n !== "") { ctl.tecla(n); mostrar(); k.accepted = true }
        }
    }

    // ---------- Pantalla de inicio (también menú de respaldo) ----------
    Rectangle {
        id: inicio
        anchors.fill: parent
        visible: enInicio
        gradient: Gradient {
            GradientStop { position: 0.0; color: "#1c1e25" }
            GradientStop { position: 1.0; color: "#08090b" }
        }
        Rectangle {
            width: parent.width; height: width; radius: width / 2
            x: parent.width * 0.42; y: -parent.height * 0.75
            color: acento; opacity: 0.07
        }

        ColumnLayout {
            anchors.left: parent.left; anchors.leftMargin: Math.max(48, parent.width * 0.07)
            anchors.verticalCenter: parent.verticalCenter
            anchors.verticalCenterOffset: -14
            spacing: win.height < 760 ? 4 : 10
            Text { text: "BOLIM  ·  BLU-RAY"; color: acento; font.pixelSize: 13; font.letterSpacing: 5; font.bold: true }
            Text {
                text: e.hayDisco ? e.titulo : "Sin disco"
                color: texto; font.pixelSize: Math.min(64, win.width / 16); font.weight: Font.Light
                Layout.maximumWidth: win.width * 0.55; elide: Text.ElideRight
            }
            Text {
                text: !e.hayDisco ? (e.cargando ? "Leyendo el disco…" : "Inserta un Blu-ray y elige Cargar disco") :
                      (e.duracionPrincipal > 0 ? hms(e.duracionPrincipal) : "") +
                      (e.inicioCapitulos.length ? "   ·   " + e.inicioCapitulos.length + (e.inicioCapitulos.length === 1 ? " capítulo" : " capítulos") : "")
                color: tenue; font.pixelSize: 15
            }
            Rectangle {
                visible: e.hayDisco && e.sinClave
                Layout.topMargin: 8
                Layout.preferredWidth: 400
                Layout.preferredHeight: columnaClave.implicitHeight + 24
                radius: 12; color: "#26e8a33d"; border.color: acento
                Column {
                    id: columnaClave
                    x: 16; y: 12; width: parent.width - 32; spacing: 4
                    Text { text: "Sin clave para este disco"; color: acento; font.pixelSize: 15; font.bold: true }
                    Text { width: parent.width; wrapMode: Text.WordWrap; color: texto; font.pixelSize: 13
                           text: e.claveMensaje }
                }
            }
            Item { Layout.preferredHeight: win.height < 760 ? 10 : 22 }
            OpcionInicio { id: opCargar; visible: !e.hayDisco; principal: true
                           etiqueta: e.cargando ? "Cargando…" : "Cargar disco"; onElegida: ctl.cargarDisco() }
            OpcionInicio { id: opReintentar; visible: e.hayDisco && e.sinClave; principal: true
                           etiqueta: e.cargando ? "Cargando…" : "Volver a intentar"; detalle: "tras agregar la clave"
                           onElegida: ctl.reintentar() }
            OpcionInicio { id: opReanudar; visible: e.hayDisco && !e.sinClave && e.reanudarPos > 0; principal: true
                           etiqueta: "Reanudar"; detalle: "desde " + hms(e.reanudarPos); onElegida: ctl.reanudar() }
            OpcionInicio { id: opcion1; visible: e.hayDisco && !e.sinClave; principal: !(e.reanudarPos > 0)
                           etiqueta: e.reanudarPos > 0 ? "Desde el inicio" : "Reproducir película"
                           onElegida: ctl.reproducirPelicula(-1) }
            OpcionInicio { visible: e.hayDisco && !e.sinClave; etiqueta: "Menú del disco"; onElegida: ctl.menuDisco() }
            OpcionInicio { visible: e.hayDisco && !e.sinClave; etiqueta: "Capítulos"; detalle: e.inicioCapitulos.length ? "Elegir escena" : ""
                           onElegida: panel.cual = "capitulos" }
            OpcionInicio { visible: e.hayDisco && !e.sinClave; etiqueta: "Audio"; detalle: e.inicioAudio[e.inicioAudioSel] || ""
                           onElegida: panel.cual = "audio" }
            OpcionInicio { visible: e.hayDisco && !e.sinClave; etiqueta: "Subtítulos"; detalle: e.inicioSubs[e.inicioSubSel] || ""
                           onElegida: panel.cual = "subs" }
            OpcionInicio { visible: e.hayDisco && !e.sinClave && e.inicioTitulos.length > 0; etiqueta: "Otros títulos"
                           detalle: e.inicioTitulos.length + (e.inicioTitulos.length === 1 ? " extra" : " extras")
                           onElegida: panel.cual = "titulos" }
            OpcionInicio { visible: e.hayDisco; etiqueta: "Expulsar disco"; onElegida: { panel.cual = ""; ctl.expulsar() } }
            OpcionInicio { etiqueta: "Componentes"
                           detalle: e.avisosComp > 0 ? e.avisosComp + (e.avisosComp === 1 ? " aviso" : " avisos") : "Todo listo"
                           onElegida: panel.cual = "componentes" }
        }

        Rectangle {
            id: panel
            property string cual: ""
            visible: cual !== "" && (e.hayDisco || cual === "componentes")
            anchors.right: parent.right; anchors.rightMargin: Math.max(32, parent.width * 0.05)
            anchors.verticalCenter: parent.verticalCenter
            width: Math.min(cual === "componentes" ? 480 : 420, parent.width * 0.4)
            height: Math.min(parent.height * 0.8, (cual === "componentes" ? listaComp.contentHeight + 40 : lista.contentHeight) + 76)
            radius: 16; color: "#d9141519"; border.color: "#1fffffff"
            Text {
                x: 22; y: 18
                text: panel.cual === "capitulos" ? "Capítulos" : panel.cual === "audio" ? "Audio"
                    : panel.cual === "titulos" ? "Otros títulos" : panel.cual === "componentes" ? "Componentes" : "Subtítulos"
                color: acento; font.pixelSize: 13; font.letterSpacing: 2; font.bold: true
            }
            Boton { icono: "volver"; tam: 32; anchors.right: parent.right; anchors.rightMargin: 12; y: 8
                    onPulsado: { panel.cual = ""; enfocarInicio() } }
            ListView {
                id: listaComp
                visible: panel.cual === "componentes"
                anchors.fill: parent; anchors.topMargin: 52; anchors.margins: 12; anchors.bottomMargin: 40
                clip: true; spacing: 4
                model: e.componentes
                delegate: Item {
                    width: ListView.view.width; height: colComp.implicitHeight + 14
                    Rectangle {
                        x: 6; y: 12; width: 10; height: 10; radius: 5
                        color: modelData.estado === "ok" ? "#5cb85c" : modelData.estado === "aviso" ? acento : "#e05050"
                    }
                    Column {
                        id: colComp
                        x: 26; y: 6; width: parent.width - 32; spacing: 2
                        Text { text: modelData.nombre; color: texto; font.pixelSize: 15 }
                        Text { width: parent.width; wrapMode: Text.WordWrap; color: tenue; font.pixelSize: 12
                               text: modelData.detalle }
                    }
                }
            }
            Text {
                visible: panel.cual === "componentes"
                anchors.bottom: parent.bottom; anchors.bottomMargin: 14; x: 22; width: parent.width - 44
                elide: Text.ElideMiddle; color: "#6b7077"; font.pixelSize: 11
                text: "Registro: " + e.registro
            }
            ListView {
                id: lista
                visible: panel.cual !== "componentes"
                anchors.fill: parent; anchors.topMargin: 52; anchors.margins: 12
                clip: true
                model: panel.cual === "capitulos" ? e.inicioCapitulos : panel.cual === "audio" ? e.inicioAudio
                     : panel.cual === "titulos" ? e.inicioTitulos : e.inicioSubs
                delegate: Rectangle {
                    width: ListView.view.width; height: 44; radius: 8
                    readonly property bool marcado: panel.cual === "audio" ? index === e.inicioAudioSel
                                                  : panel.cual === "subs" ? index === e.inicioSubSel : false
                    color: zonaL.containsMouse ? "#22ffffff" : "transparent"
                    Text { x: 14; anchors.verticalCenter: parent.verticalCenter; text: modelData
                           color: marcado ? acento : texto; font.pixelSize: 16 }
                    MouseArea {
                        id: zonaL; anchors.fill: parent; hoverEnabled: true
                        onClicked: {
                            if (panel.cual === "capitulos") { ctl.reproducirPelicula(index); panel.cual = "" }
                            else if (panel.cual === "titulos") { ctl.reproducirTitulo(index); panel.cual = "" }
                            else if (panel.cual === "audio") ctl.elegirAudioInicio(index)
                            else ctl.elegirSubInicio(index)
                        }
                    }
                }
            }
        }

        Text {
            visible: win.height >= 600
            anchors.bottom: parent.bottom; anchors.bottomMargin: 14; anchors.horizontalCenter: parent.horizontalCenter
            text: "↑ ↓ elegir   ·   Enter aceptar   ·   F pantalla completa   ·   Q salir"
            color: "#6b7077"; font.pixelSize: 12
        }
    }

    // ---------- Barra superior ----------
    Rectangle {
        id: arriba
        visible: !enInicio
        anchors.left: parent.left; anchors.right: parent.right; anchors.top: parent.top
        height: 70
        opacity: controlesVisibles ? 1 : 0
        Behavior on opacity { NumberAnimation { duration: 250 } }
        gradient: Gradient {
            GradientStop { position: 0.0; color: "#cc000000" }
            GradientStop { position: 1.0; color: "transparent" }
        }
        HoverHandler { id: sobreArriba }
        RowLayout {
            anchors.fill: parent; anchors.leftMargin: 14; anchors.rightMargin: 14; anchors.bottomMargin: 14
            spacing: 10
            Boton { icono: "volver"; tam: 38; onPulsado: ctl.detener() }
            Text { text: e.titulo; color: texto; font.pixelSize: 17; font.weight: Font.Medium
                   Layout.fillWidth: true; elide: Text.ElideRight }
            Rectangle {
                visible: e.modo === "disco" && e.enPeliculaDisco && e.reanudarPos > 0 && e.posicion < e.reanudarPos - 30
                height: 34; radius: 17; width: textoReanudar.implicitWidth + 30
                color: zonaR.containsMouse ? Qt.lighter(acento, 1.12) : acento
                Text { id: textoReanudar; anchors.centerIn: parent; color: "#141414"; font.pixelSize: 14; font.bold: true
                       text: "Reanudar desde " + hms(e.reanudarPos) + "  (R)" }
                MouseArea { id: zonaR; anchors.fill: parent; hoverEnabled: true; onClicked: ctl.reanudarAqui() }
            }
            Boton { icono: "menu"; tam: 38; onPulsado: ctl.menuDisco() }
        }
    }

    // Velocidad distinta de 1×: siempre visible
    Rectangle {
        visible: !enInicio && Math.abs((e.velocidad || 1) - 1) > 0.01
        anchors.top: parent.top; anchors.topMargin: 72; anchors.right: parent.right; anchors.rightMargin: 18
        height: 30; radius: 15; width: textoVel.implicitWidth + 28
        color: acento
        Text { id: textoVel; anchors.centerIn: parent; color: "#141414"; font.pixelSize: 13; font.bold: true
               text: (Math.round((e.velocidad || 1) * 100) / 100) + "×   ·   clic para 1×" }
        MouseArea { anchors.fill: parent; onClicked: ctl.velocidadNormal() }
    }

    // ---------- Barra inferior ----------
    Rectangle {
        id: barra
        visible: !enInicio && !e.menuVisible
        anchors.left: parent.left; anchors.right: parent.right; anchors.bottom: parent.bottom
        height: 118
        opacity: controlesVisibles ? 1 : 0
        Behavior on opacity { NumberAnimation { duration: 250 } }
        gradient: Gradient {
            GradientStop { position: 0.0; color: "transparent" }
            GradientStop { position: 1.0; color: "#e6000000" }
        }
        HoverHandler { id: sobreBarra }

        Item {
            id: progreso
            anchors.left: parent.left; anchors.right: parent.right; anchors.leftMargin: 22; anchors.rightMargin: 22
            y: 30; height: 24
            property bool arrastrando: false
            property real posArrastre: 0
            readonly property real frac: arrastrando ? posArrastre : (e.duracion > 0 ? Math.min(1, e.posicion / e.duracion) : 0)
            Rectangle {
                anchors.verticalCenter: parent.verticalCenter
                width: parent.width; height: zonaB.containsMouse || progreso.arrastrando ? 6 : 4; radius: height / 2
                color: "#40ffffff"
                Behavior on height { NumberAnimation { duration: 100 } }
                Rectangle { width: parent.width * progreso.frac; height: parent.height; radius: parent.radius; color: acento }
            }
            Repeater {
                model: e.duracion > 0 ? e.capitulos : []
                Rectangle {
                    visible: modelData > 0.5
                    x: progreso.width * modelData / e.duracion - 1
                    anchors.verticalCenter: parent.verticalCenter
                    width: 2; height: 10; radius: 1; color: "#b3ffffff"
                }
            }
            Rectangle {
                visible: zonaB.containsMouse || progreso.arrastrando
                x: progreso.width * progreso.frac - width / 2
                anchors.verticalCenter: parent.verticalCenter
                width: 14; height: 14; radius: 7; color: texto
            }
            Rectangle {
                visible: zonaB.containsMouse && e.duracion > 0
                y: -32; x: Math.max(0, Math.min(progreso.width - width, zonaB.mouseX - width / 2))
                width: textoTip.implicitWidth + 16; height: 24; radius: 6; color: "#e6111214"
                Text { id: textoTip; anchors.centerIn: parent; color: texto; font.pixelSize: 12
                       text: hms(e.duracion * Math.max(0, Math.min(1, zonaB.mouseX / progreso.width))) }
            }
            MouseArea {
                id: zonaB
                anchors.fill: parent
                hoverEnabled: true
                onPressed: function(m) { progreso.arrastrando = true; progreso.posArrastre = Math.max(0, Math.min(1, m.x / width)) }
                onPositionChanged: function(m) { if (pressed) progreso.posArrastre = Math.max(0, Math.min(1, m.x / width)) }
                onReleased: { ctl.irA(progreso.posArrastre); progreso.arrastrando = false }
            }
        }

        Row {
            anchors.left: parent.left; anchors.leftMargin: 16; anchors.verticalCenter: centro.verticalCenter
            spacing: 6
            Boton { icono: "stop"; anchors.verticalCenter: parent.verticalCenter; onPulsado: ctl.detener() }
            Boton { icono: "expulsar"; anchors.verticalCenter: parent.verticalCenter; onPulsado: ctl.expulsar() }
            Text {
                visible: win.width >= 900
                leftPadding: 8; anchors.verticalCenter: parent.verticalCenter
                text: hms(e.posicion) + "  /  " + hms(e.duracion); color: tenue; font.pixelSize: 13
            }
        }

        Row {
            id: centro
            anchors.horizontalCenter: parent.horizontalCenter
            anchors.bottom: parent.bottom; anchors.bottomMargin: 12
            spacing: 10
            Boton { icono: "anterior"; anchors.verticalCenter: parent.verticalCenter; onPulsado: ctl.capituloRel(-1) }
            Boton {
                id: bAtras
                icono: "atras"; anchors.verticalCenter: parent.verticalCenter
                property bool sostenido: false
                Timer { id: tAtras; interval: 450; onTriggered: { bAtras.sostenido = true; tAtrasRep.start() } }
                Timer { id: tAtrasRep; interval: 300; repeat: true; triggeredOnStart: true; onTriggered: ctl.buscar(-10) }
                onPresionado: { sostenido = false; tAtras.start() }
                onSoltado: { tAtras.stop(); tAtrasRep.stop(); if (!sostenido) ctl.buscar(-10); sostenido = false }
            }
            Boton { icono: e.pausado ? "play" : "pausa"; tam: 54; principal: true; anchors.verticalCenter: parent.verticalCenter
                    onPulsado: ctl.pausa() }
            Boton {
                id: bAdelante
                icono: "adelante"; anchors.verticalCenter: parent.verticalCenter
                property bool sostenido: false
                Timer { id: tAdel; interval: 450; onTriggered: { bAdelante.sostenido = true; ctl.velocidad(2); tAdelRep.start() } }
                Timer { id: tAdelRep; interval: 1500; repeat: true; onTriggered: ctl.velocidad(Math.min(8, (e.velocidad || 1) * 2)) }
                onPresionado: { sostenido = false; tAdel.start() }
                onSoltado: { tAdel.stop(); tAdelRep.stop(); if (sostenido) ctl.velocidad(1); else ctl.buscar(10); sostenido = false }
            }
            Boton { icono: "siguiente"; anchors.verticalCenter: parent.verticalCenter; onPulsado: ctl.capituloRel(1) }
        }

        Row {
            anchors.right: parent.right; anchors.rightMargin: 18; anchors.verticalCenter: centro.verticalCenter
            spacing: 6
            Boton {
                icono: "audio"; anchors.verticalCenter: parent.verticalCenter
                onPulsado: popAudio.open()
                ListaPistas { id: popAudio; modelo: e.audio; prop: "aid"; onClosed: teclas.forceActiveFocus(); x: -width + parent.width; y: -height - 12 }
            }
            Boton {
                icono: "subs"; anchors.verticalCenter: parent.verticalCenter
                onPulsado: popSubs.open()
                ListaPistas { id: popSubs; modelo: e.subs; prop: "sid"; onClosed: teclas.forceActiveFocus(); x: -width + parent.width; y: -height - 12 }
            }
            Boton { icono: e.silencio ? "silencio" : "audio"; tam: 34; anchors.verticalCenter: parent.verticalCenter
                    onPulsado: ctl.silencio() }
            Item {
                visible: win.width >= 1000
                width: 90; height: 24; anchors.verticalCenter: parent.verticalCenter
                Rectangle {
                    anchors.verticalCenter: parent.verticalCenter
                    width: parent.width; height: 4; radius: 2; color: "#40ffffff"
                    Rectangle { width: parent.width * Math.min(1, (e.volumen || 0) / 100); height: parent.height
                                radius: 2; color: e.silencio ? tenue : texto }
                }
                MouseArea {
                    anchors.fill: parent
                    function fijar(m) { ctl.volumen(Math.max(0, Math.min(100, m.x / width * 100))) }
                    onPressed: function(m) { fijar(m) }
                    onPositionChanged: function(m) { if (pressed) fijar(m) }
                }
            }
            Boton { icono: "pantalla"; anchors.verticalCenter: parent.verticalCenter; onPulsado: alternarPantalla() }
        }
    }

    // ---------- Avisos ----------
    Rectangle {
        id: aviso
        anchors.horizontalCenter: parent.horizontalCenter
        y: parent.height - 170
        width: Math.min(win.width - 40, textoAviso.implicitWidth + 36); height: 42; radius: 12
        color: "#ee111214"; border.color: "#22ffffff"
        opacity: 0
        Text { id: textoAviso; anchors.centerIn: parent; width: parent.width - 24; horizontalAlignment: Text.AlignHCenter
               elide: Text.ElideRight; color: texto; font.pixelSize: 15; text: e.aviso }
        SequentialAnimation {
            id: animAviso
            NumberAnimation { target: aviso; property: "opacity"; to: 1; duration: 150 }
            PauseAnimation { duration: 2600 }
            NumberAnimation { target: aviso; property: "opacity"; to: 0; duration: 400 }
        }
    }
}
