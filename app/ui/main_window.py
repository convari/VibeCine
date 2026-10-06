# -*- coding: utf-8 -*-
"""Janela principal: sidebar + páginas empilhadas."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QFrame, QHBoxLayout, QLabel, QMainWindow,
                               QPushButton, QStackedWidget, QSystemTrayIcon,
                               QVBoxLayout, QWidget)

from app.core import branding
from app.core.config import load_config
from app.core.history import HistoryStore
from app.ui import theme
from app.ui.onboarding import OnboardingDialog
from app.ui.pages.downloads import DownloadsPage
from app.ui.pages.history import HistoryPage
from app.ui.pages.library import LibraryPage
from app.ui.pages.settings import SettingsPage
from app.ui.resources.icons import (app_icon, ensure_icon_files,
                                    horizontal_pixmap, nav_icon)
from app.ui.widgets.toast import ToastManager

_PAGES = (
    ("library", "🎬  Biblioteca"),
    ("downloads", "⬇  Downloads"),
    ("history", "🕘  Histórico"),
    ("settings", "⚙  Configurações"),
)


class MainWindow(QMainWindow):
    def __init__(self, cfg: dict | None = None, manager_factory=None,
                 history: HistoryStore | None = None):
        super().__init__()
        self.setWindowTitle(f"{branding.APP_NAME} — Downloader Pro")
        self.resize(1180, 760)
        self.setMinimumSize(980, 620)
        try:
            self.setWindowIcon(app_icon())
        except Exception:
            pass

        self.cfg = cfg if cfg is not None else load_config()
        self.history = history if history is not None else HistoryStore()

        root = QWidget()
        root.setObjectName("root")
        self.setCentralWidget(root)
        lay = QHBoxLayout(root)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        # ── Sidebar ──
        sidebar = QFrame()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(220)
        sb = QVBoxLayout(sidebar)
        sb.setContentsMargins(14, 18, 14, 14)
        sb.setSpacing(6)
        # Wordmark horizontal oficial (ícone + VibeCine)
        word = QLabel()
        word.setPixmap(horizontal_pixmap(40))
        word.setAlignment(Qt.AlignLeft)
        sb.addWidget(word)
        sub = QLabel("DOWNLOADER PRO")
        sub.setObjectName("brandSub")
        sub.setStyleSheet("letter-spacing: 3px;")
        sb.addWidget(sub)
        sb.addSpacing(18)

        self.nav_buttons: dict[str, QPushButton] = {}
        _ICONS = {"library": "library", "downloads": "downloads",
                  "history": "history", "settings": "settings"}
        for key, label in _PAGES:
            b = QPushButton(label)
            b.setObjectName("nav")
            b.setCheckable(True)
            b.setCursor(Qt.PointingHandCursor)
            b.setIcon(nav_icon(_ICONS.get(key, "library")))
            b.clicked.connect(lambda _c=False, k=key: self.navigate(k))
            sb.addWidget(b)
            self.nav_buttons[key] = b
        sb.addStretch(1)

        foot = QLabel(f"v{branding.APP_VERSION}")
        foot.setObjectName("brandSub")
        sb.addWidget(foot)
        lay.addWidget(sidebar)

        # ── Páginas ──
        self.stack = QStackedWidget()
        lay.addWidget(self.stack, 1)

        self.library = LibraryPage(self.cfg)
        self.downloads = DownloadsPage(self.cfg, self.history,
                                       manager_factory=manager_factory)
        self.history_page = HistoryPage(self.history, self.cfg)
        self.settings = SettingsPage(self.cfg)
        for w in (self.library, self.downloads, self.history_page,
                  self.settings):
            self.stack.addWidget(w)

        self._page_index = {"library": 0, "downloads": 1, "history": 2,
                            "settings": 3}

        # ── Toasts + notificação não intrusiva ──
        self.toasts = ToastManager(self)
        self.tray = QSystemTrayIcon(app_icon(), self) if \
            QSystemTrayIcon.isSystemTrayAvailable() else None
        if self.tray is not None:
            self.tray.setToolTip(f"{branding.APP_NAME} — Downloader Pro")
        from app.ui.widgets.notifier import Notifier
        self.notifier = Notifier(self.tray, self)
        self.notifier.inAppToast.connect(
            lambda msg, kind: getattr(self.toasts, kind, self.toasts.info)(msg))
        self.downloads.notifier = self.notifier
        for page in (self.library, self.downloads, self.history_page,
                     self.settings):
            page.wantToast.connect(
                lambda msg, kind: getattr(self.toasts, kind, self.toasts.info)(msg))

        # ── Navegação entre páginas ──
        self.library.entriesSelected.connect(self._send_to_downloads)
        self.downloads.historyChanged.connect(self.history_page.reload)
        self.settings.themeChanged.connect(self.apply_theme)
        self.settings.configSaved.connect(self._on_config_saved)

        self.apply_theme(self.cfg.get("theme", "dark"))
        self.navigate("library")
        try:
            ensure_icon_files()
        except Exception:
            pass  # ícone é cosmético; nunca pode impedir a abertura

    # ── Primeira execução: onboarding + termos ──────────────────────────

    def maybe_show_onboarding(self) -> bool:
        """Exibe o onboarding na 1ª execução. Retorna True se exibiu."""
        if self.cfg.get("onboarding_done"):
            return False
        dlg = OnboardingDialog(self.cfg, self)
        dlg.finishedOk.connect(self._on_onboarding_done)
        dlg.exec()
        return True

    def _on_onboarding_done(self, cfg: dict):
        self.cfg.update(cfg)
        self.apply_theme(self.cfg.get("theme", "dark"))
        self.toasts.success(f"Bem-vindo ao {branding.APP_NAME}!")

    # ── Navegação ────────────────────────────────────────────────────────

    def navigate(self, key: str):
        self.stack.setCurrentIndex(self._page_index[key])
        for k, b in self.nav_buttons.items():
            b.setChecked(k == key)
        if key == "history":
            self.history_page.reload()

    def _send_to_downloads(self, entries: list):
        self.downloads.enqueue(entries)
        self.navigate("downloads")

    # ── Tema/config ──────────────────────────────────────────────────────

    def apply_theme(self, name: str):
        from PySide6.QtWidgets import QApplication
        theme.set_theme(name)
        app = QApplication.instance()
        if app is not None:
            app.setPalette(theme.app_palette(name))  # placeholders, alternates...
            app.setStyleSheet(theme.build_qss(name))
            # Re-render de áreas com cores semânticas pintadas em código
            if hasattr(self, "library") and self.library.filtered:
                self.library._apply_filters_now()
            if hasattr(self, "history_page"):
                self.history_page.reload()

    def _on_config_saved(self, cfg: dict):
        self.cfg.update(cfg)
        self.apply_theme(self.cfg.get("theme", "dark"))

    # ── Primeira execução ────────────────────────────────────────────────

    def maybe_show_onboarding(self):
        """Exibe o onboarding uma única vez (pulável), com termos de uso."""
        if self.cfg.get("onboarding_done"):
            return
        dlg = OnboardingDialog(self.cfg, self)
        dlg.finishedOk.connect(lambda c: (self.cfg.update(c),
                                          self.apply_theme(c.get("theme", "dark"))))
        dlg.exec()

    # ── Links externos (vibcine://) ──────────────────────────────────────

    def open_external_url(self, url: str):
        """Carrega uma URL vinda do protocolo vibcine:// (já validada)."""
        self.show()
        self.raise_()
        self.activateWindow()
        self.navigate("library")
        self.library.url_edit.setText(url)
        self.toasts.info("Link recebido via vibcine://")
        self.library.load_url()

    # ── Encerramento limpo ───────────────────────────────────────────────
    def closeEvent(self, event):
        if self.downloads.has_active():
            self.downloads.cancel_all()
        self.library.shutdown()
        self.settings.shutdown()
        self.downloads.shutdown()
        super().closeEvent(event)
