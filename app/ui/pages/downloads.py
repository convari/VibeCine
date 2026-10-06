# -*- coding: utf-8 -*-
"""Página Downloads: fila em tempo real alimentada pelo DownloadManager.

A UI NÃO recria lógica de download: apenas consome o DownloadManager do
núcleo (Fase 2) e reflete seu estado via sinais + polling leve (QTimer).
"""

from __future__ import annotations

import os
import subprocess
import sys

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (QFrame, QHBoxLayout, QLabel, QPushButton,
                               QProgressBar, QScrollArea, QVBoxLayout, QWidget)

from app.core.downloader import (DownloadJob, DownloadManager, JobStatus)
from app.core.history import HistoryStore
from app.ui import theme
from app.ui.widgets.empty_state import EmptyState


def fmt_size(nbytes: float) -> str:
    size = float(nbytes or 0)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if size < 1024 or unit == "TB":
            return f"{size:.1f} {unit}" if unit != "B" else f"{int(size)} B"
        size /= 1024
    return f"{size:.1f} TB"


class JobRow(QFrame):
    """Linha visual de um download individual."""

    pauseRequested = Signal(int)
    resumeRequested = Signal(int)
    cancelRequested = Signal(int)
    openRequested = Signal(int)
    retryRequested = Signal(int)

    def __init__(self, job_id: int, title: str, pal: dict, parent=None):
        super().__init__(parent)
        self.job_id = job_id
        self._pal = pal
        self.setObjectName("card")

        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 10, 14, 12)
        lay.setSpacing(6)

        top = QHBoxLayout()
        self.title_lbl = QLabel(title)
        self.title_lbl.setStyleSheet("font-weight: 600;")
        self.title_lbl.setToolTip(title)
        top.addWidget(self.title_lbl, 1)

        self.badge = QLabel("Aguardando")
        self.badge.setObjectName("badge")
        top.addWidget(self.badge)

        self.pause_btn = QPushButton("⏸")
        self.pause_btn.setFixedWidth(40)
        self.pause_btn.setToolTip("Pausar (mantém o progresso)")
        self.pause_btn.clicked.connect(lambda: self.pauseRequested.emit(self.job_id))
        top.addWidget(self.pause_btn)

        self.resume_btn = QPushButton("▶")
        self.resume_btn.setFixedWidth(40)
        self.resume_btn.setToolTip("Retomar")
        self.resume_btn.setVisible(False)
        self.resume_btn.clicked.connect(lambda: self.resumeRequested.emit(self.job_id))
        top.addWidget(self.resume_btn)

        self.cancel_btn = QPushButton("✖")
        self.cancel_btn.setFixedWidth(40)
        self.cancel_btn.setToolTip("Cancelar")
        self.cancel_btn.setObjectName("danger")
        self.cancel_btn.clicked.connect(lambda: self.cancelRequested.emit(self.job_id))
        top.addWidget(self.cancel_btn)

        self.retry_btn = QPushButton("↻")
        self.retry_btn.setFixedWidth(40)
        self.retry_btn.setToolTip("Tentar novamente")
        self.retry_btn.setVisible(False)
        self.retry_btn.clicked.connect(lambda: self.retryRequested.emit(self.job_id))
        top.addWidget(self.retry_btn)

        self.open_btn = QPushButton("📂")
        self.open_btn.setFixedWidth(40)
        self.open_btn.setToolTip("Abrir pasta do arquivo")
        self.open_btn.setVisible(False)
        self.open_btn.clicked.connect(lambda: self.openRequested.emit(self.job_id))
        top.addWidget(self.open_btn)
        lay.addLayout(top)

        self.prog = QProgressBar()
        self.prog.setRange(0, 100)
        lay.addWidget(self.prog)

        info = QHBoxLayout()
        self.pct_lbl = QLabel("0%")
        self.pct_lbl.setStyleSheet("font-weight: 700;")
        info.addWidget(self.pct_lbl)
        self.meta_lbl = QLabel("")
        self.meta_lbl.setObjectName("muted")
        info.addWidget(self.meta_lbl, 1)
        self.size_lbl = QLabel("")
        self.size_lbl.setObjectName("muted")
        info.addWidget(self.size_lbl)
        lay.addLayout(info)

        self.error_lbl = QLabel("")
        self.error_lbl.setObjectName("muted")
        self.error_lbl.setWordWrap(True)
        self.error_lbl.setStyleSheet(f"color: {pal['error']};")
        self.error_lbl.hide()
        lay.addWidget(self.error_lbl)

    def refresh(self, job: DownloadJob):
        pal = theme.palette(theme.current())
        st = job.status.value
        self.badge.setText(theme.status_label(st))
        self.badge.setStyleSheet(
            f"QLabel#badge {{ background: {theme.status_color(pal, st)}; }}")

        self.prog.setObjectName(
            {"concluido": "done", "erro": "error", "cancelado": "error",
             "pausado": "paused"}.get(st, ""))
        self.prog.style().unpolish(self.prog)
        self.prog.style().polish(self.prog)
        self.prog.setValue(int(job.percent))
        self.pct_lbl.setText(f"{job.percent:.0f}%")

        running = st in ("baixando", "aguardando")
        self.pause_btn.setVisible(st == "baixando")
        self.resume_btn.setVisible(st == "pausado")
        self.cancel_btn.setVisible(running or st == "pausado")
        self.retry_btn.setVisible(st in ("erro", "cancelado"))
        self.open_btn.setVisible(st == "concluido" and bool(job.output_path))

        meta = []
        if job.speed and st == "baixando":
            meta.append(job.speed)
        if job.eta and st == "baixando":
            meta.append(f"ETA {job.eta}")
        self.meta_lbl.setText("  •  ".join(meta))

        if job.total_bytes:
            self.size_lbl.setText(
                f"{fmt_size(job.downloaded_bytes)} / {fmt_size(job.total_bytes)}")
        else:
            self.size_lbl.setText("")

        if st == "erro" and job.error_message:
            self.error_lbl.setText(job.error_message)
            self.error_lbl.show()
        else:
            self.error_lbl.hide()


class DownloadsPage(QFrame):
    wantToast = Signal(str, str)
    historyChanged = Signal()

    def __init__(self, cfg: dict, history: HistoryStore, parent=None,
                 manager_factory=None):
        super().__init__(parent)
        self.cfg_ref = cfg
        self.history = history
        self._manager_factory = manager_factory
        self.manager: DownloadManager | None = None
        self.notifier = None  # injetado pela MainWindow (não intrusivo)
        self._rows: dict[int, JobRow] = {}
        self._recorded: set[int] = set()
        self._build_ui()

        self._timer = QTimer(self)
        self._timer.setInterval(250)
        self._timer.timeout.connect(self._poll)
        self._timer.start()

    # ── UI ───────────────────────────────────────────────────────────────

    def _build_ui(self):
        pal = theme.palette(self.cfg_ref.get("theme", "dark"))
        self._pal = pal
        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 16, 20, 16)
        lay.setSpacing(12)

        top = QHBoxLayout()
        title = QLabel("Downloads")
        title.setObjectName("pageTitle")
        top.addWidget(title)
        self.summary_lbl = QLabel("")
        self.summary_lbl.setObjectName("muted")
        top.addWidget(self.summary_lbl)
        top.addStretch(1)
        self.cancel_all_btn = QPushButton("Cancelar todos")
        self.cancel_all_btn.setObjectName("danger")
        self.cancel_all_btn.setEnabled(False)
        self.cancel_all_btn.clicked.connect(self.cancel_all)
        top.addWidget(self.cancel_all_btn)
        lay.addLayout(top)

        self.total_prog = QProgressBar()
        self.total_prog.setRange(0, 100)
        lay.addWidget(self.total_prog)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.rows_widget = QWidget()
        self.rows_lay = QVBoxLayout(self.rows_widget)
        self.rows_lay.setContentsMargins(0, 0, 6, 0)
        self.rows_lay.setSpacing(10)
        self.rows_lay.addStretch(1)
        scroll.setWidget(self.rows_widget)
        lay.addWidget(scroll, 1)

        self.empty = EmptyState(
            "⬇", "Nenhum download na fila",
            "Selecione conteúdos na Biblioteca e clique em "
            "\"Baixar selecionados\".")
        lay.addWidget(self.empty)
        scroll.hide()

        self._scroll = scroll

    # ── Integração com o núcleo ─────────────────────────────────────────

    def _create_manager(self) -> DownloadManager:
        if self._manager_factory is not None:
            return self._manager_factory(self.cfg_ref)
        return DownloadManager(
            self.cfg_ref,
            max_workers=int(self.cfg_ref.get("max_concurrent_downloads", 2)),
            on_log=lambda m: None,  # log detalhado permanece no console/núcleo
        )

    def enqueue(self, entries: list[dict]):
        if not entries:
            return
        if self.manager is None:
            self.manager = self._create_manager()
            self.manager.start(entries)
        else:
            self.manager.add(entries)
        self.empty.hide()
        self._scroll.show()
        self.wantToast.emit(f"{len(entries)} item(ns) adicionados à fila.",
                            "success")

    def cancel_all(self):
        if self.manager is not None:
            self.manager.cancel_all()
            self.wantToast.emit("Cancelando todos os downloads…", "warning")

    # ── Atualização periódica ────────────────────────────────────────────

    def _poll(self):
        if self.manager is None or not self.manager.jobs:
            return
        m = self.manager
        active = any(j.status in (JobStatus.RUNNING, JobStatus.PENDING)
                     for j in m.jobs)
        self.cancel_all_btn.setEnabled(active)

        for job in m.jobs:
            row = self._rows.get(job.id)
            if row is None:
                row = JobRow(job.id, job.title, self._pal)
                row.pauseRequested.connect(self._pause)
                row.resumeRequested.connect(self._resume)
                row.cancelRequested.connect(self._cancel)
                row.openRequested.connect(self._open_location)
                row.retryRequested.connect(self._retry)
                self._rows[job.id] = row
                self.rows_lay.insertWidget(self.rows_lay.count() - 1, row)
            row.refresh(job)

            if job.status in (JobStatus.DONE, JobStatus.FAILED,
                              JobStatus.CANCELLED) and job.id not in self._recorded:
                self._recorded.add(job.id)
                self._record_history(job)
                # Notificação NÃO intrusiva: nunca rouba o foco.
                if job.status is JobStatus.DONE:
                    self._notify("Download concluído", job.title, "success")
                elif job.status is JobStatus.FAILED:
                    self._notify("Download falhou", job.title, "error")

        if m.jobs:
            done = sum(1 for j in m.jobs if j.status is JobStatus.DONE)
            total = len(m.jobs)
            overall = sum(100.0 if j.status is JobStatus.DONE else j.percent
                          for j in m.jobs) / total
            self.total_prog.setValue(int(overall))
            self.summary_lbl.setText(f"{done}/{total} concluídos")

    def _notify(self, title: str, message: str, kind: str):
        """Conclusão: Notifier decide (toast in-app focado / bandeja se background)."""
        if self.notifier is not None:
            self.notifier.notify(title, message, kind)
        else:
            self.wantToast.emit(f"{title}: {message}", kind)

    def _record_history(self, job: DownloadJob):
        try:
            size = 0
            if job.output_path and os.path.isfile(job.output_path):
                size = os.path.getsize(job.output_path)
            self.history.add(
                title=job.title,
                group=job.entry.get("group", ""),
                url=job.entry.get("url", ""),
                status=job.status.value,
                out_dir=self.cfg_ref.get("download_folder", ""),
                output_path=job.output_path,
                size_bytes=size,
                error=job.error_message,
            )
            self.historyChanged.emit()
        except Exception:
            pass  # histórico nunca deve quebrar o fluxo de download

    # ── Controles por item ───────────────────────────────────────────────

    def _pause(self, job_id: int):
        if self.manager:
            self.manager.pause_job(job_id)

    def _resume(self, job_id: int):
        if self.manager:
            self.manager.resume_job(job_id)

    def _cancel(self, job_id: int):
        if self.manager:
            self.manager.cancel_job(job_id)

    def _job(self, job_id: int):
        if self.manager is None:
            return None
        return next((j for j in self.manager.jobs if j.id == job_id), None)

    def _retry(self, job_id: int):
        job = self._job(job_id)
        if job is None or self.manager is None:
            return
        new_jobs = self.manager.add([dict(job.entry)])
        self._recorded.add(job_id)  # garante 1 registro por tentativa
        for nj in new_jobs:
            self._recorded.discard(nj.id)
        row = self._rows.pop(job_id, None)
        if row is not None:
            row.setParent(None)
            row.deleteLater()
        self.wantToast.emit(f"Tentando novamente: {job.title}", "info")

    def _open_location(self, job_id: int):
        job = self._job(job_id)
        path = (job.output_path if job else "") or ""
        folder = os.path.dirname(path) if path else self.cfg_ref.get(
            "download_folder", "")
        if not folder or not os.path.exists(folder):
            self.wantToast.emit("Pasta não encontrada.", "warning")
            return
        if sys.platform == "win32":
            if path and os.path.isfile(path):
                subprocess.Popen(["explorer", "/select,", os.path.normpath(path)])
            else:
                os.startfile(folder)  # noqa: S606 - ação explícita do usuário
        else:
            subprocess.Popen(["xdg-open", folder])

    def has_active(self) -> bool:
        return (self.manager is not None
                and any(j.status in (JobStatus.RUNNING, JobStatus.PENDING)
                        for j in self.manager.jobs))

    def shutdown(self):
        self._timer.stop()
        if self.manager is not None:
            self.manager.shutdown(wait_timeout=8)
