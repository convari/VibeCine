# -*- coding: utf-8 -*-
"""Testes do parser M3U (app.core.m3u_parser)."""

import unittest

from app.core.m3u_parser import (
    decode_playlist, detect_type, entry_for_direct_url, parse_m3u,
)


SAMPLE = """#EXTM3U
#EXTINF:-1 tvg-id="globo.br" tvg-logo="http://x/g.png" group-title="Canais Abertos",Globo HD
http://provider.tv/live/globo.m3u8
#EXTINF:-1 tvg-name="Matrix" group-title="Filmes Ação",Matrix
http://provider.tv/movie/matrix.mp4
#EXTGRP:Esportes
#EXTINF:-1 tvg-id="espn",ESPN
http://provider.tv/live/espn.m3u8
"""


class TestParseM3U(unittest.TestCase):
    def test_parsing_basico(self):
        entries = parse_m3u(SAMPLE)
        self.assertEqual(len(entries), 3)
        e = entries[0]
        self.assertEqual(e["title"], "Globo HD")
        self.assertEqual(e["group"], "Canais Abertos")
        self.assertEqual(e["logo"], "http://x/g.png")
        self.assertEqual(e["tvg_id"], "globo.br")
        self.assertEqual(e["url"], "http://provider.tv/live/globo.m3u8")

    def test_extgrp_fallback(self):
        entries = parse_m3u(SAMPLE)
        espn = [e for e in entries if e["title"] == "ESPN"][0]
        self.assertEqual(espn["group"], "Esportes")

    def test_atributos_sem_aspas(self):
        content = '#EXTINF:-1 tvg-id=abc group-title=Filmes,Filme X\nhttp://x/a.mp4\n'
        entries = parse_m3u(content)
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["tvg_id"], "abc")
        self.assertEqual(entries[0]["group"], "Filmes")

    def test_titulo_vem_do_tvg_name_quando_ausente(self):
        content = '#EXTINF:-1 tvg-name="Canal Y",\nhttp://x/y.m3u8\n'
        entries = parse_m3u(content)
        self.assertEqual(entries[0]["title"], "Canal Y")

    def test_extinf_sem_url_nao_trava_proximo_item(self):
        content = (
            '#EXTINF:-1 group-title="X",Item Sem URL\n'
            '#EXTINF:-1 group-title="Y",Item Com URL\n'
            'http://x/ok.m3u8\n'
        )
        entries = parse_m3u(content)
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["title"], "Item Com URL")
        self.assertEqual(entries[0]["group"], "Y")

    def test_diretivas_ignoradas(self):
        content = (
            '#EXTM3U\n#EXTVLCOPT:http-user-agent=Agent\n#KODIPROP:xx\n'
            '#EXTINF:-1,T\nhttp://x/t.m3u8\n'
        )
        entries = parse_m3u(content)
        self.assertEqual(len(entries), 1)

    def test_manifest_hls_nao_gera_entradas(self):
        content = ("#EXTM3U\n#EXT-X-STREAM-INF:BANDWIDTH=1000\n"
                   "http://x/variant.m3u8\n")
        self.assertEqual(parse_m3u(content), [])

    def test_decode_latin1(self):
        data = "#EXTINF:-1,Animação\nhttp://x/a.mp4\n".encode("iso-8859-1")
        text = decode_playlist(data)
        self.assertIn("Animação", text)

    def test_detect_type(self):
        self.assertEqual(detect_type("Filmes Ação", "Matrix"), "filme")
        self.assertEqual(detect_type("Séries", "Breaking Bad"), "serie")
        self.assertEqual(detect_type("Rádio FM", ""), "radio")
        self.assertEqual(detect_type("Canais", "Futebol ao vivo"), "esporte")
        self.assertEqual(detect_type("Abertos", "Globo"), "canal")

    def test_entry_for_direct_url(self):
        e = entry_for_direct_url("http://x/pasta/meu%20video.mp4?token=1")
        self.assertEqual(e["url"], "http://x/pasta/meu%20video.mp4?token=1")
        self.assertTrue(e["title"])


if __name__ == "__main__":
    unittest.main()
