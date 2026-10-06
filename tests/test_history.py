# -*- coding: utf-8 -*-
"""Testes do histórico (app.core.history)."""

import os
import tempfile
import unittest

from app.core.history import HistoryStore
from app.core.downloader import JobStatus


class TestHistory(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.store = HistoryStore(os.path.join(self.tmp.name, "h.db"))

    def test_add_e_listagem(self):
        self.store.add(title="Matrix", group="Filmes",
                       url="http://user:senha@h.tv/x?token=abc",
                       status=JobStatus.DONE.value, out_dir="C:/F",
                       output_path="C:/F/matrix.mp4", size_bytes=123)
        rows = self.store.list()
        self.assertEqual(len(rows), 1)
        r = rows[0]
        self.assertEqual(r["title"], "Matrix")
        self.assertEqual(r["status"], "concluido")
        self.assertEqual(r["size_bytes"], 123)
        # credenciais mascaradas no histórico
        self.assertNotIn("senha", r["url"])
        self.assertNotIn("abc", r["url"])

    def test_filtro_por_status(self):
        self.store.add(title="A", group="", url="u", status="concluido", out_dir="")
        self.store.add(title="B", group="", url="u", status="erro", out_dir="")
        self.assertEqual(len(self.store.list(status="erro")), 1)
        self.assertEqual(len(self.store.list(status="concluido")), 1)
        self.assertEqual(len(self.store.list()), 2)

    def test_contagem_e_limpeza(self):
        self.store.add(title="A", group="", url="u", status="concluido", out_dir="")
        self.store.add(title="B", group="", url="u", status="cancelado", out_dir="")
        counts = self.store.count_by_status()
        self.assertEqual(counts["concluido"], 1)
        self.assertEqual(counts["cancelado"], 1)
        self.assertEqual(self.store.clear(), 2)
        self.assertEqual(self.store.list(), [])

    def test_banco_criado(self):
        self.assertTrue(os.path.isfile(self.store.db_path))


if __name__ == "__main__":
    unittest.main()
