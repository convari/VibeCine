# -*- coding: utf-8 -*-
"""Estado vazio: orientação amigável quando não há conteúdo."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QVBoxLayout


class EmptyState(QFrame):
    def __init__(self, icon: str, title: str, subtitle: str = "",
                 parent=None, action_button=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setAlignment(Qt.AlignCenter)
        lay.setSpacing(8)

        ic = QLabel(icon)
        ic.setObjectName("emptyIcon")
        ic.setAlignment(Qt.AlignCenter)
        lay.addWidget(ic)

        t = QLabel(title)
        t.setAlignment(Qt.AlignCenter)
        t.setStyleSheet("font-size: 15px; font-weight: 600;")
        lay.addWidget(t)

        if subtitle:
            s = QLabel(subtitle)
            s.setObjectName("muted")
            s.setAlignment(Qt.AlignCenter)
            s.setWordWrap(True)
            lay.addWidget(s)

        if action_button is not None:
            row = QHBoxLayout()
            row.addStretch(1)
            row.addWidget(action_button)
            row.addStretch(1)
            lay.addLayout(row)
