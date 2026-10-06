# -*- coding: utf-8 -*-
"""Diálogo de compartilhamento moderno (WhatsApp, Telegram, Facebook, X,
e-mail, copiar link e QR Code)."""

from __future__ import annotations

import webbrowser

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (QDialog, QFrame, QHBoxLayout, QLabel,
                               QPushButton, QVBoxLayout, QFileDialog)

from app.core import share
from app.ui import theme


class ShareDialog(QDialog):
    """Compartilha uma entrada respeitando as regras de segurança."""

    wantToast = Signal(str, str)

    def __init__(self, entry: dict, parent=None):
        super().__init__(parent)
        self.entry = entry
        self.plan = share.plan_share(entry)
        self.setWindowTitle("Compartilhar — VibeCine")
        self.setMinimumWidth(380)
        self.setModal(True)
        self._qr_bytes: bytes | None = None
        self._build_ui()

    # ── UI ───────────────────────────────────────────────────────────────

    def _build_ui(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 18, 20, 18)
        lay.setSpacing(12)

        title = QLabel("Compartilhar")
        title.setStyleSheet("font-size: 16px; font-weight: 700;")
        lay.addWidget(title)

        pal = theme.palette(theme.current())
        item = QLabel(f"<b>{self.entry.get('title','')}</b><br>"
                      f"<span style='color:{pal['text_dim']}'>"
                      f"{theme.type_label(self.entry.get('type',''))}</span>")
        item.setWordWrap(True)
        lay.addWidget(item)

        if not self.plan.shareable:
            # URL sensível: explica o bloqueio e oferece apenas a referência.
            box = QFrame()
            box.setObjectName("card")
            bv = QVBoxLayout(box)
            bv.setContentsMargins(14, 12, 14, 12)
            warn = QLabel("🔒 " + self.plan.reason)
            warn.setWordWrap(True)
            bv.addWidget(warn)
            if self.plan.safe_reference:
                bv.addWidget(QLabel("Referência segura (sem credenciais):"))
                ref = QLabel(self.plan.safe_reference)
                ref.setObjectName("muted")
                ref.setWordWrap(True)
                ref.setTextInteractionFlags(Qt.TextSelectableByMouse)
                bv.addWidget(ref)
                btn = QPushButton("📋 Copiar referência segura")
                btn.clicked.connect(self._copy_safe_reference)
                bv.addWidget(btn, alignment=Qt.AlignLeft)
            lay.addWidget(box)
            close = QPushButton("Fechar")
            close.setObjectName("primary")
            close.clicked.connect(self.accept)
            lay.addWidget(close, alignment=Qt.AlignRight)
            return

        message = share.build_share_message(self.entry, self.plan.url)

        # Prévia da mensagem
        prev = QFrame()
        prev.setObjectName("card")
        pv = QVBoxLayout(prev)
        pv.setContentsMargins(14, 10, 14, 10)
        msg = QLabel(message)
        msg.setObjectName("muted")
        msg.setWordWrap(True)
        msg.setTextInteractionFlags(Qt.TextSelectableByMouse)
        pv.addWidget(msg)
        lay.addWidget(prev)

        # Redes
        links = share.build_share_links(message, self.plan.url)
        grid = QHBoxLayout()
        networks = [("whatsapp", "WhatsApp", "#25D366"),
                    ("telegram", "Telegram", "#229ED9"),
                    ("facebook", "Facebook", "#1877F2"),
                    ("x", "X", "#111111")]
        for key, label, color in networks:
            b = QPushButton(label)
            b.setStyleSheet(f"QPushButton {{ border-color: {color}; }}"
                            f"QPushButton:hover {{ background: {color}; color: white; }}")
            b.clicked.connect(lambda _c=False, k=key: self._open(links[k]))
            grid.addWidget(b)
        lay.addLayout(grid)

        row2 = QHBoxLayout()
        mail = QPushButton("✉ E-mail")
        mail.clicked.connect(lambda: self._open(links["email"]))
        row2.addWidget(mail)
        copy_btn = QPushButton("📋 Copiar link")
        copy_btn.clicked.connect(self._copy_link)
        row2.addWidget(copy_btn)
        qr_btn = QPushButton("▦ Gerar QR Code")
        qr_btn.clicked.connect(self._show_qr)
        row2.addWidget(qr_btn)
        lay.addLayout(row2)

        # Área do QR (aparece sob demanda)
        self.qr_area = QFrame()
        self.qr_area.setObjectName("card")
        qv = QVBoxLayout(self.qr_area)
        qv.setContentsMargins(14, 12, 14, 12)
        qv.setAlignment(Qt.AlignCenter)
        self.qr_lbl = QLabel()
        self.qr_lbl.setAlignment(Qt.AlignCenter)
        qv.addWidget(self.qr_lbl)
        save_btn = QPushButton("💾 Salvar QR Code (PNG)")
        save_btn.clicked.connect(self._save_qr)
        qv.addWidget(save_btn, alignment=Qt.AlignCenter)
        self.qr_area.hide()
        self._qr_area_widget = self.qr_area
        self._save_qr_btn = save_btn
        lay.addWidget(self.qr_area)

    # ── Ações ────────────────────────────────────────────────────────────

    def _open(self, url: str):
        webbrowser.open(url)
        self.wantToast.emit("Abrindo compartilhamento no navegador…", "info")

    def _copy(self, text: str, feedback: str):
        from PySide6.QtWidgets import QApplication
        QApplication.clipboard().setText(text)
        self.wantToast.emit(feedback, "success")

    def _copy_link(self):
        self._copy(self.plan.url, "Link copiado!")

    def _copy_safe_reference(self):
        self._copy(self.plan.safe_reference, "Referência copiada (sem credenciais).")

    def _show_qr(self):
        if self._qr_bytes is None:
            self._qr_bytes = share.make_qr_png_bytes(self.plan.url)
        pix = QPixmap()
        pix.loadFromData(self._qr_bytes)
        self.qr_lbl.setPixmap(pix.scaled(220, 220, Qt.KeepAspectRatio,
                                         Qt.SmoothTransformation))
        self.qr_area.setVisible(True)
        self.adjustSize()

    def _save_qr(self):
        if not self._qr_bytes:
            return
        name = f"qrcode_{self.entry.get('title','vibcine')[:30]}.png"
        path, _ = QFileDialog.getSaveFileName(
            self, "Salvar QR Code", name, "Imagem PNG (*.png)")
        if path:
            with open(path, "wb") as fh:
                fh.write(self._qr_bytes)
            self.wantToast.emit("QR Code salvo!", "success")
