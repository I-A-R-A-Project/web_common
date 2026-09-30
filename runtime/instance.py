"""Coordinación de instancias para los navegadores de IARA."""

import json

from PyQt6.QtCore import QObject, QTimer
from PyQt6.QtNetwork import QLocalServer, QLocalSocket


SERVER_NAME = "IARA-Browser-Instance-v1"


def _payload(url=""):
    return json.dumps({"url": url or ""}, separators=(",", ":")).encode("utf-8") + b"\n"


def forward_to_running_instance(url="", server_name=SERVER_NAME):
    """Envía una orden a la instancia primaria si existe."""
    socket = QLocalSocket()
    socket.connectToServer(server_name)
    if not socket.waitForConnected(300):
        return False
    socket.write(_payload(url))
    socket.waitForBytesWritten(300)
    socket.disconnectFromServer()
    return True


class BrowserInstanceServer(QObject):
    """Servidor local que recibe órdenes de nuevas ejecuciones del navegador."""

    def __init__(self, on_open, server_name=SERVER_NAME, parent=None):
        super().__init__(parent)
        self._on_open = on_open
        self._server_name = server_name
        self._server = QLocalServer(self)
        self._server.newConnection.connect(self._read_connection)

    def listen(self):
        return self._server.listen(self._server_name)

    def set_handler(self, on_open):
        self._on_open = on_open

    def _read_connection(self):
        while self._server.hasPendingConnections():
            socket = self._server.nextPendingConnection()
            socket.readyRead.connect(
                lambda current=socket: self._read_socket(current)
            )
            socket.disconnected.connect(socket.deleteLater)
            if socket.bytesAvailable():
                self._read_socket(socket)

    def _read_socket(self, socket):
        while socket.canReadLine():
            raw = bytes(socket.readLine()).strip()
            try:
                message = json.loads(raw.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                continue
            if isinstance(message, dict):
                url = message.get("url", "")
                if isinstance(url, str):
                    QTimer.singleShot(0, lambda value=url: self._on_open(value))

    def close(self):
        self._server.close()
        QLocalServer.removeServer(self._server_name)


def acquire_browser_instance(on_open=None, server_name=SERVER_NAME):
    """Devuelve el servidor primario o ``None`` si otra instancia ya existe."""
    if forward_to_running_instance(server_name=server_name):
        return None

    server = BrowserInstanceServer(on_open, server_name=server_name)
    if server.listen():
        return server

    # Otro proceso pudo empezar a escuchar entre el primer intento y listen().
    if forward_to_running_instance(server_name=server_name):
        server.deleteLater()
        return None

    server.deleteLater()
    return None
