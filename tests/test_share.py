# -*- coding: utf-8 -*-
"""Testes do sistema de compartilhamento (app.core.share + diálogo Qt)."""

import os
import urllib.parse
import unittest

from app.core.share import (APP_NAME, build_share_links, build_share_message,
                            canonical_youtube_url, is_sensitive_url,
                            make_qr_png_bytes, plan_share, url_has_credentials,
                            url_has_sensitive_params)

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


def entry(url, kind="filme", title="Matrix", tvg_id=""):
    return {"title": title, "group": "Filmes", "logo": "", "tvg_id": tvg_id,
            "tvg_name": title, "url": url, "type": kind}


SAFE_URL = "http://provedor.tv/filmes/matrix.mp4"
SENSITIVE_URL = "http://user:senha123@provedor.tv/live/x?token=abc456"


class TestSegurancaDeUrl(unittest.TestCase):
    def test_credenciais(self):
        self.assertTrue(url_has_credentials("http://user:pass@h.tv/x"))
        self.assertFalse(url_has_credentials(SAFE_URL))

    def test_parametros_sensiveis(self):
        self.assertTrue(url_has_sensitive_params("http://h.tv/x?token=abc"))
        self.assertTrue(url_has_sensitive_params("http://h.tv/x?Password=1"))
        self.assertFalse(url_has_sensitive_params("http://h.tv/x?tipo=m3u"))

    def test_is_sensitive(self):
        self.assertTrue(is_sensitive_url(SENSITIVE_URL))
        self.assertFalse(is_sensitive_url(SAFE_URL))


class TestPlanShare(unittest.TestCase):
    def test_url_limpa_e_compartilhavel(self):
        plan = plan_share(entry(SAFE_URL))
        self.assertTrue(plan.shareable)
        self.assertEqual(plan.url, SAFE_URL)

    def test_sensivel_bloqueada_com_referencia(self):
        plan = plan_share(entry(SENSITIVE_URL))
        self.assertFalse(plan.shareable)
        self.assertIn("credenciais", plan.reason)
        self.assertTrue(plan.safe_reference)
        self.assertNotIn("senha123", plan.safe_reference)
        self.assertNotIn("abc456", plan.safe_reference)

    def test_youtube_prioriza_pagina(self):
        e = entry("https://youtu.be/dQw4w9WgXcQ", kind="youtube",
                  tvg_id="dQw4w9WgXcQ")
        plan = plan_share(e)
        self.assertTrue(plan.shareable)
        self.assertEqual(plan.url,
                         "https://www.youtube.com/watch?v=dQw4w9WgXcQ")

    def test_canonical_youtube(self):
        self.assertEqual(
            canonical_youtube_url(entry("https://youtu.be/ABC123",
                                        kind="youtube", tvg_id="ABC123")),
            "https://www.youtube.com/watch?v=ABC123")
        self.assertEqual(
            canonical_youtube_url(entry("https://www.youtube.com/watch?v=Z9")),
            "https://www.youtube.com/watch?v=Z9")

    def test_sem_url(self):
        plan = plan_share(entry(""))
        self.assertFalse(plan.shareable)


class TestMensagem(unittest.TestCase):
    def test_conteudo_padrao(self):
        msg = build_share_message(entry(SAFE_URL, title="Matrix"), SAFE_URL)
        self.assertIn("Matrix", msg)
        self.assertIn("Filme", msg)
        self.assertIn(SAFE_URL, msg)
        self.assertIn(APP_NAME, msg)

    def test_nunca_vaza_credenciais(self):
        plan = plan_share(entry(SENSITIVE_URL))
        self.assertFalse(plan.shareable)  # nenhuma mensagem é montada
        if plan.shareable:
            self.fail("mensagem não deveria existir para URL sensível")


class TestShareLinks(unittest.TestCase):
    def setUp(self):
        self.msg = build_share_message(entry(SAFE_URL, title="Ação & Aventura"),
                                       SAFE_URL)
        self.links = build_share_links(self.msg, SAFE_URL)

    def test_plataformas(self):
        for key, domain in (("whatsapp", "wa.me"), ("telegram", "t.me"),
                            ("facebook", "facebook.com/sharer"),
                            ("x", "twitter.com/intent/tweet")):
            self.assertTrue(self.links[key].startswith("https://"), key)
            self.assertIn(domain, self.links[key], key)
        self.assertTrue(self.links["email"].startswith("mailto:"))

    def test_encoding(self):
        # '&' do título deve estar percent-encoded dentro do parâmetro
        self.assertIn("%26", self.links["whatsapp"])
        self.assertNotIn("Ação & Aventura", self.links["whatsapp"])
        # decodificando, recupera a mensagem original
        parsed = urllib.parse.urlsplit(self.links["whatsapp"])
        qs = urllib.parse.parse_qs(parsed.query)
        self.assertEqual(qs["text"][0], self.msg)

    def test_sem_credenciais_nos_links(self):
        joined = " ".join(self.links.values())
        self.assertNotIn("senha", joined)
        self.assertNotIn("token=", joined)


class TestQrCode(unittest.TestCase):
    def test_png_valido(self):
        data = make_qr_png_bytes("https://youtu.be/dQw4w9WgXcQ")
        self.assertTrue(data.startswith(b"\x89PNG"))
        self.assertGreater(len(data), 200)

    def test_png_abre_com_pillow(self):
        from io import BytesIO
        from PIL import Image
        img = Image.open(BytesIO(make_qr_png_bytes("teste-qr")))
        img.verify()


class TestShareDialogQt(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PySide6.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication([])

    def test_dialogo_compartilhavel(self):
        from PySide6.QtWidgets import QPushButton
        from app.ui.widgets.share_dialog import ShareDialog
        dlg = ShareDialog(entry(SAFE_URL))
        buttons = " ".join(b.text() for b in dlg.findChildren(QPushButton))
        for esperado in ("WhatsApp", "Telegram", "Facebook", "X",
                         "E-mail", "Copiar link", "QR Code"):
            self.assertIn(esperado, buttons)
        dlg.deleteLater()

    def test_dialogo_sensivel_nao_oferece_redes(self):
        from PySide6.QtWidgets import QPushButton
        from app.ui.widgets.share_dialog import ShareDialog
        dlg = ShareDialog(entry(SENSITIVE_URL))
        buttons = " ".join(b.text() for b in dlg.findChildren(QPushButton))
        self.assertIn("referência segura", buttons.lower())
        self.assertNotIn("WhatsApp", buttons)
        dlg.deleteLater()

    def test_copiar_link_usa_url_segura(self):
        from PySide6.QtWidgets import QApplication
        dlg_entry = entry(SAFE_URL)
        from app.ui.widgets.share_dialog import ShareDialog
        dlg = ShareDialog(dlg_entry)
        dlg._copy_link()
        self.assertEqual(QApplication.clipboard().text(), SAFE_URL)
        dlg.deleteLater()

    def test_qr_gerado_na_ui(self):
        from app.ui.widgets.share_dialog import ShareDialog
        dlg = ShareDialog(entry(SAFE_URL))
        dlg._show_qr()
        self.assertTrue(dlg.qr_area is not None)
        self.assertIsNotNone(dlg._qr_bytes)
        dlg.deleteLater()


if __name__ == "__main__":
    unittest.main()
