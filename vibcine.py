#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""VibeCine Downloader Pro — interface moderna (PySide6).

Uso:
    vibcine.exe                     (app empacotado)
    python vibcine.py               (desenvolvimento)
    vibcine.exe "vibcine://load?url=..."

Instância única: um segundo processo com um link vibcine:// envia a URL à
instância já aberta via QLocalServer e encerra.

A interface legada Tkinter permanece disponível em m3u_downloader.py.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

SERVER_NAME = "vibcine-single-instance"


def _selftest() -> int:
    """Modo de auto-teste para verificação de build (sem janela)."""
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    from PySide6.QtWidgets import QApplication

    from app.core import branding, paths
    from app.core.config import load_config
    from app.core.history import HistoryStore
    from app.ui.main_window import MainWindow

    app = QApplication([])
    window = MainWindow(cfg=load_config())
    window.show()
    app.processEvents()
    print(f"SELFTEST OK | {branding.APP_PRODUCT} v{branding.APP_VERSION} | "
          f"frozen={paths.is_frozen()}")
    window.close()
    HistoryStore()  # cria/abre o banco de dados do usuário
    return 0


def main() -> int:
    from PySide6.QtCore import QTimer
    from PySide6.QtNetwork import QLocalServer, QLocalSocket
    from PySide6.QtWidgets import QApplication

    from app.core import branding, protocol
    from app.core.config import load_config
    from app.ui.main_window import MainWindow

    if "--selftest" in sys.argv:
        return _selftest()

    link_arg = next((a for a in sys.argv[1:]
                     if a.lower().startswith("vibcine://")), None)
    if link_arg:
        print("[vibcine] link recebido:", protocol.log_safe_uri(link_arg))

    app = QApplication(sys.argv)
    app.setApplicationName(branding.APP_PRODUCT)
    app.setOrganizationName(branding.APP_VENDOR)

    # ── Instância única ──────────────────────────────────────────────────
    socket = QLocalSocket()
    socket.connectToServer(SERVER_NAME)
    if socket.waitForConnected(500):
        # Já existe uma janela: só entrega o link e sai.
        if link_arg:
            socket.write(link_arg.encode("utf-8"))
            socket.flush()
            socket.waitForBytesWritten(1000)
        return 0

    cfg = load_config()
    window = MainWindow(cfg=cfg)

    server = QLocalServer(window)

    def _on_connection():
        while server.hasPendingConnections():
            conn = server.nextPendingConnection()
            data = bytes(conn.readAll()).decode("utf-8", errors="replace")
            url, err = protocol.parse_vibcine_uri(data)
            if url:
                window.open_external_url(url)
            elif err and data:
                window.toasts.warning(f"Link vibcine:// rejeitado: {err}")
            conn.disconnectFromServer()

    QLocalServer.removeServer(SERVER_NAME)  # limpeza de restos de crash
    server.listen(SERVER_NAME)
    server.newConnection.connect(_on_connection)

    # Onboarding na 1ª execução (pulável; nunca se repete após concluído).
    window.show()
    QTimer.singleShot(0, window.maybe_show_onboarding)

    # Link passado na linha de comando (app estava fechado).
    if link_arg:
        def _open_initial():
            url, err = protocol.parse_vibcine_uri(link_arg)
            if url:
                window.open_external_url(url)
            elif err:
                window.toasts.warning(f"Link vibcine:// rejeitado: {err}")
        QTimer.singleShot(600, _open_initial)

    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
