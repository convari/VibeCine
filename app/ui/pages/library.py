# -*- coding: utf-8 -*-
"""Página Biblioteca — VIRTUALIZADA (QAbstractTableModel + QTableView).

Antes: um QTableWidgetItem×3 por item (10k itens = 30k objetos + batches
no event loop → CPU 100% por minutos).
Agora: um modelo de dados leve; a view cria widgets apenas para as células
visíveis (virtualização nativa do Qt). O número de componentes visuais é
constante, para 500 ou 100.000 itens.

Preservado: filtros (busca/grupo/tipo), seleção por checkbox e ARRASTE,
todos/nenhum/inverter, detalhes com capa sob demanda (cache LRU), capas
NUNCA carregadas em massa (só o item em visualização), parse incremental
em lotes de 200 (worker em background), erros amigáveis.
"""

from __future__ import annotations

from collections import OrderedDict

from PySide6.QtCore import (QAbstractTableModel, QModelIndex, Qt, QTimer,
                            Signal)
from PySide6.QtGui import QBrush, QColor, QMouseEvent, QPixmap
from PySide6.QtWidgets import (QComboBox, QFrame, QHBoxLayout, QHeaderView,
                               QLabel, QLineEdit, QPushButton, QProgressBar,
                               QStackedWidget, QTableView, QVBoxLayout)

from app.core.url_router import UrlKind, classify_url, validate_url
from app.core.downloader import redact_url
from app.core import share
from app.core.share import is_sensitive_url
from app.ui import theme
from app.ui.widgets.content_grid import ContentGridView
from app.ui.workers import (CoverFetcher, CoverPool, ExtractWorker,
                            PlaylistBatchWorker)

_COVER_CACHE_MAX = 32          # capas em memória (LRU)
_SEARCH_DEBOUNCE_MS = 250      # debounce da busca
_LOAD_BATCH = 200              # itens por lote vindo do parser


class LibraryModel(QAbstractTableModel):
    """Modelo leve: nenhum widget por linha; apenas referências às entradas."""

    HEADERS = ("✓", "Tipo", "Título")

    def __init__(self, parent=None):
        super().__init__(parent)
        self._all: list[dict] = []
        self._filtered: list[dict] = []
        self._checks: list[bool] = []
        self._filter = ("", "Todos", "Todos")  # (busca, grupo, tipo)
        self._loading = False

    # ── Dados ────────────────────────────────────────────────────────────

    def set_entries(self, entries: list[dict]):
        self.beginResetModel()
        self._all = list(entries)
        self._filtered = []
        self._checks = []
        self._loading = False
        self._refilter()
        self.endResetModel()

    def begin_loading(self):
        self.beginResetModel()
        self._all = []
        self._filtered = []
        self._checks = []
        self._loading = True
        self.endResetModel()

    def append_entries(self, batch: list[dict]):
        """Insere um lote — apenas os que passam pelo filtro atual."""
        self._all.extend(batch)
        s, g, t = self._filter
        new = [e for e in batch if self._match(e, s, g, t)]
        if not new:
            return
        start = len(self._filtered)
        self.beginInsertRows(QModelIndex(), start, start + len(new) - 1)
        self._filtered.extend(new)
        self._checks.extend([False] * len(new))
        self.endInsertRows()

    @staticmethod
    def _match(e, s, g, t):
        return ((not s or s in e["title"].lower())
                and (g == "Todos" or e["group"] == g)
                and (t == "Todos" or e["type"] == t))

    def _refilter(self):
        s, g, t = self._filter
        self._filtered = [e for e in self._all if self._match(e, s, g, t)]
        self._checks = [False] * len(self._filtered)

    def set_filter(self, search: str, group: str, kind: str):
        self.beginResetModel()
        self._filter = (search.lower().strip(), group, kind)
        self._refilter()
        self.endResetModel()

    # ── Qt model ─────────────────────────────────────────────────────────

    def rowCount(self, parent=QModelIndex()) -> int:
        return len(self._filtered)

    def columnCount(self, parent=QModelIndex()) -> int:
        return 3

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if role == Qt.DisplayRole and orientation == Qt.Horizontal:
            return self.HEADERS[section]
        return None

    def flags(self, index):
        if not index.isValid():
            return Qt.NoItemFlags
        return Qt.ItemIsEnabled

    def entry_at(self, row: int) -> dict:
        return self._filtered[row]

    def is_checked(self, row: int) -> bool:
        return self._checks[row]

    def set_checked(self, row: int, value: bool):
        self._checks[row] = bool(value)
        self.dataChanged.emit(self.index(row, 0), self.index(row, 0))

    def set_checked_all(self, value: bool):
        self._checks = [bool(value)] * len(self._checks)
        if self._checks:
            self.dataChanged.emit(self.index(0, 0),
                                  self.index(len(self._checks) - 1, 0))

    def invert_checked(self):
        self._checks = [not c for c in self._checks]
        if self._checks:
            self.dataChanged.emit(self.index(0, 0),
                                  self.index(len(self._checks) - 1, 0))

    def checked_rows(self) -> list[int]:
        return [i for i, c in enumerate(self._checks) if c]

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid():
            return None
        row, col = index.row(), index.column()
        e = self._filtered[row]

        if role == Qt.DisplayRole:
            if col == 0:
                return "☑" if self._checks[row] else "☐"
            if col == 1:
                return theme.type_label(e["type"])
            return e["title"]
        if role == Qt.ForegroundRole:
            if col == 1:
                return QBrush(QColor(theme.type_color(e["type"])))
            if self._checks[row]:
                return QBrush(QColor(theme.palette(theme.current())["accent"]))
            return None
        if role == Qt.BackgroundRole and self._checks[row]:
            return QBrush(QColor(124, 92, 255, 42))
        if role == Qt.ToolTipRole:
            shown = (redact_url(e["url"]) if is_sensitive_url(e["url"])
                     else e["url"])
            return shown
        if role == Qt.UserRole:
            return e  # entrada completa (delegate do grid)
        if role == Qt.UserRole + 1:
            return bool(self._checks[row])  # estado de seleção (delegate)
        return None


class LibraryView(QTableView):
    """Virtualizada + seleção por arraste (marca/desmarca ao arrastar)."""

    selectionChanged = Signal(int)
    detailRequested = Signal(int)

    def __init__(self, model: LibraryModel, parent=None):
        super().__init__(parent)
        self._model = model
        self.setModel(model)
        self._drag_check = True
        self._dragging = False
        self._drag_seen: set[int] = set()
        self.verticalHeader().setVisible(False)
        self.verticalHeader().setDefaultSectionSize(30)
        self.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.horizontalHeader().setSectionsClickable(False)
        self.setColumnWidth(0, 36)
        self.setColumnWidth(1, 90)
        self.setSelectionBehavior(QTableView.SelectRows)
        self.setSelectionMode(QTableView.NoSelection)
        self.setShowGrid(False)
        self.setEditTriggers(QTableView.NoEditTriggers)

    # Drag-select (equivalente ao Tkinter original)
    def mousePressEvent(self, e: QMouseEvent):
        if e.button() == Qt.LeftButton:
            idx = self.indexAt(e.position().toPoint())
            if idx.isValid():
                row = idx.row()
                self._drag_check = not self._model.is_checked(row)
                self._dragging = True
                self._drag_seen = set()
                self._apply_drag(row)
        super().mousePressEvent(e)

    def mouseMoveEvent(self, e: QMouseEvent):
        if self._dragging:
            idx = self.indexAt(e.position().toPoint())
            if idx.isValid():
                self._apply_drag(idx.row())
        super().mouseMoveEvent(e)

    def mouseReleaseEvent(self, e: QMouseEvent):
        self._dragging = False
        super().mouseReleaseEvent(e)

    def _apply_drag(self, row: int):
        if row in self._drag_seen:
            return
        self._drag_seen.add(row)
        self._model.set_checked(row, self._drag_check)
        self.detailRequested.emit(row)
        self.selectionChanged.emit(len(self._model.checked_rows()))

    # API de compatibilidade (usada pela página e pelos testes)
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


class LibraryPage(QFrame):
    entriesSelected = Signal(list)
    wantToast = Signal(str, str)

    def __init__(self, cfg: dict, parent=None):
        super().__init__(parent)
        self.cfg = cfg
        self.entries: list[dict] = []
        self.filtered: list[dict] = []  # compat: expõe o filtered do modelo
        self._current_entry: dict | None = None
        self._worker = None  # ExtractWorker | PlaylistBatchWorker
        self._cover_worker: CoverFetcher | None = None
        self._cover_pixmap: QPixmap | None = None
        self._cover_cache: OrderedDict = OrderedDict()  # LRU
        self._filter_timer = QTimer(self)
        self._filter_timer.setSingleShot(True)
        self._filter_timer.setInterval(_SEARCH_DEBOUNCE_MS)
        self._filter_timer.timeout.connect(self._apply_filters_now)
        self._build_ui()

    # ── UI ───────────────────────────────────────────────────────────────

    def _build_ui(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 16, 20, 16)
        lay.setSpacing(12)

        title = QLabel("Biblioteca")
        title.setObjectName("pageTitle")
        lay.addWidget(title)

        url_card = QFrame()
        url_card.setObjectName("card")
        uc = QVBoxLayout(url_card)
        uc.setContentsMargins(14, 12, 14, 12)
        row = QHBoxLayout()
        self.url_edit = QLineEdit()
        self.url_edit.setPlaceholderText(
            "Cole a URL de uma lista M3U, canal/playlist do YouTube ou link de vídeo…")
        self.url_edit.returnPressed.connect(self.load_url)
        row.addWidget(self.url_edit, 1)
        self.load_btn = QPushButton("Carregar")
        self.load_btn.setObjectName("primary")
        self.load_btn.clicked.connect(self.load_url)
        row.addWidget(self.load_btn)
        uc.addLayout(row)
        self.status_lbl = QLabel("Nenhuma lista carregada")
        self.status_lbl.setObjectName("muted")
        uc.addWidget(self.status_lbl)
        self.load_prog = QProgressBar()
        self.load_prog.setRange(0, 0)
        self.load_prog.hide()
        uc.addWidget(self.load_prog)
        lay.addWidget(url_card)

        # Barra de busca grande (referência) + chips de filtro
        fcard = QFrame()
        fcard.setObjectName("card")
        fv = QVBoxLayout(fcard)
        fv.setContentsMargins(14, 10, 14, 12)
        fv.setSpacing(10)
        srow = QHBoxLayout()
        self.search_edit = QLineEdit()
        self.search_edit.setObjectName("bigSearch")
        self.search_edit.setPlaceholderText("🔎  Buscar filmes, séries ou canais…")
        self.search_edit.setMinimumHeight(42)
        self.search_edit.textChanged.connect(self._on_search_changed)
        srow.addWidget(self.search_edit, 1)
        self.group_cb = QComboBox()
        self.group_cb.addItem("Todos os grupos", "Todos")
        self.group_cb.currentIndexChanged.connect(self._apply_filters_now)
        srow.addWidget(self.group_cb, 0)
        self.clear_btn = QPushButton("Limpar")
        self.clear_btn.setObjectName("chip")
        self.clear_btn.clicked.connect(self.clear_filters)
        srow.addWidget(self.clear_btn)
        fv.addLayout(srow)

        # Chips de tipo (Todos / Filmes / Séries / Rádio / Esportes / Canais / YouTube)
        self.type_cb = QComboBox()  # compat: espelho do chip ativo (não exibido)
        for lbl, val in (("Todos", "Todos"), ("Filmes", "filme"),
                         ("Séries", "serie"), ("Rádio", "radio"),
                         ("Esportes", "esporte"), ("Canais", "canal"),
                         ("YouTube", "youtube")):
            self.type_cb.addItem(lbl, val)
        self.type_cb.currentIndexChanged.connect(self._apply_filters_now)

        chips_row = QHBoxLayout()
        chips_row.setSpacing(8)
        self._chips: dict[str, QPushButton] = {}
        for lbl, val in (("Todos", "Todos"), ("Filmes", "filme"),
                         ("Séries", "serie"), ("Rádio", "radio"),
                         ("Esportes", "esporte"), ("Canais", "canal"),
                         ("YouTube", "youtube")):
            chip = QPushButton(lbl)
            chip.setObjectName("chip")
            chip.setCheckable(True)
            chip.setChecked(val == "Todos")
            chip.clicked.connect(lambda _c=False, v=val: self._select_chip(v))
            chips_row.addWidget(chip)
            self._chips[val] = chip
        chips_row.addStretch(1)
        # alternância Grid/Lista (mesma virtualização, mesma seleção)
        self._view_chips: dict[str, QPushButton] = {}
        for icon, key in (("▦", "grid"), ("☰", "list")):
            c = QPushButton(icon)
            c.setObjectName("chip")
            c.setCheckable(True)
            c.setChecked(key == "grid")
            c.setFixedWidth(42)
            c.setToolTip("Grade" if key == "grid" else "Lista")
            c.clicked.connect(lambda _x=False, k=key: self._switch_view(k))
            chips_row.addWidget(c)
            self._view_chips[key] = c
        fv.addLayout(chips_row)
        lay.addWidget(fcard)

        mid = QHBoxLayout()
        mid.setSpacing(12)

        # Stack: estado vazio / view virtualizada
        self.stack = QStackedWidget()
        self.empty = QFrame()
        ev = QVBoxLayout(self.empty)
        ev.setAlignment(Qt.AlignCenter)
        ev.setSpacing(10)
        from app.ui.resources.icons import logo_pixmap
        logo = QLabel()
        logo.setPixmap(logo_pixmap(72))
        logo.setAlignment(Qt.AlignCenter)
        ev.addWidget(logo)
        et = QLabel("Nenhum conteúdo carregado")
        et.setAlignment(Qt.AlignCenter)
        et.setStyleSheet("font-size: 15px; font-weight: 600;")
        ev.addWidget(et)
        es = QLabel("Cole acima a URL de uma lista M3U, canal do YouTube\n"
                    "ou link de vídeo e clique em Carregar.")
        es.setObjectName("muted")
        es.setAlignment(Qt.AlignCenter)
        ev.addWidget(es)
        self.stack.addWidget(self.empty)

        self.model = LibraryModel(self)

        # Pool de capas (3 workers, fila limitada) — lazy loading visual
        self.cover_pool = CoverPool(self, workers=3)
        self.cover_pool.start()

        # Views compartilhando o mesmo modelo (virtualizadas)
        self.grid = ContentGridView(self.model, self.cover_pool)
        self.grid.selectionChanged.connect(self._on_selection_changed)
        self.grid.detailRequested.connect(self._on_detail_row)
        self.table_view = LibraryView(self.model)
        self.table_view.selectionChanged.connect(self._on_selection_changed)
        self.table_view.detailRequested.connect(self._on_detail_row)

        # view ativa (padrão: grid, como na referência)
        self._views = [self.grid, self.table_view]
        self.view_stack = QStackedWidget()
        self.view_stack.addWidget(self.grid)
        self.view_stack.addWidget(self.table_view)
        self.table = self.grid  # alias público (API/testes existentes)

        self.stack.addWidget(self.empty)
        self.stack.addWidget(self.view_stack)
        mid.addWidget(self.stack, 1)

        det = QFrame()
        det.setObjectName("card")
        det.setFixedWidth(290)
        dv = QVBoxLayout(det)
        dv.setContentsMargins(14, 12, 14, 12)
        dh = QLabel("Detalhes")
        dh.setStyleSheet("font-weight: 700;")
        dv.addWidget(dh)
        self.cover_lbl = QLabel()
        self.cover_lbl.setFixedSize(260, 150)
        self.cover_lbl.setAlignment(Qt.AlignCenter)
        self.cover_lbl.setObjectName("muted")
        self.cover_lbl.setText("Sem capa")
        dv.addWidget(self.cover_lbl)

        self.detail_lbl = QLabel("Selecione um item para ver detalhes.")
        self.detail_lbl.setObjectName("muted")
        self.detail_lbl.setWordWrap(True)
        self.detail_lbl.setTextInteractionFlags(Qt.TextSelectableByMouse)
        dv.addWidget(self.detail_lbl)

        share_row = QHBoxLayout()
        self.copy_url_btn = QPushButton("📋 Copiar URL")
        self.copy_url_btn.setEnabled(False)
        self.copy_url_btn.clicked.connect(self._copy_current_url)
        share_row.addWidget(self.copy_url_btn)
        self.share_btn = QPushButton("↗ Compartilhar")
        self.share_btn.setEnabled(False)
        self.share_btn.clicked.connect(self._share_current)
        share_row.addWidget(self.share_btn)
        dv.addLayout(share_row)
        dv.addStretch(1)
        mid.addWidget(det)
        lay.addLayout(mid, 1)

        bar = QHBoxLayout()
        for text, slot in (("Todos", self.select_all),
                           ("Nenhum", self.select_none),
                           ("Inverter", self.select_invert)):
            b = QPushButton(text)
            b.clicked.connect(slot)
            bar.addWidget(b)
        self.sel_lbl = QLabel("0 selecionados")
        self.sel_lbl.setObjectName("muted")
        bar.addWidget(self.sel_lbl)
        bar.addStretch(1)
        self.dl_btn = QPushButton("Baixar selecionados")
        self.dl_btn.setObjectName("primary")
        self.dl_btn.setEnabled(False)
        self.dl_btn.clicked.connect(self._emit_selected)
        bar.addWidget(self.dl_btn)
        lay.addLayout(bar)

    def _select_chip(self, value: str):
        """Chips de tipo: atualiza combo interno (compat) e filtra."""
        for k, chip in self._chips.items():
            chip.setChecked(k == value)
        idx = self.type_cb.findData(value)
        if idx >= 0:
            self.type_cb.setCurrentIndex(idx)
        self._apply_filters_now()

    def _switch_view(self, key: str):
        for k, c in self._view_chips.items():
            c.setChecked(k == key)
        self.view_stack.setCurrentWidget(
            self.grid if key == "grid" else self.table_view)

    # ── Carregamento ─────────────────────────────────────────────────────

    def load_url(self):
        url = self.url_edit.text().strip()
        ok, message = validate_url(url)
        if not ok:
            self.wantToast.emit(message, "warning")
            self.status_lbl.setText("⚠ " + message)
            return
        if self._worker is not None and self._worker.isRunning():
            self.wantToast.emit("Já existe um carregamento em andamento.", "info")
            return

        routed = classify_url(url)
        self._cancel_cover()
        self.model.begin_loading()
        self.entries = []
        self.filtered = []
        self._set_loading(True, f"Carregando: {url[:80]}")

        if routed.kind in (UrlKind.LOCAL_FILE, UrlKind.M3U_PLAYLIST):
            # Playlists: parse incremental em lotes (background).
            self._worker = PlaylistBatchWorker(url, self.cfg, _LOAD_BATCH, self)
            self._worker.batch.connect(self._on_batch)
            self._worker.done.connect(self._on_batch_done)
            self._worker.finishedEmpty.connect(lambda: self._load_rest(url))
            self._worker.failed.connect(self._on_failed)
            self._worker.start()
        else:
            self._worker = ExtractWorker(url, self.cfg, self)
            self._worker.log.connect(self._on_log)
            self._worker.done.connect(self._on_done)
            self._worker.failed.connect(self._on_failed)
            self._worker.start()

    def _load_rest(self, url: str):
        """Manifest HLS sem EXTINF: cai no extractor completo (yt-dlp)."""
        self._on_log("  Manifest HLS — tratando como vídeo único.")
        self._worker = ExtractWorker(url, self.cfg, self)
        self._worker.log.connect(self._on_log)
        self._worker.done.connect(self._on_done)
        self._worker.failed.connect(self._on_failed)
        self._worker.start()

    def _set_loading(self, loading: bool, text: str = ""):
        self.load_prog.setVisible(loading)
        self.load_btn.setEnabled(not loading)
        self.load_btn.setText("Cancelar" if loading else "Carregar")
        self.load_btn.setObjectName("danger" if loading else "primary")
        self.load_btn.style().unpolish(self.load_btn)
        self.load_btn.style().polish(self.load_btn)
        if loading:
            try:
                self.load_btn.clicked.disconnect(self.load_url)
            except RuntimeError:
                pass
            self.load_btn.clicked.connect(self._cancel_load)
        else:
            try:
                self.load_btn.clicked.disconnect(self._cancel_load)
            except RuntimeError:
                pass
            self.load_btn.clicked.connect(self.load_url)
        if text:
            self.status_lbl.setText(text)

    def _cancel_load(self):
        if self._worker and self._worker.isRunning():
            self._worker.cancel()

    def _on_log(self, msg: str):
        self.status_lbl.setText(msg)

    def _on_batch(self, batch: list):
        """Lote vindo do parser em background — insere no modelo em bloco."""
        self.entries.extend(batch)
        self.model.append_entries(batch)
        self.filtered = self.model._filtered
        total = len(self.model._all)
        self.status_lbl.setText(f"Carregando… {total:,} itens".replace(",", "."))

    def _on_batch_done(self, total: int):
        self._set_loading(False)
        self._finish_load(total)

    def _on_done(self, entries: list):
        self._set_loading(False)
        self._on_entries(entries)

    def _on_entries(self, entries: list):
        """Entrada única (YouTube/sites): o modelo recria de uma vez — leve,
        pois não há widgets por item."""
        self.entries = entries
        self.model.set_entries(entries)
        self.filtered = self.model._filtered
        self._finish_load(len(entries))
        self._refresh_groups()

    def _finish_load(self, total: int):
        self.stack.setCurrentWidget(self.view_stack if total else self.empty)
        if total == 0:
            self.status_lbl.setText("Nenhum item encontrado nesta lista.")
            self.wantToast.emit("Nenhum item encontrado.", "info")
        else:
            self.status_lbl.setText(f"{total:,} itens carregados ✔".replace(",", "."))
            self.wantToast.emit(f"{total} itens carregados!", "success")
        self._on_selection_changed(0)

    def _refresh_groups(self):
        groups = sorted({e["group"] for e in self.entries})
        self.group_cb.blockSignals(True)
        self.group_cb.clear()
        self.group_cb.addItem("Todos os grupos", "Todos")
        for g in groups:
            self.group_cb.addItem(g, g)
        self.group_cb.blockSignals(False)

    def _on_failed(self, friendly: str, detail: str):
        self._set_loading(False)
        self.status_lbl.setText("✖ " + friendly)
        self.wantToast.emit(friendly, "error")
        if detail:
            self.status_lbl.setToolTip(detail)

    # ── Filtros com debounce ─────────────────────────────────────────────

    def _on_search_changed(self, _text):
        self._filter_timer.start()  # reinicia a cada tecla (debounce)

    def _apply_filters_now(self, *_):
        self.model.set_filter(
            self.search_edit.text().lower().strip(),
            self.group_cb.currentData() or "Todos",
            self.type_cb.currentData() or "Todos")
        self.filtered = self.model._filtered
        self.stack.setCurrentWidget(self.view_stack if self.model.rowCount()
                                    else self.empty)
        self._on_selection_changed(0)

    # Compat com a API antiga (chamadas diretas/disparo imediato)
    def apply_filters(self):
        self._apply_filters_now()

    def clear_filters(self):
        self.search_edit.clear()
        self.group_cb.setCurrentIndex(0)
        self.type_cb.setCurrentIndex(0)
        for k, chip in self._chips.items():
            chip.setChecked(k == "Todos")
        self._apply_filters_now()

    # ── Seleção ──────────────────────────────────────────────────────────

    def _on_selection_changed(self, count: int):
        self.sel_lbl.setText(f"{count:,} selecionados".replace(",", "."))
        self.dl_btn.setEnabled(count > 0)
        self._show_current_details()

    def _on_detail_row(self, row: int):
        if 0 <= row < self.model.rowCount():
            self._show_detail(self.model.entry_at(row))

    def select_all(self):
        self.model.set_checked_all(True)
        self.table.selectionChanged.emit(self.table.checked_count())

    def select_none(self):
        self.model.set_checked_all(False)
        self.table.selectionChanged.emit(0)

    def select_invert(self):
        self.model.invert_checked()
        self.table.selectionChanged.emit(self.table.checked_count())

    def selected_entries(self) -> list[dict]:
        return [self.model.entry_at(r) for r in self.table.checked_rows()]

    def _emit_selected(self):
        selected = self.selected_entries()
        if not selected:
            self.wantToast.emit("Selecione pelo menos um item.", "warning")
            return
        self.entriesSelected.emit(selected)

    # ── Detalhes/capa sob demanda ────────────────────────────────────────

    def _show_current_details(self):
        rows = self.table.checked_rows()
        if rows:
            self._show_detail(self.model.entry_at(rows[-1]))

    def _show_detail(self, e: dict):
        self._current_entry = e
        self.copy_url_btn.setEnabled(True)
        self.share_btn.setEnabled(True)
        shown_url = redact_url(e["url"]) if is_sensitive_url(e["url"]) else e["url"]
        self.detail_lbl.setText(
            f"<b>{e['title']}</b><br>"
            f"Grupo: {e['group']}<br>"
            f"Tipo: {theme.type_label(e['type'])}<br>"
            f"URL: {shown_url[:120]}{'…' if len(shown_url) > 120 else ''}")

        # Capa: cache LRU → só o item em detalhe; nunca em massa.
        logo = e.get("logo") or ""
        if not logo:
            self._show_placeholder_cover()
            return
        if logo in self._cover_cache:
            self._cover_cache.move_to_end(logo)
            self._apply_cover(self._cover_cache[logo])
            return
        self.cover_lbl.setText("Carregando capa…")
        self._cancel_cover()
        self._cover_worker = CoverFetcher(logo, self)
        self._cover_worker.loaded.connect(
            lambda data, k=logo: self._cache_and_show(k, data))
        self._cover_worker.start()

    def _cache_and_show(self, key: str, data: bytes):
        pix = QPixmap()
        pix.loadFromData(data)
        if pix.isNull():
            self._show_placeholder_cover()
            return
        pix = pix.scaled(260, 150, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self._cover_cache[key] = pix
        self._cover_cache.move_to_end(key)
        while len(self._cover_cache) > _COVER_CACHE_MAX:
            self._cover_cache.popitem(last=False)
        self._apply_cover(pix)

    def _apply_cover(self, pix: QPixmap):
        self._cover_pixmap = pix
        self.cover_lbl.setPixmap(pix)

    def _show_placeholder_cover(self):
        self._cover_pixmap = None
        self.cover_lbl.setPixmap(QPixmap())
        self.cover_lbl.setText("Sem capa")

    def _cancel_cover(self):
        if self._cover_worker and self._cover_worker.isRunning():
            self._cover_worker.terminate()
            self._cover_worker.wait(500)

    # ── Compartilhamento ─────────────────────────────────────────────────

    def _copy_current_url(self):
        e = self._current_entry
        if e is None:
            return
        plan = share.plan_share(e)
        from PySide6.QtWidgets import QApplication
        if plan.shareable:
            QApplication.clipboard().setText(plan.url)
            self.wantToast.emit("URL copiada!", "success")
        elif plan.safe_reference:
            QApplication.clipboard().setText(plan.safe_reference)
            self.wantToast.emit(
                "Link com credenciais: copiada apenas a referência segura.",
                "warning")
        else:
            self.wantToast.emit("Este item não possui URL para copiar.", "info")

    def _share_current(self):
        e = self._current_entry
        if e is None:
            return
        from app.ui.widgets.share_dialog import ShareDialog
        dlg = ShareDialog(e, self)
        dlg.wantToast.connect(self.wantToast)
        dlg.exec()

    # ── Ciclo de vida ────────────────────────────────────────────────────

    def shutdown(self):
        if self._worker and self._worker.isRunning():
            self._worker.cancel()
            self._worker.wait(2000)
        self.cover_pool.stop()
        self.cover_pool.wait(2000)
        self._cancel_cover()
