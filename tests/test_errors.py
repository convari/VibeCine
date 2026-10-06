# -*- coding: utf-8 -*-
"""Testes da classificação de erros (app.core.errors)."""

import socket
import unittest
import urllib.error

from app.core.errors import classify_exception, user_message


class TestErrors(unittest.TestCase):
    def code(self, exc):
        return classify_exception(exc)[0]

    def test_http_403(self):
        exc = urllib.error.HTTPError("http://x", 403, "Forbidden", {}, None)
        self.assertEqual(self.code(exc), "forbidden")

    def test_http_404(self):
        exc = urllib.error.HTTPError("http://x", 404, "Not Found", {}, None)
        self.assertEqual(self.code(exc), "not_found")

    def test_http_500(self):
        exc = urllib.error.HTTPError("http://x", 502, "Bad Gateway", {}, None)
        self.assertEqual(self.code(exc), "server_error")

    def test_dns(self):
        exc = urllib.error.URLError(socket.gaierror(-2, "Name or service not known"))
        self.assertEqual(self.code(exc), "dns_error")

    def test_timeout(self):
        self.assertEqual(self.code(TimeoutError()), "timeout")
        exc = urllib.error.URLError(TimeoutError("timed out"))
        self.assertEqual(self.code(exc), "timeout")

    def test_arquivo(self):
        self.assertEqual(self.code(FileNotFoundError("nada")), "file_not_found")
        self.assertEqual(self.code(PermissionError("negado")), "permission")

    def test_desconhecido(self):
        self.assertEqual(self.code(RuntimeError("boom")), "unknown")

    def test_mensagem_amigavel_em_portugues(self):
        exc = urllib.error.HTTPError("http://x", 403, "Forbidden", {}, None)
        self.assertIn("expirado", user_message(exc).lower())


if __name__ == "__main__":
    unittest.main()
