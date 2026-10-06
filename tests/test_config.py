# -*- coding: utf-8 -*-
"""Testes de configuração (app.core.config)."""

import json
import os
import tempfile
import unittest

from app.core.config import (DEFAULT_CONFIG, load_config, save_config,
                             validate_config)


class TestConfig(unittest.TestCase):
    def test_padrao_nao_e_mp3(self):
        self.assertEqual(DEFAULT_CONFIG["format"], "original")

    def test_formato_invalido_volta_para_original(self):
        cfg = validate_config({"format": "avi"})
        self.assertEqual(cfg["format"], "original")

    def test_chaves_ausentes_preenchidas(self):
        cfg = validate_config({"download_folder": "X"})
        for key in DEFAULT_CONFIG:
            self.assertIn(key, cfg)
        self.assertEqual(cfg["download_folder"], "X")

    def test_migracao_caminhos(self):
        cfg = validate_config({"ffmpeg_path": "ffmpeg", "ytdlp_path": "yt-dlp"})
        self.assertEqual(cfg["ffmpeg_path"], "ffmpeg.exe")
        self.assertEqual(cfg["ytdlp_path"], "yt-dlp.exe")

    def test_speed_limit_invalido(self):
        self.assertEqual(validate_config({"speed_limit": "rapido"})["speed_limit"], "0")
        self.assertEqual(validate_config({"speed_limit": "30M"})["speed_limit"], "30M")

    def test_roundtrip_json(self):
        with tempfile.TemporaryDirectory() as td:
            path = os.path.join(td, "config.json")
            save_config({"download_folder": "D:/videos", "format": "mp4"}, path)
            cfg = load_config(path)
            self.assertEqual(cfg["download_folder"], "D:/videos")
            self.assertEqual(cfg["format"], "mp4")

    def test_json_corrompido_usa_defaults(self):
        with tempfile.TemporaryDirectory() as td:
            path = os.path.join(td, "config.json")
            with open(path, "w") as fh:
                fh.write("{não é json")
            cfg = load_config(path)
            self.assertEqual(cfg, DEFAULT_CONFIG)

    def test_config_antiga_com_mp3_e_preservada(self):
        # A escolha explícita de MP3 pelo usuário deve ser respeitada.
        with tempfile.TemporaryDirectory() as td:
            path = os.path.join(td, "config.json")
            with open(path, "w", encoding="utf-8") as fh:
                json.dump({"format": "mp3"}, fh)
            self.assertEqual(load_config(path)["format"], "mp3")


if __name__ == "__main__":
    unittest.main()
