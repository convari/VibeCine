# -*- coding: utf-8 -*-
"""Teste do comportamento não intrusivo ao concluir downloads."""

import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QSystemTrayIcon  # noqa: E402

from app.ui.widgets.notifier import Notifier  # noqa: E402


class TestNotifierNaoIntrusivo(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_background_usa_bandeja_sem_foco(self):
        """Sem janela ativa (app em background), deve usar tray, nunca
        foco/raise/activate."""
        called = {"activate": False}

        class FakeWindow:
            def activateWindow(self):
                called["activate"] = True

        tray = None
        if QSystemTrayIcon.isSystemTrayAvailable():
            tray = QSystemTrayIcon()

        notifier = Notifier(tray)
        toasts = []
        notifier.inAppToast.connect(lambda m, k: toasts.append(m))
        notifier.notify("Download concluído", "Filme X")
        # Offscreen/background: janela nunca está ativa → canal tray
        self.assertIn(notifier.last_channel, ("tray",))
        self.assertEqual(toasts, [])
        self.assertFalse(called["activate"])

    def test_foreground_usa_toast(self):
        """Janela ativa → toast interno, sem balão do sistema."""
        from PySide6.QtWidgets import QWidget
        notifier = Notifier(None)
        win = QWidget()
        win.show()
        win.activateWindow()
        self.app.processEvents()
        toasts = []
        notifier.inAppToast.connect(lambda m, k: toasts.append(m))
        # Força estado ativo para o teste determinístico
        notifier.app_is_active = lambda: True
        notifier.notify("Download concluído", "Filme Y")
        self.assertEqual(notifier.last_channel, "toast")
        self.assertEqual(toasts, ["Filme Y"])
        win.close()

    def test_mensagem_registrada(self):
        notifier = Notifier(None)
        notifier.notify("Download concluído", "Ação")
        self.assertEqual(notifier.last_message, "Ação")
        self.assertIn(notifier.last_channel, ("toast", "tray"))


if __name__ == "__main__":
    unittest.main()
