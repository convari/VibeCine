# -*- coding: utf-8 -*-
"""Toasts: notificações não-bloqueantes que substituem messageboxes."""

from __future__ import annotations

from PySide6.QtCore import (QEasingCurve, QEvent, QObject, QPropertyAnimation,
                            Qt, QTimer)
from PySide6.QtWidgets import QFrame, QGraphicsOpacityEffect, QHBoxLayout, QLabel

_KIND_COLOR = {
    "info": "#4A9EFF",
    "success": "#2F9E63",
    "warning": "#C77F0A",
    "error": "#C93C3C",
}
_KIND_ICON = {"info": "ℹ", "success": "✔", "warning": "⚠", "error": "✖"}


class Toast(QFrame):
    def __init__(self, text: str, kind: str, parent):
        super().__init__(parent, Qt.ToolTip | Qt.FramelessWindowHint)
        self.setObjectName("toast")
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.setStyleSheet(
            f"QFrame#toast {{ background: {_KIND_COLOR.get(kind, _KIND_COLOR['info'])};"
            " border-radius: 10px; }")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(14, 10, 14, 10)
        lbl = QLabel(f"{_KIND_ICON.get(kind, 'ℹ')}  {text}")
        lbl.setObjectName("toastText")
        lbl.setStyleSheet("color: white; font-weight: 600;")
        lay.addWidget(lbl)
        self.adjustSize()

        self._opacity = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self._opacity)

    def show_and_fade(self, duration_ms: int = 3500):
        self.show()
        anim = QPropertyAnimation(self._opacity, b"opacity", self)
        anim.setDuration(220)
        anim.setStartValue(0.0)
        anim.setEndValue(1.0)
        anim.setEasingCurve(QEasingCurve.OutCubic)
        anim.start()
        self._anim = anim
        QTimer.singleShot(duration_ms, self._fade_out)

    def _fade_out(self):
        anim = QPropertyAnimation(self._opacity, b"opacity", self)
        anim.setDuration(300)
        anim.setStartValue(1.0)
        anim.setEndValue(0.0)
        anim.finished.connect(self.deleteLater)
        anim.start()
        self._anim = anim


class ToastManager(QObject):
    """Exibe toasts empilhados no canto inferior direito da janela."""

    def __init__(self, parent_widget):
        super().__init__(parent_widget)
        self._parent = parent_widget
        self._active: list[Toast] = []
        self._parent.installEventFilter(self)

    def eventFilter(self, obj, event):
        if obj is self._parent and event.type() == QEvent.Resize:
            self._reposition()
        return False

    def show(self, text: str, kind: str = "info", duration_ms: int = 3500) -> Toast:
        toast = Toast(text, kind, self._parent)
        self._active.append(toast)
        self._reposition()
        toast.destroyed.connect(
            lambda: self._active.remove(toast) if toast in self._active else None)
        toast.show_and_fade(duration_ms)
        return toast

    # Atalhos semânticos
    def info(self, text, **kw): return self.show(text, "info", **kw)
    def success(self, text, **kw): return self.show(text, "success", **kw)
    def warning(self, text, **kw): return self.show(text, "warning", **kw)
    def error(self, text, **kw): return self.show(text, "error", **kw)

    def _reposition(self):
        margin, gap = 18, 8
        y = self._parent.height() - margin
        for toast in reversed(self._active):
            y -= toast.height()
            x = self._parent.width() - toast.width() - margin
            toast.move(max(x, margin), max(y, margin))
            y -= gap
