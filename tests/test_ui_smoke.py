# -*- coding: utf-8 -*-
"""Testes da nova interface PySide6 (modo offscreen: nenhuma janela é exibida).

Valida navegação, Biblioteca (filtros, seleção por checkbox), integração
Biblioteca → Downloads com o DownloadManager (yt-dlp falso), registro no
histórico e troca de tema.
"""

import os
import sys
import tempfile
import time
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication  # noqa: E402

from app.core.config import load_config  # noqa: E402
from app.core.downloader import DownloadManager, JobStatus  # noqa: E402
from app.core.history import HistoryStore  # noqa: E402
from app.ui.main_window import MainWindow  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
FAKE = os.path.join(HERE, "_fake_ytdlp.py")


def fake_builder_factory(workdir):
    def build(entry, cfg, unique_names=False):
        stem = entry["url"].replace("fake://", "").split("?")[0] or "item"
        template = os.path.join(workdir, stem + "-%(ext)s")
        ctx = {"out_dir": workdir, "out_template": template, "stem": stem,
               "warnings": [], "ytdlp": "fake",
               "ffmpeg": os.path.join(workdir, "fake.exe"), "deno": "fake"}
        return [sys.executable, FAKE, "-o", template, entry["url"]], ctx
    return build


def process_until(app, predicate, timeout=20.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        app.processEvents()
        if predicate():
            return True
        time.sleep(0.03)
    return predicate()


ENTRIES = [
    {"title": "Matrix", "group": "Filmes", "logo": "", "tvg_id": "",
     "tvg_name": "", "url": "fake://ok", "type": "filme"},
    {"title": "Breaking Bad", "group": "Séries", "logo": "", "tvg_id": "",
     "tvg_name": "", "url": "fake://ok2", "type": "serie"},
    {"title": "Canal SporTV", "group": "Esportes", "logo": "", "tvg_id": "",
     "tvg_name": "", "url": "fake://ok3", "type": "esporte"},
]


class TestMainWindow(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        cfg = load_config()
        cfg["download_folder"] = self.tmp.name
        history = HistoryStore(os.path.join(self.tmp.name, "h.db"))
        builder = fake_builder_factory(self.tmp.name)

        def factory(c):
            return DownloadManager(c, max_workers=2, command_builder=builder,
                                   sleeper=lambda s: time.sleep(0.01))
        self.window = MainWindow(cfg=cfg, manager_factory=factory,
                                 history=history)
        self.addCleanup(self.window.downloads.shutdown)
        self.addCleanup(self.window.close)

    def test_paginas_e_navegacao(self):
        for key in ("library", "downloads", "history", "settings"):
            self.window.navigate(key)
            self.assertEqual(
                self.window.stack.currentIndex(),
                self.window._page_index[key])
            self.assertTrue(self.window.nav_buttons[key].isChecked())

    def test_tema_troca_sem_erros(self):
        self.window.apply_theme("light")
        self.window.apply_theme("dark")

    def test_biblioteca_filtros_e_selecao(self):
        lib = self.window.library
        lib._on_entries(ENTRIES)
        self.assertTrue(process_until(
            self.app, lambda: lib.table.rowCount() == 3))
        # Filtro por busca
        lib.search_edit.setText("matrix")
        self.assertTrue(process_until(
            self.app, lambda: lib.table.rowCount() == 1))
        lib.search_edit.clear()
        # Filtro por tipo
        idx = lib.type_cb.findData("serie")
        lib.type_cb.setCurrentIndex(idx)
        self.assertTrue(process_until(
            self.app, lambda: lib.table.rowCount() == 1))
        lib.type_cb.setCurrentIndex(0)
        self.assertTrue(process_until(
            self.app, lambda: lib.table.rowCount() == 3))
        # Seleção
        lib.select_all()
        self.assertTrue(process_until(
            self.app, lambda: lib.table.checked_count() == 3))
        self.assertTrue(lib.dl_btn.isEnabled())
        lib.select_none()
        self.assertTrue(process_until(
            self.app, lambda: lib.table.checked_count() == 0))
        self.assertFalse(lib.dl_btn.isEnabled())
        lib.select_invert()
        self.assertTrue(process_until(
            self.app, lambda: lib.table.checked_count() == 3))

    def test_fluxo_biblioteca_para_downloads_e_historico(self):
        lib = self.window.library
        lib._on_entries(ENTRIES)
        self.assertTrue(process_until(
            self.app, lambda: lib.table.rowCount() == 3))
        lib.select_all()
        lib._emit_selected()
        # Navegou para Downloads
        self.assertEqual(self.window.stack.currentIndex(),
                         self.window._page_index["downloads"])
        # Linhas criadas
        self.assertTrue(process_until(
            self.app, lambda: len(self.window.downloads._rows) == 3))
        # Downloads concluem (fake) e vão para o histórico
        self.assertTrue(process_until(
            self.app,
            lambda: all(j.status is JobStatus.DONE
                        for j in self.window.downloads.manager.jobs),
            timeout=40))
        hist = self.window.history.list()
        self.assertTrue(process_until(
            self.app, lambda: len(self.window.history.list()) == 3))
        self.assertTrue(all(h["status"] == "concluido" for h in hist))
        # Página de histórico reflete os registros
        self.window.navigate("history")
        self.assertEqual(self.window.history_page.table.rowCount(), 3)

    def test_toast_nao_bloqueia(self):
        t = self.window.toasts.success("Teste de toast")
        self.assertIsNotNone(t)


if __name__ == "__main__":
    unittest.main()
