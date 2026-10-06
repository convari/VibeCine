# -*- coding: utf-8 -*-
"""Onboarding de primeira execução + Termos de Uso.

Fluxo: Boas-vindas → Termos (aceite obrigatório para continuar) →
Pasta de downloads → Verificação das ferramentas → "Tudo pronto".

Pode ser pulado; é exibido apenas até `onboarding_done` ser gravado
na configuração. Aceite dos termos fica registrado em `terms_accepted`.
"""

from __future__ import annotations

import os
import sys

from PySide6.QtCore import QProcess, Qt, Signal
from PySide6.QtWidgets import (QCheckBox, QDialog, QFileDialog, QFrame,
                               QHBoxLayout, QLabel, QLineEdit, QPushButton,
                               QStackedWidget, QTextBrowser, QVBoxLayout)

from app.core import branding
from app.core.config import save_config
from app.core.tools import APP_DIR, check_tools
from app.ui import theme
from app.ui.resources.icons import logo_pixmap


class OnboardingDialog(QDialog):
    finishedOk = Signal(dict)

    def __init__(self, cfg: dict, parent=None):
        super().__init__(parent)
        self.cfg = cfg
        self.setWindowTitle(f"Bem-vindo ao {branding.APP_NAME}")
        self.setMinimumSize(560, 460)
        self.setModal(True)
        self._proc: QProcess | None = None
        self._build_ui()

    # ── Fluxo de páginas ─────────────────────────────────────────────────

    def _build_ui(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)

        self.stack = QStackedWidget()
        lay.addWidget(self.stack, 1)

        bar = QHBoxLayout()
        bar.setContentsMargins(20, 0, 20, 14)
        self.skip_btn = QPushButton("Pular")
        self.skip_btn.setObjectName("muted")
        self.skip_btn.setStyleSheet("border: none;")
        self.skip_btn.clicked.connect(self._skip)
        bar.addWidget(self.skip_btn)
        bar.addStretch(1)
        self.back_btn = QPushButton("Voltar")
        self.back_btn.clicked.connect(self._back)
        self.back_btn.setVisible(False)
        bar.addWidget(self.back_btn)
        self.next_btn = QPushButton("Avançar")
        self.next_btn.setObjectName("primary")
        self.next_btn.clicked.connect(self._next)
        bar.addWidget(self.next_btn)
        lay.addLayout(bar)

        self._pages = [self._page_welcome(), self._page_terms(),
                       self._page_folder(), self._page_tools(),
                       self._page_done()]
        for p in self._pages:
            self.stack.addWidget(p)
        self._update_nav()

    def _page_shell(self, title: str, subtitle: str = ""):
        page = QFrame()
        v = QVBoxLayout(page)
        v.setContentsMargins(28, 22, 28, 10)
        v.setSpacing(10)
        t = QLabel(title)
        t.setStyleSheet("font-size: 18px; font-weight: 700;")
        v.addWidget(t)
        if subtitle:
            s = QLabel(subtitle)
            s.setObjectName("muted")
            s.setWordWrap(True)
            v.addWidget(s)
        return page, v

    def _page_welcome(self):
        page, v = self._page_shell(
            f"Bem-vindo ao {branding.APP_PRODUCT} 👋", branding.APP_TAGLINE)
        logo = QLabel()
        logo.setPixmap(logo_pixmap(96))
        logo.setAlignment(Qt.AlignCenter)
        v.addWidget(logo)
        s = QLabel(
            "Organize, visualize e baixe conteúdos das suas listas M3U/IPTV "
            "e de vídeos online — com downloads simultâneos, pausa/retomada, "
            "histórico e compartilhamento seguro.\n\n"
            "Este assistente rápido prepara tudo em menos de um minuto.")
        s.setWordWrap(True)
        v.addWidget(s)
        v.addStretch(1)
        return page

    def _page_terms(self):
        page, v = self._page_shell("Termos de Uso",
                                   "Leia e aceite para continuar.")
        self.terms_txt = QTextBrowser()
        self.terms_txt.setPlainText(branding.TERMS_OF_USE)
        v.addWidget(self.terms_txt, 1)
        self.terms_cb = QCheckBox("Li e aceito os Termos de Uso.")
        v.addWidget(self.terms_cb)
        return page

    def _page_folder(self):
        page, v = self._page_shell(
            "Pasta de downloads",
            "Onde seus arquivos serão salvos. Você pode mudar depois em "
            "Configurações.")
        row = QHBoxLayout()
        self.folder_edit = QLineEdit(self.cfg.get("download_folder", ""))
        row.addWidget(self.folder_edit, 1)
        browse = QPushButton("Escolher…")
        browse.clicked.connect(self._browse)
        row.addWidget(browse)
        v.addLayout(row)
        v.addStretch(1)
        return page

    def _page_tools(self):
        page, v = self._page_shell(
            "Verificação do ambiente",
            "O VibeCine usa yt-dlp, FFmpeg e Deno (todos locais, nada é "
            "instalado no seu sistema operacional).")
        self.tools_lbl = QLabel("Verificando…")
        self.tools_lbl.setObjectName("muted")
        self.tools_lbl.setWordWrap(True)
        v.addWidget(self.tools_lbl)
        row = QHBoxLayout()
        self.update_btn = QPushButton("Baixar/atualizar ferramentas")
        self.update_btn.clicked.connect(self._run_updater)
        row.addWidget(self.update_btn)
        self.upd_status = QLabel("")
        self.upd_status.setObjectName("muted")
        row.addWidget(self.upd_status, 1)
        v.addLayout(row)
        v.addStretch(1)
        return page

    def _page_done(self):
        page, v = self._page_shell("Tudo pronto! 🎉")
        s = QLabel(
            "Cole uma URL de lista M3U ou do YouTube na Biblioteca e comece. "
            "Boa sessão!")
        s.setWordWrap(True)
        v.addWidget(s)
        v.addStretch(1)
        return page

    # ── Navegação ────────────────────────────────────────────────────────

    def _update_nav(self):
        i = self.stack.currentIndex()
        last = len(self._pages) - 1
        self.back_btn.setVisible(0 < i < last)
        self.skip_btn.setVisible(i not in (1, last))  # termos exigem decisão
        if i == 1:
            self.next_btn.setText("Aceito e continuar")
            self.next_btn.setEnabled(self.terms_cb.isChecked())
            self.terms_cb.toggled.connect(
                lambda _c: self.next_btn.setEnabled(self.terms_cb.isChecked()))
        elif i == last:
            self.next_btn.setText("Começar 🎬")
            self.next_btn.setEnabled(True)
        else:
            self.next_btn.setText("Avançar")
            self.next_btn.setEnabled(True)

    def _next(self):
        i = self.stack.currentIndex()
        if i == 1:
            self.cfg["terms_accepted"] = True
        if i == 2:
            folder = self.folder_edit.text().strip()
            if folder:
                self.cfg["download_folder"] = folder
        if i == 3:
            self._refresh_tools()
        if i == len(self._pages) - 1:
            self._finish()
            return
        self.stack.setCurrentIndex(i + 1)
        self._update_nav()

    def _back(self):
        self.stack.setCurrentIndex(max(0, self.stack.currentIndex() - 1))
        self._update_nav()

    def _skip(self):
        self._finish()

    def _finish(self):
        self.cfg["onboarding_done"] = True
        save_config(self.cfg)
        self.finishedOk.emit(self.cfg)
        self.accept()

    # ── Ferramentas ──────────────────────────────────────────────────────

    def _browse(self):
        d = QFileDialog.getExistingDirectory(
            self, "Pasta de downloads",
            self.folder_edit.text() or os.path.expanduser("~"))
        if d:
            self.folder_edit.setText(d)

    def _refresh_tools(self):
        status = check_tools(self.cfg)
        lines = []
        for key, name in (("ytdlp_path", "yt-dlp"), ("ffmpeg_path", "FFmpeg"),
                          ("deno_path", "Deno")):
            ok = status[key]["ok"]
            lines.append(f"{'✔' if ok else '✖'} {name}"
                         + ("" if ok else " — não encontrado"))
        self.tools_lbl.setText("\n".join(lines))

    def _run_updater(self):
        if self._proc and self._proc.state() != QProcess.NotRunning:
            return
        updater = os.path.join(APP_DIR, "atualizar.py")
        if not os.path.isfile(updater):
            self.upd_status.setText("atualizar.py não encontrado.")
            return
        self.update_btn.setEnabled(False)
        self.upd_status.setText("Baixando… aguarde.")
        self._proc = QProcess(self)
        self._proc.setProgram(sys.executable)
        self._proc.setArguments([updater])
        self._proc.finished.connect(self._update_done)
        self._proc.start()

    def _update_done(self, code, _status):
        self.update_btn.setEnabled(True)
        self.upd_status.setText("Concluído." if code == 0 else "Falhou.")
        self._refresh_tools()

    def closeEvent(self, event):
        if self._proc and self._proc.state() != QProcess.NotRunning:
            self._proc.kill()
            self._proc.waitForFinished(2000)
        super().closeEvent(event)
