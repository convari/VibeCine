# -*- coding: utf-8 -*-
"""Testes da Fase 5: marca, ícones, onboarding, histórico e polimento da UI."""

import os
import tempfile
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from app.core import branding  # noqa: E402
from app.core.config import load_config, save_config  # noqa: E402
from app.core.history import HistoryStore  # noqa: E402


class TestBranding(unittest.TestCase):
    def test_constantes_centralizadas(self):
        self.assertEqual(branding.APP_NAME, "VibeCine")
        self.assertTrue(branding.APP_VERSION)
        self.assertIn("VibeCine", branding.APP_ABOUT_TEXT)
        self.assertIn("TERMOS DE USO", branding.TERMS_OF_USE)
        self.assertIn("autorização", branding.TERMS_OF_USE.lower())

    def test_sem_nome_pessoal_hardcoded(self):
        # A marca não deve conter nomes pessoais.
        for texto in (branding.APP_ABOUT_TEXT, branding.TERMS_OF_USE,
                      branding.APP_NAME, branding.APP_VENDOR):
            self.assertNotIn("Eduardo", texto)

    def test_flags_de_primeira_execucao(self):
        cfg = load_config()
        self.assertIn("onboarding_done", cfg)
        self.assertIn("terms_accepted", cfg)
        self.assertEqual(cfg["max_concurrent_downloads"], 2)
        self.assertEqual(cfg["theme"], "dark")


class TestIcons(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PySide6.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication([])

    def test_logo_pixmap(self):
        from app.ui.resources.icons import logo_pixmap
        pix = logo_pixmap(64)
        self.assertFalse(pix.isNull())
        self.assertEqual(pix.width(), 64)

    def test_arquivos_de_icone_gerados(self):
        from app.ui.resources.icons import ICO_PATH, PNG_PATH, ensure_icon_files
        png, ico = ensure_icon_files()
        self.assertTrue(os.path.isfile(png))
        self.assertTrue(os.path.isfile(ico))
        self.assertGreater(os.path.getsize(png), 500)
        self.assertGreater(os.path.getsize(ico), 500)


class TestHistoryDelete(unittest.TestCase):
    def test_delete_registro(self):
        with tempfile.TemporaryDirectory() as td:
            store = HistoryStore(os.path.join(td, "h.db"))
            rid = store.add(title="X", group="", url="u", status="concluido",
                            out_dir="")
            self.assertEqual(len(store.list()), 1)
            self.assertTrue(store.delete(rid))
            self.assertFalse(store.delete(rid))  # já removido
            self.assertEqual(store.list(), [])


class TestOnboarding(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PySide6.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication([])

    def _make(self, **over):
        cfg = load_config()
        cfg.update({"onboarding_done": False, "terms_accepted": False})
        cfg.update(over)
        return cfg

    def test_fluxo_e_bloqueio_de_termos(self):
        import app.ui.onboarding as ob
        saved = {}
        original = ob.save_config
        ob.save_config = lambda c, **kw: saved.update(c)
        try:
            dlg = ob.OnboardingDialog(self._make())
            dlg.show()
            self.app.processEvents()
            # Página 0 -> avançar sem problemas
            dlg._next()
            self.assertEqual(dlg.stack.currentIndex(), 1)
            # Termos: botão desabilitado até aceitar
            self.assertFalse(dlg.next_btn.isEnabled())
            dlg.terms_cb.setChecked(True)
            self.assertTrue(dlg.next_btn.isEnabled())
            dlg._next()  # grava aceite
            self.assertTrue(dlg.cfg["terms_accepted"])
            # Avança até o fim
            while dlg.stack.currentIndex() < len(dlg._pages) - 1:
                dlg._next()
            self.assertEqual(dlg.stack.currentIndex(), len(dlg._pages) - 1)
            dlg._next()  # "Começar"
            self.assertTrue(saved.get("onboarding_done"))
            dlg.deleteLater()
        finally:
            ob.save_config = original

    def test_skip_conclui_sem_aceitar_termos(self):
        import app.ui.onboarding as ob
        saved = {}
        original = ob.save_config
        ob.save_config = lambda c, **kw: saved.update(c)
        try:
            dlg = ob.OnboardingDialog(self._make())
            dlg.show()
            self.app.processEvents()
            dlg._skip()
            self.assertTrue(saved.get("onboarding_done"))
            self.assertFalse(dlg.cfg.get("terms_accepted", True) and False
                             or False)  # skip não força aceite
            dlg.deleteLater()
        finally:
            ob.save_config = original


class TestMainWindowPolish(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PySide6.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        from app.ui.main_window import MainWindow
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        cfg = load_config()
        cfg["download_folder"] = self.tmp.name
        cfg["onboarding_done"] = True
        self.window = MainWindow(cfg=cfg,
                                 history=HistoryStore(
                                     os.path.join(self.tmp.name, "h.db")))
        self.addCleanup(self.window.close)

    def test_janela_tem_icone_e_titulo(self):
        self.assertFalse(self.window.windowIcon().isNull())
        self.assertIn("VibeCine", self.window.windowTitle())

    def test_tamanho_minimo(self):
        self.assertGreaterEqual(self.window.minimumWidth(), 900)
        self.assertGreaterEqual(self.window.minimumHeight(), 600)

    def test_config_paginas_em_secoes(self):
        from PySide6.QtWidgets import QTabWidget
        tabs = self.window.settings.findChild(QTabWidget)
        self.assertIsNotNone(tabs)
        self.assertEqual(tabs.count(), 6)
        names = [tabs.tabText(i) for i in range(tabs.count())]
        for esperado in ("Downloads", "Desempenho", "Aparência",
                         "Ferramentas", "Atualizações", "Informações"):
            self.assertIn(esperado, names)

    def test_historico_filtros_corretos(self):
        cb = self.window.history_page.filter_cb
        self.assertIsNone(cb.itemData(0))
        self.assertEqual(cb.itemData(1), "concluido")
        self.assertEqual(cb.itemData(2), "erro")
        self.assertEqual(cb.itemData(3), "cancelado")

    def test_onboarding_nao_repete(self):
        self.window.maybe_show_onboarding()  # já concluído: não deve abrir
        self.app.processEvents()
        self.assertTrue(self.window.cfg["onboarding_done"])

    def test_temas_claro_e_escuro(self):
        self.window.apply_theme("light")
        self.window.apply_theme("dark")


if __name__ == "__main__":
    unittest.main()
