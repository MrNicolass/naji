"""Single-instance guard based on QLocalServer."""

from __future__ import annotations

import logging

from PySide6.QtCore import QObject, Signal
from PySide6.QtNetwork import QLocalServer, QLocalSocket

log = logging.getLogger(__name__)

DEFAULT_KEY = "naji-desktop-single-instance"


def notify_running_instance(key: str = DEFAULT_KEY, timeout_ms: int = 400) -> bool:
    """Ask an existing instance to surface its bar. Returns True if reached."""
    socket = QLocalSocket()
    socket.connectToServer(key)
    if not socket.waitForConnected(timeout_ms):
        return False
    socket.write(b"show")
    socket.flush()
    socket.waitForBytesWritten(timeout_ms)
    socket.disconnectFromServer()
    return True


class SingleInstanceServer(QObject):
    """Server side of the single-instance guard."""

    activated = Signal()

    def __init__(self, key: str = DEFAULT_KEY, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._key = key
        self._server = QLocalServer(self)
        self._server.newConnection.connect(self._on_new_connection)
        QLocalServer.removeServer(key)
        self._listening = self._server.listen(key)
        if not self._listening:
            log.warning("Could not listen on %s: %s", key, self._server.errorString())

    @property
    def listening(self) -> bool:
        return self._listening

    def _on_new_connection(self) -> None:
        while self._server.hasPendingConnections():
            connection = self._server.nextPendingConnection()
            if connection is None:
                continue
            connection.waitForReadyRead(100)
            payload = bytes(connection.readAll())
            connection.disconnectFromServer()
            connection.deleteLater()
            if b"show" in payload:
                self.activated.emit()

    def close(self) -> None:
        self._server.close()
        QLocalServer.removeServer(self._key)
