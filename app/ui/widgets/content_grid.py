# -*- coding: utf-8 -*-
"""Grid de conteúdo virtualizado (referência visual VibeCine).

- QListView em modo ícone + delegate custom: capa grande, título,
  subtítulo (tipo/grupo), hover com glow, seleção com borda/glow vermelha
  e badge ✓ no canto.
- Virtualização nativa: widgets apenas para células visíveis.
- Capas via CoverPool (fila limitada, 3 workers, cache LRU da página).
- Seleção: clique alterna; arraste por rubber band marca em lote;
  compatível com a API da tabela (rowCount/checked_count/checked_rows).
"""

from __future__ import annotations

from PySide6.QtCore import QModelIndex, QRect, QSize, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QMouseEvent, QPainter, QPainterPath, QPixmap
from PySide6.QtWidgets import QListView, QStyle, QStyledItemDelegate, QStyleOptionViewItem

from app.ui import theme

CARD_W, CARD_H = 188, 262
COVER_H = 200


class ContentCardDelegate(QStyledItemDelegate):
    """Pinta o card do grid (capa + textos + estado de seleção)."""

    def __init__(self, view):
        super().__init__(view)
        self.view = view

    def sizeHint(self, option, index):
        return QSize(CARD_W, CARD_H)

    def paint(self, p: QPainter, option: QStyleOptionViewItem, index: QModelIndex):
        entry = index.data(Qt.UserRole) or {}
        checked = bool(index.data(Qt.UserRole + 1))
        hovered = bool(option.state & QStyle.State_MouseOver)
        pal = theme.palette(theme.current())

        r = option.rect.adjusted(6, 6, -6, -6)
        p.save()
        p.setRenderHint(QPainter.Antialiasing)

        # Fundo do card
        bg = QPainterPath()
        bg.addRoundedRect(r, 12, 12)
        p.fillPath(bg, QColor(pal["card"]))

        # Hover: leve elevação + glow vermelho
        if hovered:
            glow = QPainterPath()
            glow.addRoundedRect(r.adjusted(-2, -2, 2, 2), 14, 14)
            p.fillPath(glow, QColor(pal["glow"]))

        # Seleção: borda vermelha + fundo suave
        if checked:
            sel = QPainterPath()
            sel.addRoundedRect(r, 12, 12)
            p.fillPath(sel, QColor(pal["accent_soft"]))
            pen = p.pen()
            pen.setColor(QColor(pal["accent"]))
            pen.setWidthF(2.0)
            p.setPen(pen)
            p.drawRoundedRect(r, 12, 12)
            p.setPen(Qt.NoPen)

        # Capa (lazy: buscada sob demanda)
        cover_rect = QRect(r.left(), r.top(), r.width(), min(COVER_H, r.height() - 56))
        logo_url = entry.get("logo", "")
        pix = self.view.cover_for(logo_url, index.row()) if logo_url else None
        cover_clip = QPainterPath()
        cover_clip.addRoundedRect(QRect(r.left(), r.top(), r.width(),
                                        cover_rect.height()), 12, 12)
        p.setClipPath(cover_clip)
        if pix and not pix.isNull():
            p.drawPixmap(cover_rect, pix)
        else:
            # placeholder escuro com marquinha
            p.fillRect(cover_rect, QColor(pal["input_bg"]))
            from app.ui.resources.icons import logo_pixmap
            small = logo_pixmap(min(56, cover_rect.width() - 20))
            px = small.scaled(56, 56, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            p.drawPixmap(cover_rect.center().x() - px.width() // 2,
                         cover_rect.center().y() - px.height() // 2, px)

        p.setClipping(False)

        # Textos
        font = p.font()
        font.setBold(True)
        p.setFont(font)
        title_rect = QRect(r.left() + 8, r.top() + cover_rect.height() + 6,
                           r.width() - 16, 34)
        metrics = p.fontMetrics()
        title = metrics.elidedText(entry.get("title", ""), Qt.ElideRight,
                                   title_rect.width())
        p.setPen(QColor(pal["text"]))
        p.drawText(title_rect, Qt.AlignLeft | Qt.AlignTop, title)

        font.setBold(False)
        font.setPointSizeF(max(8.0, font.pointSizeF() - 1.5))
        p.setFont(font)
        meta = f"{theme.type_label(entry.get('type',''))} • {entry.get('group','')}"
        meta = metrics.elidedText(meta, Qt.ElideRight, r.width() - 16)
        p.setPen(QColor(pal["text_dim"]))
        p.drawText(QRect(r.left() + 8,
                         r.top() + cover_rect.height() + 6 + metrics.height() + 2,
                         r.width() - 16, 20),
                   Qt.AlignLeft | Qt.AlignTop, meta)

        # Badge ✓ selecionado (canto superior direito do card)
        if checked:
            badge = QRect(r.right() - 26, r.top() + 8, 20, 20)
            p.setBrush(QColor(pal["accent"]))
            p.setPen(Qt.NoPen)
            p.drawEllipse(badge)
            p.setPen(QColor(pal["on_accent"]))
            p.drawText(badge, Qt.AlignCenter, "✓")

        p.restore()


class ContentGridView(QListView):
    """Grid virtualizado de capas com seleção por clique/arraste."""

    selectionChanged = Signal(int)
    detailRequested = Signal(int)

    def __init__(self, model, cover_pool, parent=None):
        super().__init__(parent)
        self._model = model
        self._pool = cover_pool
        self._cache: dict[str, QPixmap] = {}
        self._requested: set[int] = set()
        self.setModel(model)
        self.setModelColumn(2)  # Título
        self.setViewMode(QListView.IconMode)
        self.setResizeMode(QListView.Adjust)
        self.setUniformItemSizes(True)
        self.setGridSize(QSize(CARD_W, CARD_H))
        self.setSpacing(4)
        self.setWrapping(True)
        self.setSelectionMode(QListView.ExtendedSelection)
        self.setItemDelegate(ContentCardDelegate(self))
        self.setMouseTracking(True)
        cover_pool.ready.connect(self._on_cover_ready)
        self._cover_pool = cover_pool
        # Rubber band manual (QListView não tem RubberBandDrag nativo)
        self._rb_origin = None
        self._rubber = None

    # ── Capas (lazy; pool limitado) ──────────────────────────────────────

    def cover_for(self, url: str, row: int) -> QPixmap | None:
        pix = self._cache.get(url)
        if pix is not None:
            return pix
        if row not in self._requested:
            self._requested.add(row)
            self._pool.request(url)
        return None

    def _on_cover_ready(self, url: str, image):
        from PySide6.QtGui import QPixmap
        pix = QPixmap.fromImage(image).scaled(
            CARD_W - 12, COVER_H, Qt.KeepAspectRatioByExpanding,
            Qt.SmoothTransformation)
        self._cache[url] = pix
        if len(self._cache) > 128:  # LRU simples: descarta os mais antigos
            for k in list(self._cache)[:32]:
                del self._cache[k]
        # repinta células que usam essa URL (barato: a view só pede visíveis)
        self.viewport().update()

    # ── Interação ────────────────────────────────────────────────────────

    def mousePressEvent(self, e: QMouseEvent):
        if e.button() == Qt.LeftButton:
            idx = self.indexAt(e.position().toPoint())
            if idx.isValid():
                self._model.set_checked(idx.row(), not self._model.is_checked(idx.row()))
                self.detailRequested.emit(idx.row())
                self.selectionChanged.emit(len(self._model.checked_rows()))
                self._rb_origin = None
            else:
                # começou no vazio → rubber band de marcação
                from PySide6.QtWidgets import QRubberBand
                self._rb_origin = e.position().toPoint()
                if self._rubber is None:
                    self._rubber = QRubberBand(QRubberBand.Rectangle,
                                               self.viewport())
                self._rubber.setGeometry(self._rb_origin.x(),
                                         self._rb_origin.y(), 1, 1)
                self._rubber.show()
        super().mousePressEvent(e)

    def mouseMoveEvent(self, e: QMouseEvent):
        if self._rb_origin is not None and self._rubber is not None:
            cur = e.position().toPoint()
            rect = QRect(self._rb_origin, cur).normalized()
            self._rubber.setGeometry(rect)
        super().mouseMoveEvent(e)

    def mouseReleaseEvent(self, e: QMouseEvent):
        if self._rb_origin is not None and self._rubber is not None:
            rect = QRect(self._rb_origin,
                         e.position().toPoint()).normalized()
            self._rubber.hide()
            self._rubber = None
            marked = 0
            pal = theme.palette(theme.current())
            for row in range(self._model.rowCount()):
                idx = self._model.index(row, 0)
                if rect.intersects(self.visualRect(idx)):
                    if not self._model.is_checked(row):
                        self._model.set_checked(row, True)
                        marked += 1
            if marked:
                self.selectionChanged.emit(len(self._model.checked_rows()))
            self._rb_origin = None
        super().mouseReleaseEvent(e)

    # ── API compatível com a tabela (testes/página) ──────────────────────

    def rowCount(self) -> int:
        return self._model.rowCount()

    def checked_count(self) -> int:
        return len(self._model.checked_rows())

    def checked_rows(self) -> list[int]:
        return self._model.checked_rows()

    def set_checked_range(self, rows, checked: bool):
        for r in rows:
            if 0 <= r < self.rowCount():
                self._model.set_checked(r, checked)
        self.selectionChanged.emit(self.checked_count())
