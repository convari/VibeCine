# -*- coding: utf-8 -*-
"""Página Histórico: registros de todos os downloads finalizados (SQLite).

Fase 5: filtros corretos, status coloridos, abrir arquivo/pasta,
excluir registro individual (sem confirmação — ação reversível fácil)
e limpeza total (com confirmação, pois é irreversível).
"""

from __future__ import annotations

import os
import subprocess
import sys

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QBrush, QColor
from PySide6.QtWidgets import (QComboBox, QFrame, QHBoxLayout, QHeaderView,
                               QLabel, QMessageBox, QPushButton,
                               QTableWidget, QTableWidgetItem, QVBoxLayout)

from app.core.history import HistoryStore
from app.ui import theme
from app.ui.pages.downloads import fmt_size

_STATUS_PT = {"concluido": "Concluído", "erro": "Erro", "cancelado": "Cancelado"}
_FILTERS = (("Todos", None), ("Concluídos", "concluido"),
            ("Com erro", "erro"), ("Cancelados", "cancelado"))


class HistoryPage(QFrame):
    wantToast = Signal(str, str)

    def __init__(self, history: HistoryStore, cfg: dict, parent=None):
        super().__init__(parent)
        self.history = history
        self.cfg = cfg
        self._rows: list[dict] = []
        self._build_ui()
        self.reload()

    def _build_ui(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 16, 20, 16)
        lay.setSpacing(12)

        top = QHBoxLayout()
        title = QLabel("Histórico")
        title.setObjectName("pageTitle")
        top.addWidget(title)
        top.addStretch(1)
        self.filter_cb = QComboBox()
        for lbl, val in _FILTERS:
            self.filter_cb.addItem(lbl, val)
        self.filter_cb.currentIndexChanged.connect(self.reload)
        top.addWidget(self.filter_cb)
        self.open_btn = QPushButton("📂 Abrir localização")
        self.open_btn.setToolTip("Abre a pasta do registro selecionado")
        self.open_btn.clicked.connect(self.open_location)
        top.addWidget(self.open_btn)
        self.del_btn = QPushButton("Excluir registro")
        self.del_btn.clicked.connect(self.delete_selected)
        top.addWidget(self.del_btn)
        self.clear_btn = QPushButton("Limpar tudo")
        self.clear_btn.setObjectName("danger")
        self.clear_btn.clicked.connect(self.clear_history)
        top.addWidget(self.clear_btn)
        lay.addLayout(top)

        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(
            ["Data", "Título", "Status", "Tamanho", "Pasta"])
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setAlternatingRowColors(True)
        lay.addWidget(self.table, 1)

        self.empty_lbl = QLabel("🕘 Nenhum registro no histórico ainda.\n"
                                "Os downloads concluídos aparecerão aqui.")
        self.empty_lbl.setObjectName("muted")
        self.empty_lbl.setAlignment(Qt.AlignCenter)
        lay.addWidget(self.empty_lbl)

    def reload(self):
        status = self.filter_cb.currentData()
        rows = self.history.list(status=status)
        self._rows = rows
        self.table.setRowCount(len(rows))
        self.empty_lbl.setVisible(not rows)
        self.table.setVisible(bool(rows))
        for i, r in enumerate(rows):
            status_txt = _STATUS_PT.get(r.get("status", ""), r.get("status", ""))
            values = [
                (r.get("finished_at", "") or "").replace("T", " "),
                r.get("title", ""),
                status_txt,
                fmt_size(r.get("size_bytes") or 0),
                r.get("out_dir", ""),
            ]
            for c, val in enumerate(values):
                item = QTableWidgetItem(val)
                if c == 2:
                    pal = theme.palette(theme.current())
                    item.setForeground(QBrush(QColor(
                        theme.status_color(pal, r.get("status", "")))))
                if c == 4:
                    item.setToolTip(r.get("output_path", "") or val)
                self.table.setItem(i, c, item)

    def open_location(self):
        idx = self.table.currentRow()
        if idx < 0 or idx >= len(self._rows):
            self.wantToast.emit("Selecione um registro primeiro.", "info")
            return
        r = self._rows[idx]
        path = r.get("output_path") or ""
        folder = path if os.path.isdir(path) else (
            os.path.dirname(path) if path else r.get("out_dir", ""))
        if not folder or not os.path.exists(folder):
            self.wantToast.emit("Pasta não encontrada (o arquivo pode ter sido movido).",
                                "warning")
            return
        if sys.platform == "win32":
            if path and os.path.isfile(path):
                subprocess.Popen(["explorer", "/select,", os.path.normpath(path)])
            else:
                os.startfile(folder)  # noqa: S606 - ação explícita do usuário
        else:
            subprocess.Popen(["xdg-open", folder])

    def delete_selected(self):
        idx = self.table.currentRow()
        if idx < 0 or idx >= len(self._rows):
            self.wantToast.emit("Selecione um registro para excluir.", "info")
            return
        r = self._rows[idx]
        if self.history.delete(r["id"]):
            self.reload()
            self.wantToast.emit("Registro excluído.", "info")

    def clear_history(self):
        resp = QMessageBox.question(
            self, "Limpar histórico",
            "Excluir TODOS os registros do histórico?\n"
            "Esta ação não pode ser desfeita.",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if resp != QMessageBox.Yes:
            return
        removed = self.history.clear()
        self.reload()
        self.wantToast.emit(f"Histórico limpo ({removed} registros).", "info")
