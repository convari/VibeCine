# -*- coding: utf-8 -*-
"""Página Configurações — organizada em seções (Fase 5)."""

from __future__ import annotations

import os
import sys

from PySide6.QtCore import QProcess, Qt, Signal
from PySide6.QtWidgets import (QCheckBox, QComboBox, QFileDialog, QFrame,
                               QHBoxLayout, QLabel, QLineEdit, QPlainTextEdit,
                               QPushButton, QSpinBox, QTabWidget, QVBoxLayout,
                               QWidget)

from app.core import branding
from app.core.config import save_config
from app.core.tools import APP_DIR, check_tools
from app.ui.resources.icons import logo_pixmap


def _section_label(text: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setStyleSheet("font-weight: 700;")
    return lbl


def _hint(text: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setObjectName("muted")
    lbl.setWordWrap(True)
    lbl.setStyleSheet("font-size: 11px;")
    return lbl


class SettingsPage(QFrame):
    wantToast = Signal(str, str)
    themeChanged = Signal(str)
    configSaved = Signal(dict)

    def __init__(self, cfg: dict, parent=None):
        super().__init__(parent)
        self.cfg = cfg
        self._proc: QProcess | None = None
        self._build_ui()
        self._refresh_tools_status()

    # ── UI ───────────────────────────────────────────────────────────────

    def _build_ui(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 16, 20, 16)
        lay.setSpacing(10)

        title = QLabel("Configurações")
        title.setObjectName("pageTitle")
        lay.addWidget(title)

        tabs = QTabWidget()
        lay.addWidget(tabs, 1)
        tabs.addTab(self._tab_downloads(), "Downloads")
        tabs.addTab(self._tab_performance(), "Desempenho")
        tabs.addTab(self._tab_appearance(), "Aparência")
        tabs.addTab(self._tab_tools(), "Ferramentas")
        tabs.addTab(self._tab_updates(), "Atualizações")
        tabs.addTab(self._tab_about(), "Informações")

        save = QPushButton("Salvar configurações")
        save.setObjectName("primary")
        save.clicked.connect(self.save)
        lay.addWidget(save, alignment=Qt.AlignLeft)

    def _card(self):
        c = QFrame()
        c.setObjectName("card")
        v = QVBoxLayout(c)
        v.setContentsMargins(16, 14, 16, 14)
        v.setSpacing(8)
        return c, v

    def _tab_downloads(self):
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(4, 12, 4, 4)
        card, v = self._card()

        v.addWidget(_section_label("Pasta de downloads"))
        v.addWidget(_hint("Diretório onde os arquivos baixados serão salvos."))
        row = QHBoxLayout()
        self.folder_edit = QLineEdit(self.cfg.get("download_folder", ""))
        row.addWidget(self.folder_edit, 1)
        browse = QPushButton("Escolher…")
        browse.clicked.connect(self._browse)
        row.addWidget(browse)
        v.addLayout(row)

        v.addWidget(_section_label("Formato de saída"))
        v.addWidget(_hint(
            "\"Original\" preserva a melhor qualidade disponível. Escolha "
            "MP3 apenas se quiser apenas áudio."))
        self.fmt_cb = QComboBox()
        for lbl, val in (("Original (automático)", "original"),
                         ("MP4 (vídeo)", "mp4"), ("FullHD (1080p)", "fullhd"),
                         ("MP3 (somente áudio)", "mp3")):
            self.fmt_cb.addItem(lbl, val)
        self.fmt_cb.setCurrentIndex(
            max(0, self.fmt_cb.findData(self.cfg.get("format", "original"))))
        v.addWidget(self.fmt_cb)

        self.org_cb = QCheckBox("Organizar downloads em pastas por grupo")
        self.org_cb.setChecked(bool(self.cfg.get("organize_by_group", True)))
        v.addWidget(self.org_cb)
        v.addWidget(_hint("Ex.: Filmes/, Séries/, Esportes/…"))
        v.addStretch(1)
        lay.addWidget(card)
        return page

    def _tab_performance(self):
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(4, 12, 4, 4)
        card, v = self._card()

        v.addWidget(_section_label("Downloads simultâneos"))
        v.addWidget(_hint("Quantos itens da fila baixam ao mesmo tempo (1–8)."))
        self.conc_spin = QSpinBox()
        self.conc_spin.setRange(1, 8)
        self.conc_spin.setValue(
            int(self.cfg.get("max_concurrent_downloads", 2)))
        v.addWidget(self.conc_spin)

        v.addWidget(_section_label("Limite de velocidade"))
        v.addWidget(_hint("Limita a velocidade total por arquivo; útil para "
                          "não saturar sua conexão."))
        self.speed_cb = QComboBox()
        for lbl, val in (("Sem limite", "0"), ("1 MB/s", "1M"),
                         ("5 MB/s", "5M"), ("10 MB/s", "10M"),
                         ("20 MB/s", "20M"), ("50 MB/s", "50M")):
            self.speed_cb.addItem(lbl, val)
        self.speed_cb.setCurrentIndex(
            max(0, self.speed_cb.findData(self.cfg.get("speed_limit", "0"))))
        v.addWidget(self.speed_cb)
        v.addStretch(1)
        lay.addWidget(card)
        return page

    def _tab_appearance(self):
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(4, 12, 4, 4)
        card, v = self._card()
        v.addWidget(_section_label("Tema da interface"))
        v.addWidget(_hint("Aplicado imediatamente ao trocar."))
        self.theme_cb = QComboBox()
        self.theme_cb.addItem("Escuro (padrão VibeCine)", "dark")
        self.theme_cb.addItem("Claro", "light")
        self.theme_cb.setCurrentIndex(
            0 if self.cfg.get("theme", "dark") == "dark" else 1)
        self.theme_cb.currentIndexChanged.connect(
            lambda _i: self.themeChanged.emit(self.theme_cb.currentData()))
        v.addWidget(self.theme_cb)
        v.addStretch(1)
        lay.addWidget(card)
        return page

    def _tab_tools(self):
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(4, 12, 4, 4)
        card, v = self._card()
        v.addWidget(_section_label("Ferramentas locais"))
        v.addWidget(_hint("Caminhos dos executáveis. Por padrão ficam na "
                          "própria pasta do programa (portátil)."))
        for key, label in (("ytdlp_path", "yt-dlp:"),
                           ("ffmpeg_path", "FFmpeg:"),
                           ("deno_path", "Deno (necessário p/ YouTube):")):
            row = QHBoxLayout()
            row.addWidget(QLabel(label))
            edit = QLineEdit(str(self.cfg.get(key, "")))
            row.addWidget(edit, 1)
            v.addLayout(row)
            setattr(self, f"_{key}_edit", edit)
        self.tools_lbl = QLabel("Verificando…")
        self.tools_lbl.setObjectName("muted")
        v.addWidget(self.tools_lbl)
        v.addStretch(1)
        lay.addWidget(card)
        return page

    def _tab_updates(self):
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(4, 12, 4, 4)
        card, v = self._card()

        # Atualização do APLICATIVO (Fase 6)
        v.addWidget(_section_label("Atualização do aplicativo"))
        v.addWidget(_hint(
            f"Versão instalada: {branding.APP_VERSION}. A verificação baixa "
            "apenas pacotes com hash SHA-256 válido e preserva suas "
            "configurações, histórico e downloads."))
        row_upd = QHBoxLayout()
        self.app_update_btn = QPushButton("Verificar atualização do VibeCine")
        self.app_update_btn.clicked.connect(self.check_app_update)
        row_upd.addWidget(self.app_update_btn)
        self.app_upd_status = QLabel("")
        self.app_upd_status.setObjectName("muted")
        row_upd.addWidget(self.app_upd_status, 1)
        v.addLayout(row_upd)

        v.addWidget(_section_label("Atualizações das ferramentas"))
        v.addWidget(_hint(
            "Baixa as versões mais recentes do yt-dlp, FFmpeg e Deno "
            "(licenças nos avisos do pacote). Tudo fica em pasta gravável, "
            "sem alterar o Windows."))
        row = QHBoxLayout()
        self.update_btn = QPushButton("Verificar e atualizar ferramentas")
        self.update_btn.clicked.connect(self.run_updater)
        row.addWidget(self.update_btn)
        self.upd_status = QLabel("")
        self.upd_status.setObjectName("muted")
        row.addWidget(self.upd_status, 1)
        v.addLayout(row)
        self.upd_log = QPlainTextEdit()
        self.upd_log.setReadOnly(True)
        self.upd_log.setMaximumBlockCount(500)
        self.upd_log.setPlaceholderText("O progresso da atualização aparece aqui.")
        v.addWidget(self.upd_log, 1)
        lay.addWidget(card)
        return page

    def _tab_about(self):
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(4, 12, 4, 4)
        card, v = self._card()
        logo = QLabel()
        logo.setPixmap(logo_pixmap(72))
        logo.setAlignment(Qt.AlignCenter)
        v.addWidget(logo)
        name = QLabel(branding.APP_PRODUCT)
        name.setStyleSheet("font-size: 17px; font-weight: 700;")
        name.setAlignment(Qt.AlignCenter)
        v.addWidget(name)
        ver = QLabel(f"Versão {branding.APP_VERSION}")
        ver.setObjectName("muted")
        ver.setAlignment(Qt.AlignCenter)
        v.addWidget(ver)
        about = QLabel(branding.APP_ABOUT_TEXT)
        about.setWordWrap(True)
        about.setObjectName("muted")
        v.addWidget(about)
        v.addStretch(1)
        lay.addWidget(card)
        return page

    # ── Ações ────────────────────────────────────────────────────────────

    def _browse(self):
        d = QFileDialog.getExistingDirectory(
            self, "Pasta de downloads",
            self.folder_edit.text() or os.path.expanduser("~"))
        if d:
            self.folder_edit.setText(d)

    def save(self):
        self.cfg["download_folder"] = self.folder_edit.text().strip()
        self.cfg["format"] = self.fmt_cb.currentData()
        self.cfg["speed_limit"] = self.speed_cb.currentData()
        self.cfg["max_concurrent_downloads"] = self.conc_spin.value()
        self.cfg["theme"] = self.theme_cb.currentData()
        self.cfg["organize_by_group"] = self.org_cb.isChecked()
        for key in ("ytdlp_path", "ffmpeg_path", "deno_path"):
            self.cfg[key] = getattr(self, f"_{key}_edit").text().strip()
        save_config(self.cfg)
        self.configSaved.emit(dict(self.cfg))
        self.wantToast.emit("Configurações salvas!", "success")
        self._refresh_tools_status()

    def _refresh_tools_status(self):
        status = check_tools(self.cfg)
        parts = []
        for key, name in (("ytdlp_path", "yt-dlp"), ("ffmpeg_path", "FFmpeg"),
                          ("deno_path", "Deno")):
            s = status[key]
            parts.append(f"{'✔' if s['ok'] else '✖'} {name}")
        self.tools_lbl.setText("   ".join(parts))
        self.tools_lbl.setToolTip("\n".join(
            f"{k}: {v['path']}" for k, v in status.items()))

    def run_updater(self):
        if self._proc and self._proc.state() != QProcess.NotRunning:
            self.wantToast.emit("Atualização já em andamento.", "info")
            return
        from app.core import paths
        updater_script = os.path.join(APP_DIR, "atualizar.py")
        if paths.is_frozen() or not os.path.isfile(updater_script):
            # Modo empacotado: atualiza em thread com o módulo nativo.
            self._run_tools_updater_thread()
            return
        self.update_btn.setEnabled(False)
        self.upd_status.setText("Atualizando… (pode levar alguns minutos)")
        self.upd_log.clear()
        self._proc = QProcess(self)
        self._proc.setProgram(sys.executable)
        self._proc.setArguments([updater_script])
        self._proc.readyReadStandardOutput.connect(self._read_out)
        self._proc.finished.connect(self._update_finished)
        self._proc.start()

    def _run_tools_updater_thread(self):
        from PySide6.QtCore import QThread
        from app.core import tools_updater

        class _T(QThread):
            done = Signal(list)
            log_line = Signal(str)

            def run(self):
                self.done.emit(tools_updater.update_all(
                    log=self.log_line.emit))

        self.update_btn.setEnabled(False)
        self.upd_status.setText("Atualizando ferramentas…")
        self.upd_log.clear()
        self._thread = _T(self)
        self._thread.log_line.connect(self.upd_log.appendPlainText)
        self._thread.done.connect(self._tools_thread_done)
        self._thread.start()

    def _tools_thread_done(self, results):
        self.update_btn.setEnabled(True)
        ok = all(r.ok for r in results)
        for r in results:
            mark = "✔" if r.ok else "✖"
            self.upd_log.appendPlainText(f"{mark} {r.name}: {r.message}")
        self.upd_status.setText("Concluído ✔" if ok else "Concluído com falhas — veja o registro.")
        self.wantToast.emit(
            "Ferramentas atualizadas!" if ok else "Houve falhas na atualização.",
            "success" if ok else "warning")
        self._refresh_tools_status()

    # ── Atualização do aplicativo (Fase 6) ──────────────────────────────

    def check_app_update(self):
        from PySide6.QtCore import QThread
        from app.core import app_updater

        class _Check(QThread):
            done = Signal(object, str)

            def run(self):
                try:
                    manifest = app_updater.check_for_update()
                    self.done.emit(manifest, "")
                except Exception as exc:
                    self.done.emit(None, str(exc))

        self.app_update_btn.setEnabled(False)
        self.app_upd_status.setText("Verificando…")
        self._check_thread = _Check(self)
        self._check_thread.done.connect(self._app_update_checked)
        self._check_thread.start()

    def _app_update_checked(self, manifest, error):
        from app.core import app_updater
        self.app_update_btn.setEnabled(True)
        if manifest is None:
            self.app_upd_status.setText("Não foi possível verificar agora.")
            self.wantToast.emit(f"Verificação falhou: {error}", "warning")
            return
        if app_updater.is_newer(manifest.get("version", "0")):
            self.app_upd_status.setText(
                f"Nova versão {manifest['version']} disponível!")
            self.wantToast.emit(
                f"Nova versão {manifest['version']} disponível. "
                "Baixe o instalador no site oficial.", "info")
        else:
            self.app_upd_status.setText("Você já está na versão mais recente ✔")
            self.wantToast.emit("VibeCine está atualizado.", "success")

    def _read_out(self):
        if self._proc is None:
            return
        data = bytes(self._proc.readAllStandardOutput()).decode(
            "utf-8", errors="replace")
        if data:
            self.upd_log.appendPlainText(data.rstrip())

    def _update_finished(self, code, _status):
        self.update_btn.setEnabled(True)
        ok = code == 0
        self.upd_status.setText("Atualização concluída ✔" if ok
                                else "Atualização falhou — veja o registro acima.")
        self.wantToast.emit(
            "Ferramentas atualizadas!" if ok
            else "A atualização das ferramentas falhou.",
            "success" if ok else "error")
        self._refresh_tools_status()

    def shutdown(self):
        if self._proc and self._proc.state() != QProcess.NotRunning:
            self._proc.kill()
            self._proc.waitForFinished(2000)
