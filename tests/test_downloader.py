# -*- coding: utf-8 -*-
"""Testes do downloader: nomes, comando e parser de progresso."""

import unittest

from app.core.downloader import (build_ytdlp_command, output_dir_for,
                                 parse_progress_line, sanitize_filename,
                                 _size_to_bytes)


CFG = {
    "download_folder": "C:/FILMES",
    "ffmpeg_path": "ffmpeg.exe",
    "ytdlp_path": "yt-dlp.exe",
    "deno_path": "deno.exe",
    "organize_by_group": True,
    "speed_limit": "10M",
    "format": "original",
}
ENTRY = {"title": "Meu Filme: A Missão?", "group": "Filmes/Ação",
         "url": "http://x/f.mp4", "logo": "", "tvg_id": "",
         "tvg_name": "", "type": "filme"}


class TestFilenames(unittest.TestCase):
    def test_sanitize(self):
        self.assertEqual(sanitize_filename('A/B:C*D?"E'), "A_B_C_D__E")
        s = sanitize_filename('A/B:C*D?"E')
        for ch in '<>:"/\\|?*\n\r':
            self.assertNotIn(ch, s)

    def test_truncamento(self):
        s = sanitize_filename("x" * 500)
        self.assertLessEqual(len(s), 80)

    def test_vazio(self):
        self.assertEqual(sanitize_filename("   "), "download")

    def test_output_dir_por_grupo(self):
        d = output_dir_for("C:/F", ENTRY, True)
        self.assertIn("Filmes_Ação", d.replace("\\", "/"))
        self.assertEqual(output_dir_for("C:/F", ENTRY, False), "C:/F")


class TestCommand(unittest.TestCase):
    def test_comando_original(self):
        cmd, ctx = build_ytdlp_command(ENTRY, CFG)
        self.assertIn("--no-playlist", cmd)
        self.assertIn("--limit-rate", cmd)
        self.assertIn("10M", cmd)
        self.assertIn("bv*+ba/b", cmd)
        self.assertIn("--continue", cmd)
        self.assertTrue(cmd[-1].endswith("f.mp4") or cmd[-1] == ENTRY["url"])

    def test_formato_mp3_explicito(self):
        cmd, _ = build_ytdlp_command(ENTRY, {**CFG, "format": "mp3"})
        self.assertIn("--audio-format", cmd)
        self.assertIn("mp3", cmd)

    def test_sem_limite_de_velocidade(self):
        cmd, _ = build_ytdlp_command(ENTRY, {**CFG, "speed_limit": "0"})
        self.assertNotIn("--limit-rate", cmd)

    def test_aviso_sem_deno(self):
        # deno.exe não existe na pasta do projeto durante os testes
        cmd, ctx = build_ytdlp_command(ENTRY, {**CFG, "deno_path": "inexistente-xyz.exe"})
        if not any("deno" in a for a in cmd):
            self.assertTrue(any("Deno" in w for w in ctx["warnings"]))


class TestProgress(unittest.TestCase):
    def test_linha_completa(self):
        p = parse_progress_line(
            "[download]  45.2% of ~120.50MiB at    3.20MiB/s ETA 00:12")
        self.assertIsNotNone(p)
        self.assertAlmostEqual(p["percent"], 45.2)
        self.assertGreater(p["total_bytes"], 100_000_000)
        self.assertIn("MiB/s", p["speed"])
        self.assertEqual(p["eta"], "00:12")

    def test_linha_parcial(self):
        p = parse_progress_line("[download]  10.0%")
        self.assertIsNotNone(p)
        self.assertEqual(p["percent"], 10.0)

    def test_linhas_que_nao_sao_progresso(self):
        for line in ("[youtube] Extracing URL", "", "[Merger] Merging formats"):
            self.assertIsNone(parse_progress_line(line))

    def test_size_to_bytes(self):
        self.assertEqual(_size_to_bytes("1KiB"), 1024)
        self.assertAlmostEqual(_size_to_bytes("2.5MiB"), 2.5 * 1024 ** 2)
        self.assertEqual(_size_to_bytes(""), 0.0)


if __name__ == "__main__":
    unittest.main()
