# -*- coding: utf-8 -*-
"""Smoke test: fluxo de ponta a ponta do extrator (sem interface).

Uso: python tests/smoke_extractor.py
"""

import os
import sys
import tempfile

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.core.extractor import ExtractorError, extract_entries  # noqa: E402
from app.core.config import load_config  # noqa: E402


def main() -> int:
    cfg = load_config()

    # 1) Playlist local via extract_entries (fluxo completo do roteador)
    sample = ("#EXTM3U\n"
              '#EXTINF:-1 group-title="Filmes",Matrix\n'
              "http://x/movie/matrix.mp4\n"
              "#EXTGRP:Canais\n"
              "#EXTINF:-1,Globo\n"
              "http://x/live/globo.m3u8\n")
    with tempfile.NamedTemporaryFile("w", suffix=".m3u", delete=False, encoding="utf-8") as fh:
        fh.write(sample)
        path = fh.name
    entries = extract_entries(path, cfg)
    assert len(entries) == 2, entries
    assert entries[0]["type"] == "filme" and entries[1]["group"] == "Canais"
    print("1. playlist local OK:", [e["title"] for e in entries])
    os.unlink(path)

    # 2) URL invalida -> erro amigavel
    try:
        extract_entries("isto nao e url", cfg)
        raise SystemExit("deveria ter falhado")
    except ExtractorError as e:
        print("2. URL invalida OK:", e.code, "->", e.friendly[:60])

    # 3) Stream direto
    e = extract_entries("http://x.tv/video.mp4", cfg)
    assert e[0]["group"] == "Links Diretos"
    print("3. stream direto OK:", e[0]["title"])

    # 4) Manifest HLS puro reclassificado como video unico
    hls = "#EXTM3U\n#EXT-X-STREAM-INF:BANDWIDTH=800000\nhttp://x/v.m3u8\n"
    with tempfile.NamedTemporaryFile("w", suffix=".m3u8", delete=False, encoding="utf-8") as fh:
        fh.write(hls)
        path = fh.name
    e = extract_entries(path, cfg)
    assert e[0]["group"] == "Links Diretos", e
    print("4. manifest HLS OK:", e[0]["title"])
    os.unlink(path)

    # 5) Playlist vazia remota nao e confundida (arquivo local vazio)
    with tempfile.NamedTemporaryFile("w", suffix=".m3u", delete=False, encoding="utf-8") as fh:
        fh.write("#EXTM3U\n")
        path = fh.name
    try:
        extract_entries(path, cfg)
        raise SystemExit("deveria ter falhado com empty_playlist")
    except ExtractorError as e:
        assert e.code == "empty_playlist", e.code
        print("5. playlist vazia OK:", e.friendly[:60])
    os.unlink(path)

    print("\nSMOKE TEST: todos os cenarios passaram.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
