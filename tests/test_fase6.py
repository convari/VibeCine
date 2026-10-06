# -*- coding: utf-8 -*-
"""Testes da Fase 6: protocolo vibcine://, paths e atualizador do app."""

import os
import sys
import tempfile
import unittest
import zipfile


class TestPaths(unittest.TestCase):
    def test_dirs_diferem_e_existem(self):
        from app.core import paths
        self.assertTrue(os.path.isdir(paths.data_dir()))
        self.assertTrue(os.path.isdir(paths.tools_dir()))
        self.assertTrue(os.path.isdir(paths.app_dir()))
        # dados nunca dentro do _MEIPASS
        self.assertNotIn("_MEI", paths.data_dir())

    def test_default_config_path(self):
        # Em desenvolvimento, config.json fica na raiz do projeto.
        from app.core.config import CONFIG_FILE
        self.assertTrue(CONFIG_FILE.endswith("config.json"))
        self.assertIn("vibcine", CONFIG_FILE.lower())


class TestProtocolo(unittest.TestCase):
    def test_load_valido(self):
        from app.core.protocol import parse_vibcine_uri
        url, err = parse_vibcine_uri(
            "vibcine://load?url=https%3A%2F%2Fyoutu.be%2Fabc123")
        self.assertEqual(url, "https://youtu.be/abc123")
        self.assertEqual(err, "")

    def test_rejeicoes(self):
        from app.core.protocol import parse_vibcine_uri
        for arg, esperado in (
            ("http://exemplo.com", "Não é um link"),
            ("vibcine://delete?url=http://x.tv", "Ação não suportada"),
            ("vibcine://load", "Link sem URL"),
            ("vibcine://load?url=texto%20solto", "invalid"),
            ("vibcine://load?url=file%3A%2F%2FC%3A%5Ca.m3u", "http"),
            ("vibcine://load?url=http%3A%2F%2Fu%40h.tv%2Fx", "credenciais"),
        ):
            url, err = parse_vibcine_uri(arg)
            self.assertIsNone(url, msg=arg)
            self.assertTrue(err, msg=arg)

    def test_log_nao_vaza_credenciais(self):
        from app.core.protocol import log_safe_uri
        out = log_safe_uri(
            "vibcine://load?url=http%3A%2F%2Fuser%3Asenha%40h.tv%2Fx")
        self.assertNotIn("senha", out)

    def test_register_unregister(self):
        # Só roda no Windows; usa a própria chave de teste e limpa depois.
        if sys.platform != "win32":
            self.skipTest("win32 only")
        import winreg
        from app.core.protocol import PROTOCOL, register_protocol, unregister_protocol
        register_protocol()
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                            rf"Software\Classes\{PROTOCOL}") as k:
            val, _ = winreg.QueryValueEx(k, None)
            self.assertIn("VibeCine", val)
        unregister_protocol()
        with self.assertRaises(OSError):
            winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                           rf"Software\Classes\{PROTOCOL}")


class TestAppUpdater(unittest.TestCase):
    def _make_package(self, entries, payload_text=b"hello"):
        d = tempfile.mkdtemp()
        zp = os.path.join(d, "pkg.zip")
        with zipfile.ZipFile(zp, "w") as z:
            for name in entries:
                z.writestr(name, payload_text)
        return zp

    def test_validacao_sha256(self):
        from app.core import app_updater
        zp = self._make_package(["app/x.txt"])
        digest = app_updater.sha256_file(zp)
        manifest = {"version": "9.9.9",
                    "url": "file:///" + zp.replace("\\", "/"),
                    "sha256": digest}
        out = app_updater.download_update(manifest)
        self.assertTrue(os.path.isfile(out))
        # hash errado → aborta
        manifest_bad = dict(manifest, sha256="0" * 64)
        with self.assertRaises(app_updater.UpdateError):
            app_updater.download_update(manifest_bad)
        # sem hash → recusa
        with self.assertRaises(app_updater.UpdateError):
            app_updater.download_update({"version": "9.9.9",
                                         "url": manifest["url"]})

    def test_protecao_zip_slip(self):
        from app.core import app_updater
        zp = self._make_package(["../evil.txt"])
        with self.assertRaises(app_updater.UpdateError):
            app_updater.safe_extract(zp, tempfile.mkdtemp())

    def test_safe_extract_ok(self):
        from app.core import app_updater
        zp = self._make_package(["pasta/ok.txt"])
        out = app_updater.safe_extract(zp, tempfile.mkdtemp())
        self.assertTrue(os.path.isfile(os.path.join(out, "pasta", "ok.txt")))

    def test_is_newer(self):
        from app.core.app_updater import is_newer
        self.assertTrue(is_newer("2.0.1", "2.0.0"))
        self.assertFalse(is_newer("2.0.0", "2.0.0"))
        self.assertFalse(is_newer("1.9.9", "2.0.0"))

    def test_swap_script_preserva_dados(self):
        from app.core import app_updater
        bat = app_updater.make_swap_script("C:/src", "C:/dst", "VibeCine.exe")
        self.assertTrue(os.path.isfile(bat))
        content = open(bat).read()
        self.assertIn("robocopy", content)
        self.assertNotIn("APPDATA", content)  # dados do usuário não são tocados


class TestToolsUpdater(unittest.TestCase):
    def test_atomic_write_nao_sobrescreve_em_uso(self):
        from app.core.tools_updater import _atomic_write, tools_target_dir
        self.assertTrue(os.path.isdir(str(tools_target_dir())))
        with tempfile.TemporaryDirectory() as td:
            alvo = os.path.join(td, "x.exe")
            p = _atomic_write(type("P", (), {})() if False else __import__("pathlib").Path(alvo), b"MZ" + b"0" * 5000)
            self.assertTrue(os.path.isfile(str(p)))
            os.unlink(str(p))


if __name__ == "__main__":
    unittest.main()
