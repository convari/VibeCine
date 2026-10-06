# -*- coding: utf-8 -*-
"""Testes do roteador de URLs (app.core.url_router)."""

import os
import tempfile
import unittest

from app.core.url_router import UrlKind, classify_url, is_youtube_url, validate_url


class TestUrlRouter(unittest.TestCase):
    def test_youtube(self):
        for u in ("https://www.youtube.com/watch?v=abc",
                  "https://youtu.be/abc",
                  "https://music.youtube.com/playlist?list=x"):
            self.assertEqual(classify_url(u).kind, UrlKind.YOUTUBE)
            self.assertTrue(is_youtube_url(u))

    def test_playlist_m3u(self):
        self.assertEqual(classify_url("http://lista.tv/get.php?type=m3u").kind,
                         UrlKind.GENERIC)
        self.assertEqual(classify_url("http://lista.tv/lista.m3u").kind,
                         UrlKind.M3U_PLAYLIST)
        self.assertEqual(classify_url("http://lista.tv/lista.m3u8").kind,
                         UrlKind.M3U_PLAYLIST)

    def test_stream_direto(self):
        self.assertEqual(classify_url("http://x.tv/filme.mp4").kind,
                         UrlKind.DIRECT_STREAM)
        self.assertEqual(classify_url("http://x.tv/musica.mp3?t=1").kind,
                         UrlKind.DIRECT_STREAM)

    def test_outros_sites_vao_para_generic(self):
        self.assertEqual(classify_url("https://vimeo.com/12345").kind, UrlKind.GENERIC)

    def test_invalidas(self):
        for u in ("", "   ", "Cena final do filme", "http://", "ftp://x/a.m3u"):
            routed = classify_url(u)
            self.assertEqual(routed.kind, UrlKind.INVALID, msg=u)
            self.assertTrue(routed.message)

    def test_validate_url(self):
        self.assertFalse(validate_url("")[0])
        self.assertFalse(validate_url("texto solto")[0])
        self.assertTrue(validate_url("https://exemplo.com/lista.m3u")[0])

    def test_arquivo_local(self):
        with tempfile.NamedTemporaryFile(suffix=".m3u", delete=False) as fh:
            fh.write(b"#EXTM3U\n")
            path = fh.name
        try:
            routed = classify_url(path)
            self.assertEqual(routed.kind, UrlKind.LOCAL_FILE)
            self.assertTrue(os.path.isfile(routed.local_path))
            routed2 = classify_url("file://" + path)
            self.assertEqual(routed2.kind, UrlKind.LOCAL_FILE)
        finally:
            os.unlink(path)


if __name__ == "__main__":
    unittest.main()
