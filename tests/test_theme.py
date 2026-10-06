# -*- coding: utf-8 -*-
"""Testes de tema: contraste WCAG e cobertura QSS dos widgets."""

import re
import unittest

from app.ui import theme


class TestContraste(unittest.TestCase):
    """Contraste WCAG: texto normal ≥ 4.5, textos grandes/úteis ≥ 3.0."""

    PARES_TEXTUAIS = (
        ("text", "bg"), ("text", "card"), ("text", "panel"),
        ("text", "input_bg"),
        ("text_dim", "card"), ("text_dim", "panel"),       # secundários
        ("selection_text", "selection"),
        ("on_accent", "accent"),
        ("placeholder", "input_bg"),                        # ≥ 2.0 basta p/ hint
    )

    def test_contraste_dark(self):
        p = theme.PALETTES["dark"]
        self.assertGreaterEqual(theme.contrast_ratio(p["text"], p["bg"]), 4.5)
        self.assertGreaterEqual(theme.contrast_ratio(p["text"], p["card"]), 4.5)
        self.assertGreaterEqual(theme.contrast_ratio(p["text"], p["panel"]), 4.5)
        self.assertGreaterEqual(theme.contrast_ratio(p["text"], p["input_bg"]), 4.5)
        self.assertGreaterEqual(theme.contrast_ratio(p["text_dim"], p["card"]), 4.5)
        self.assertGreaterEqual(theme.contrast_ratio(p["text_dim"], p["panel"]), 4.5)
        self.assertGreaterEqual(theme.contrast_ratio(p["selection_text"], p["selection"]), 3.0)
        self.assertGreaterEqual(theme.contrast_ratio(p["on_accent"], p["accent"]), 3.0)
        self.assertGreaterEqual(theme.contrast_ratio(p["placeholder"], p["input_bg"]), 2.0)
        self.assertGreaterEqual(theme.contrast_ratio(p["text_disabled"], p["panel"]), 3.0)

    def test_contraste_light(self):
        p = theme.PALETTES["light"]
        self.assertGreaterEqual(theme.contrast_ratio(p["text"], p["bg"]), 4.5)
        self.assertGreaterEqual(theme.contrast_ratio(p["text"], p["card"]), 4.5)
        self.assertGreaterEqual(theme.contrast_ratio(p["text"], p["panel"]), 4.5)
        self.assertGreaterEqual(theme.contrast_ratio(p["text"], p["input_bg"]), 4.5)
        self.assertGreaterEqual(theme.contrast_ratio(p["text_dim"], p["card"]), 4.5)
        self.assertGreaterEqual(theme.contrast_ratio(p["text_dim"], p["panel"]), 4.5)
        self.assertGreaterEqual(theme.contrast_ratio(p["selection_text"], p["selection"]), 3.0)
        self.assertGreaterEqual(theme.contrast_ratio(p["on_accent"], p["accent"]), 3.0)
        self.assertGreaterEqual(theme.contrast_ratio(p["placeholder"], p["input_bg"]), 2.0)
        self.assertGreaterEqual(theme.contrast_ratio(p["text_disabled"], p["panel"]), 3.0)

    def test_cores_de_tipo_legiveis_nos_dois_temas(self):
        for kind in ("filme", "serie", "radio", "esporte", "youtube", "canal"):
            for t, bg in (("dark", theme.PALETTES["dark"]["card"]),
                          ("light", theme.PALETTES["light"]["card"])):
                r = theme.contrast_ratio(theme.type_color(kind, t), bg)
                self.assertGreaterEqual(r, 3.0,
                                        f"{kind} no tema {t}: contraste {r:.2f}")


class TestCoberturaQSS(unittest.TestCase):
    """O QSS precisa cobrir TODOS os componentes pedidos na auditoria."""

    SELETORES_OBRIGATORIOS = [
        "QLabel", "QPushButton", "QLineEdit", "QTextEdit", "QPlainTextEdit",
        "QTextBrowser", "QComboBox", "QCheckBox", "QRadioButton",
        "QTabWidget", "QTableWidget", "QTableView", "QListWidget",
        "QHeaderView", "QMenu", "QDialog", "QToolTip", "QSpinBox",
        "QProgressBar", "QScrollBar", "QMainWindow",
    ]

    ESTADOS_OBRIGATORIOS = [":hover", ":disabled", ":focus", ":selected",
                            ":checked", ":pressed"]

    def test_seletores_presentes(self):
        for tema in ("dark", "light"):
            qss = theme.build_qss(tema)
            for sel in self.SELETORES_OBRIGATORIOS:
                self.assertIn(sel, qss, f"{sel} ausente no tema {tema}")

    def test_estados_presentes(self):
        for tema in ("dark", "light"):
            qss = theme.build_qss(tema)
            for est in self.ESTADOS_OBRIGATORIOS:
                self.assertIn(est, qss, f"{est} ausente no tema {tema}")

    def test_sem_cor_fixa_no_qss(self):
        """QSS deve usar apenas cores vindas da paleta (nenhum #hex solto)."""
        for tema in ("dark", "light"):
            qss = theme.build_qss(tema)
            palette_hex = {v.lower() for v in theme.PALETTES[tema].values()}
            soltos = [h.lower() for h in re.findall(r"#[0-9A-Fa-f]{6}\b", qss)
                      if h.lower() not in palette_hex]
            self.assertEqual(soltos, [],
                             f"tema {tema}: cores fora da paleta: {soltos}")

    def test_cores_diferentes_por_tema(self):
        d, l = theme.PALETTES["dark"], theme.PALETTES["light"]
        self.assertNotEqual(d["bg"], l["bg"])
        self.assertNotEqual(d["text"], l["text"])

    def test_app_palette_disponivel(self):
        import os
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PySide6.QtGui import QPalette
        from PySide6.QtWidgets import QApplication
        QApplication.instance() or QApplication([])
        pal = theme.app_palette("light")
        self.assertIsNotNone(pal.color(QPalette.PlaceholderText))
        pal2 = theme.app_palette("dark")
        self.assertIsNotNone(pal2.color(QPalette.PlaceholderText))


class TestTemaAtivo(unittest.TestCase):
    def test_set_e_current(self):
        theme.set_theme("light")
        self.assertEqual(theme.current(), "light")
        theme.set_theme("dark")
        self.assertEqual(theme.current(), "dark")
        theme.set_theme("inexistente")
        self.assertEqual(theme.current(), "dark")


if __name__ == "__main__":
    unittest.main()
