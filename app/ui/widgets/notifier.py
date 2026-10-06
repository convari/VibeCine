# -*- coding: utf-8 -*-
"""Notificação de conclusão de downloads — NÃO intrusiva.

Regra rígida (não quebrar): ao concluir um download,
- NÃO chamar activateWindow() / raise();
- NÃO QMessageBox/modal;
- NÃO roubar o foco de outro aplicativo (jogos em primeiro plano!).

Comportamento:
- VibeCine em primeiro plano → toast interno animado (in-app).
- VibeCine em segundo plano → balão da bandeja do Windows
  (QSystemTrayIcon.showMessage), sem ativar a janela.
"""

from __future__ import annotations

from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QApplication, QSystemTrayIcon


class Notifier(QObject):
    """Decide entre toast in-app (focado) e balão da bandeja (background)."""

    inAppToast = Signal(str, str)  # (mensagem, tipo) — conectado ao ToastManager

    def __init__(self, tray: QSystemTrayIcon | None, parent=None):
        super().__init__(parent)
        self.tray = tray
        # Espionagem de teste
        self.last_channel: str | None = None
        self.last_message: str | None = None

    def app_is_active(self) -> bool:
        return QApplication.activeWindow() is not None

    def notify(self, title: str, message: str, kind: str = "info"):
        """Notifica sem NUNCA roubar o foco."""
        self.last_message = message
        if self.app_is_active():
            self.last_channel = "toast"
            self.inAppToast.emit(message, kind)
        else:
            self.last_channel = "tray"
            if self.tray is not None:
                self.tray.show()  # visível apenas para garantir o balão
                self.tray.showMessage(
                    title, message, QSystemTrayIcon.Information, 4500)
            # Se não houver bandeja, silenciosamente descarta (não invadimos).
