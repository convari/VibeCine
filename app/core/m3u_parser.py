# -*- coding: utf-8 -*-
"""Parser de playlists M3U/M3U8 (IPTV).

Melhorias em relação à versão original:
- suporta #EXTGRP como fallback de grupo;
- atributos com ou sem aspas (tvg-id=logo vs tvg-id="logo");
- detecção de encoding (UTF-8 com fallback para Latin-1, comum em listas BR);
- ignora diretivas como #EXTVLCOPT, #KODIPROP etc. sem quebrar;
- preserva o schema histórico de entrada:
  {title, group, logo, tvg_id, tvg_name, url, type}.
"""

from __future__ import annotations

import re

_ATTR_RE = re.compile(r'([\w-]+)\s*=\s*(?:"([^"]*)"|([^\s,]+))')

_TYPE_KEYWORDS = (
    # (tipo, palavras-chave) — primeira correspondência vence.
    ("filme",   ("filme", "movie", "vod", "film", "cinema")),
    ("serie",   ("serie", "série", "series", "show", "temporada", "season", "episode", "episódio", "episodio")),
    ("radio",   ("radio", "rádio", "music", "musica", "música", "fm ", " fm", "am ")),
    ("esporte", ("sport", "esport", "futebol", "football", "soccer", "nba", "nfl")),
)
DEFAULT_TYPE = "canal"


def detect_type(group: str, title: str) -> str:
    """Classifica o conteúdo pelo grupo/título (palavras-chave)."""
    combined = f"{group} {title}".lower()
    for kind, keywords in _TYPE_KEYWORDS:
        if any(k in combined for k in keywords):
            return kind
    return DEFAULT_TYPE


def decode_playlist(data: bytes) -> str:
    """Decodifica bytes da playlist com fallback de encoding.

    UTF-8 (com ou sem BOM) primeiro; se falhar, Latin-1 — frequente em
    listas IPTV brasileiras antigas.
    """
    for enc in ("utf-8-sig", "utf-8", "iso-8859-1"):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")


def _parse_extinf(line: str) -> dict:
    entry = {
        "title": "",
        "group": "Sem Grupo",
        "logo": "",
        "tvg_id": "",
        "tvg_name": "",
        "url": "",
        "type": DEFAULT_TYPE,
    }

    comma = line.rfind(",")
    if comma != -1:
        entry["title"] = line[comma + 1:].strip()

    for match in _ATTR_RE.finditer(line):
        key, val = match.group(1).lower(), match.group(2) if match.group(2) is not None else (match.group(3) or "")
        if key in ("tvg-id", "tvg_id"):
            entry["tvg_id"] = val
        elif key in ("tvg-name", "tvg_name"):
            entry["tvg_name"] = val
        elif key in ("tvg-logo", "tvg_logo"):
            entry["logo"] = val
        elif key in ("group-title", "group_title"):
            entry["group"] = val.strip() or "Sem Grupo"

    if not entry["title"] and entry["tvg_name"]:
        entry["title"] = entry["tvg_name"]

    return entry


def iter_m3u_batches(content: str, batch_size: int = 200):
    """Gerador incremental: produz lotes de entradas (default: 200/lote).

    Usado pela UI para alimentar o modelo de dados de forma incremental,
    cedendo ao event loop entre os lotes. `parse_m3u` é mantido e agora é
    um simples agregador deste gerador (mesmo resultado final).
    """
    lines = content.splitlines()
    pending_group = ""  # grupo vindo de #EXTGRP
    batch: list[dict] = []
    i = 0
    while i < len(lines):
        line = lines[i].strip()

        if line.startswith("#EXTGRP:"):
            pending_group = line[len("#EXTGRP:"):].strip()
            i += 1
            continue

        if line.startswith("#EXTINF:"):
            entry = _parse_extinf(line)
            if entry["group"] == "Sem Grupo" and pending_group:
                entry["group"] = pending_group

            # Procura a URL nas linhas seguintes.
            i += 1
            while i < len(lines):
                url_line = lines[i].strip()
                if not url_line:
                    i += 1
                    continue
                if url_line.startswith("#"):
                    if url_line.startswith("#EXTGRP:"):
                        pending_group = url_line[len("#EXTGRP:"):].strip()
                        i += 1
                    break
                entry["url"] = url_line
                i += 1
                break

            if entry["title"] and entry["url"]:
                entry["type"] = detect_type(entry["group"], entry["title"])
                batch.append(entry)
                if len(batch) >= batch_size:
                    yield batch
                    batch = []
            continue
        i += 1
    if batch:
        yield batch


def parse_m3u(content: str) -> list[dict]:
    """Interpreta o conteúdo de uma playlist M3U.

    - #EXTINF inicia um item; a próxima linha não-comentário é a URL.
    - #EXTGRP define grupo quando o #EXTINF não tem group-title.
    - Demais diretivas (#EXTM3U, #EXTVLCOPT, #KODIPROP...) são ignoradas.
    """
    entries: list[dict] = []
    for batch in iter_m3u_batches(content):
        entries.extend(batch)
    return entries


def parse_m3u_bytes(data: bytes) -> list[dict]:
    """Conveniência: bytes -> entradas (com detecção de encoding)."""
    return parse_m3u(decode_playlist(data))


def entry_for_direct_url(url: str, title: str | None = None) -> dict:
    """Cria uma entrada unitária para uma URL de stream/arquivo direto."""
    name = title or url.rstrip("/").rsplit("/", 1)[-1].split("?")[0] or url
    base = name.rsplit(".", 1)[0] if "." in name else name
    return {
        "title": base,
        "group": "Links Diretos",
        "logo": "",
        "tvg_id": "",
        "tvg_name": "",
        "url": url,
        "type": detect_type("", base),
    }
