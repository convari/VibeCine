# -*- coding: utf-8 -*-
"""Testes de performance/virtualização da Biblioteca (listas grandes).

Verifica as metas da etapa:
- indexação de 50.000 itens sem congelar a UI e sem criar 50.000 widgets;
- somente itens visíveis passam por processamento visual;
- capas sob demanda com cache LRU;
- busca/filtros com debounce e O(n) leve;
- seleção completa em tempo constante por linha;
- parsing incremental em lotes.
"""

import os
import sys
import tempfile
import time
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication  # noqa: E402

from app.core.config import load_config  # noqa: E402
from app.core.history import HistoryStore  # noqa: E402
from app.core.m3u_parser import iter_m3u_batches, parse_m3u  # noqa: E402
from app.ui.main_window import MainWindow  # noqa: E402
from app.ui.pages.library import _COVER_CACHE_MAX, LibraryPage  # noqa: E402

LARGE = 50_000


def make_entries(n):
    return [{"title": f"Conteúdo {i}", "group": f"G{i % 25}", "logo": "",
             "tvg_id": str(i), "tvg_name": f"c{i}",
             "url": f"http://x.tv/v/{i}.mp4", "type": "filme"}
            for i in range(n)]


def make_m3u(n):
    lines = ["#EXTM3U"]
    for i in range(n):
        lines.append(f'#EXTINF:-1 group-title="G{i % 25}",Conteúdo {i}')
        lines.append(f"http://x.tv/v/{i}.mp4")
    return "\n".join(lines)


def pump(app, seconds=0.05):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        app.processEvents()
        time.sleep(0.005)


def process_until(app, pred, timeout=30.0):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        app.processEvents()
        if pred():
            return True
        time.sleep(0.02)
    return pred()


class PerfCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        cfg = load_config()
        cfg["download_folder"] = self.tmp.name
        cfg["onboarding_done"] = True
        self.window = MainWindow(cfg=cfg, history=HistoryStore(
            os.path.join(self.tmp.name, "h.db")))
        self.addCleanup(self.window.close)
        self.lib: LibraryPage = self.window.library


class TestParsingIncremental(unittest.TestCase):
    def test_lotes_de_200(self):
        content = make_m3u(1050)
        batches = list(iter_m3u_batches(content, 200))
        self.assertEqual(len(batches), 6)  # 5×200 + 50
        self.assertEqual(sum(len(b) for b in batches), 1050)
        # resultado idêntico ao parse completo
        full = parse_m3u(content)
        flat = [e for b in batches for e in b]
        self.assertEqual([e["title"] for e in flat],
                         [e["title"] for e in full])

    def test_parser_50k_rapido(self):
        content = make_m3u(LARGE)
        t0 = time.perf_counter()
        entries = parse_m3u(content)
        dt = time.perf_counter() - t0
        self.assertEqual(len(entries), LARGE)
        self.assertLess(dt, 5.0, f"parse lento demais: {dt:.1f}s")


class TestVirtualizacao(PerfCase):
    def test_50k_sem_widgets_por_item(self):
        from app.core.m3u_parser import parse_m3u
        entries = make_entries(LARGE)
        before = len(self.app.allWidgets())

        t0 = time.perf_counter()
        self.lib._on_entries(entries)
        pump(self.app, 0.2)
        first_usable = time.perf_counter() - t0

        after = len(self.app.allWidgets())
        self.assertEqual(self.lib.table.rowCount(), LARGE)
        self.assertLess(after - before, 100,
                        f"foram criados {after - before} widgets extras")
        self.assertLess(first_usable, 2.0,
                        f"UI utilizável em {first_usable:.2f}s")
        # view virtualizada: nunca terá 50k componentes visuais
        self.assertLess(len(self.lib.table.viewport().children()), 100)

    def test_primeira_renderizacao_rapida(self):
        entries = make_entries(LARGE)
        t0 = time.perf_counter()
        self.lib._on_entries(entries)
        self.app.processEvents()  # um ciclo de evento já basta
        dt = time.perf_counter() - t0
        self.assertLess(dt, 1.5, f"primeira renderização em {dt:.2f}s")

    def test_busca_em_50k(self):
        self.lib._on_entries(make_entries(LARGE))
        pump(self.app, 0.1)
        t0 = time.perf_counter()
        self.lib.search_edit.setText("Conteúdo 499")
        self.lib._apply_filters_now()  # busca explícita (debounce coberto)
        pump(self.app, 0.05)
        dt = time.perf_counter() - t0
        # "Conteúdo 499" casa 1 + 10 + 100 variações (prefixo numérico)
        self.assertEqual(self.lib.table.rowCount(), 111)
        self.assertLess(dt, 1.0, f"busca em 50k demorou {dt:.2f}s")

    def test_filtro_grupo_tipo(self):
        entries = make_entries(LARGE)
        entries[0] = dict(entries[0], type="serie", group="Única")
        self.lib._on_entries(entries)
        pump(self.app, 0.1)
        idx = self.lib.type_cb.findData("serie")
        self.lib.type_cb.setCurrentIndex(idx)
        self.lib._apply_filters_now()
        self.assertEqual(self.lib.table.rowCount(), 1)

    def test_selecao_50k_constante(self):
        self.lib._on_entries(make_entries(LARGE))
        pump(self.app, 0.1)
        t0 = time.perf_counter()
        self.lib.select_all()
        self.assertEqual(self.lib.table.checked_count(), LARGE)
        self.lib.select_none()
        self.assertEqual(self.lib.table.checked_count(), 0)
        self.lib.select_invert()
        self.assertEqual(self.lib.table.checked_count(), LARGE)
        dt = time.perf_counter() - t0
        self.assertLess(dt, 2.0, f"seleção de 50k em {dt:.2f}s")
        sel = self.lib.selected_entries()
        self.assertEqual(len(sel), LARGE)
        self.assertEqual(sel[0]["title"], "Conteúdo 0")

    def test_debounce_existe(self):
        self.assertEqual(self.lib._filter_timer.interval(), 250)
        self.assertTrue(self.lib._filter_timer.isSingleShot())

    def test_cache_de_capas_limitado(self):
        from PySide6.QtGui import QPixmap
        from PySide6.QtCore import QBuffer, QIODevice
        for i in range(_COVER_CACHE_MAX + 10):
            pix = QPixmap(4, 4)
            pix.fill()
            buf = QBuffer()
            buf.open(QIODevice.ReadWrite)
            pix.save(buf, "PNG")
            self.lib._cache_and_show(f"http://capa/{i}.png", bytes(buf.data()))
        self.assertEqual(len(self.lib._cover_cache), _COVER_CACHE_MAX)
        # LRU: o item mais antigo foi evictado
        self.assertNotIn("http://capa/0.png", self._lib_cache())

    def _lib_cache(self):
        return self.lib._cover_cache


class TestBatchLoadingNaUI(PerfCase):
    def test_worker_incremental_via_ui(self):
        """Carregar M3U real via PlaylistBatchWorker: lotes chegam e a
        UI nunca precisa do dataset completo de uma vez."""
        m3u_path = os.path.join(self.tmp.name, "grande.m3u")
        with open(m3u_path, "w", encoding="utf-8") as fh:
            fh.write(make_m3u(3000))
        self.lib.url_edit.setText(m3u_path)
        self.lib.load_url()
        ok = process_until(
            self.app, lambda: self.lib.table.rowCount() == 3000, timeout=30)
        self.assertTrue(ok, f"rowCount={self.lib.table.rowCount()}")
        # lista utilizável rapidamente: primeiro lote já aparece cedo
        self.assertGreaterEqual(len(self.lib.entries), 200)
        self.assertFalse(self.lib.load_prog.isVisible())


if __name__ == "__main__":
    unittest.main()
