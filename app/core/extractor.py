# -*- coding: utf-8 -*-
"""Extração de conteúdo a partir de URLs.

Responsável por transformar uma entrada (URL/caminho) em uma lista de
entradas padronizadas {title, group, logo, tvg_id, tvg_name, url, type}.

- yt-dlp é usado preferencialmente COMO BIBLIOTECA (import yt_dlp),
  com fallback automático para o subprocesso yt-dlp.exe (comportamento
  original). Isso prepara o terreno para progresso real e cancelamento
  na fase de download.
- Erros de rede passam por errors.classify_exception, gerando mensagens
  amigáveis; erros técnicos seguem disponíveis via ExtractorError.
"""

from __future__ import annotations

import json
import os
import subprocess
import threading
import time
import urllib.request

from . import errors, m3u_parser, proc as _proc, url_router
from .tools import resolve_tool_path

USER_AGENT = "M3UDownloaderPro/2.0"
FETCH_TIMEOUT = 60
YT_PROCESS_TIMEOUT = 180

try:  # yt-dlp como biblioteca (opcional nesta fase)
    import yt_dlp  # type: ignore
    YTDLP_LIB_AVAILABLE = True
except ImportError:
    yt_dlp = None
    YTDLP_LIB_AVAILABLE = False


class ExtractorError(Exception):
    """Erro de extração com mensagem amigável + código estável."""

    def __init__(self, code: str, friendly: str, technical: str = ""):
        super().__init__(friendly)
        self.code = code
        self.friendly = friendly
        self.technical = technical


# ── Rede ─────────────────────────────────────────────────────────────────────

def fetch_bytes(url: str, *, retries: int = 2, timeout: int = FETCH_TIMEOUT,
                log=lambda msg: None) -> bytes:
    """GET com retry/backoff simples e erros classificados."""
    last_exc: BaseException | None = None
    for attempt in range(retries + 1):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.read()
        except Exception as exc:  # classificado abaixo
            last_exc = exc
            if attempt < retries:
                wait = 1.5 * (attempt + 1)
                log(f"  Tentativa {attempt + 1} falhou; nova tentativa em {wait:.0f}s...")
                time.sleep(wait)
    assert last_exc is not None
    code, friendly = errors.classify_exception(last_exc, url)
    raise ExtractorError(code, friendly, str(last_exc))


def read_playlist_source(routed: url_router.RoutedUrl, log=lambda msg: None) -> str:
    """Lê o conteúdo textual da playlist (arquivo local ou remoto)."""
    if routed.kind is url_router.UrlKind.LOCAL_FILE:
        with open(routed.local_path, "rb") as fh:
            data = fh.read()
        log(f"  Arquivo lido: {len(data):,} bytes")
        return m3u_parser.decode_playlist(data)

    log("  Baixando playlist da internet...")
    data = fetch_bytes(routed.url, log=log)
    log(f"  Download concluído: {len(data):,} bytes")
    return m3u_parser.decode_playlist(data)


# ── yt-dlp: biblioteca com fallback para subprocesso ─────────────────────────

def _entry_from_ytdlp_item(item: dict, fallback_url: str) -> dict:
    vid_id = item.get("id", "")
    vid_url = (
        item.get("webpage_url")
        or item.get("original_url")
        or item.get("url")
        or (f"https://www.youtube.com/watch?v={vid_id}" if vid_id else fallback_url)
    )
    return {
        "title":    item.get("title") or vid_id or "Sem título",
        "group":    item.get("channel") or item.get("uploader") or "YouTube",
        "logo":     item.get("thumbnail", "") or "",
        "tvg_id":   vid_id,
        "tvg_name": item.get("title", "") or "",
        "url":      vid_url,
        "type":     "youtube",
    }


def _extract_with_lib(url: str, log=lambda msg: None,
                      cancel: threading.Event | None = None) -> list[dict]:
    opts = {
        "extract_flat": True,
        "quiet": True,
        "no_warnings": True,
        "noplaylist": False,
        "ignoreerrors": True,
    }
    entries: list[dict] = []
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=False)
    if not info:
        return entries
    items = info.get("entries") or [info]
    for item in items:
        if cancel is not None and cancel.is_set():
            break
        if item:
            entries.append(_entry_from_ytdlp_item(item, url))
    return entries


def _extract_with_subprocess(url: str, ytdlp_path: str, log=lambda msg: None,
                             cancel: threading.Event | None = None) -> list[dict]:
    """Versão streaming do comportamento original (Popen linha a linha).

    Em vez de travar num timeout fixo de 120s, as entradas são processadas
    conforme o yt-dlp as emite, e o cancelamento encerra o processo.
    """
    proc = _proc.popen(
        [ytdlp_path, "--flat-playlist", "--dump-json", "--no-warnings", url],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, bufsize=1,
    )
    entries: list[dict] = []
    try:
        assert proc.stdout is not None
        for line in proc.stdout:
            if cancel is not None and cancel.is_set():
                proc.terminate()
                break
            line = line.strip()
            if not line:
                continue
            try:
                entries.append(_entry_from_ytdlp_item(json.loads(line), url))
            except (json.JSONDecodeError, TypeError):
                continue
        proc.wait(timeout=YT_PROCESS_TIMEOUT)
    except subprocess.TimeoutExpired:
        proc.kill()
        code, friendly = errors.classify_exception(TimeoutError(), url)
        raise ExtractorError(code, friendly, "yt-dlp excedeu o tempo limite")

    if proc.returncode not in (0, None) and not entries:
        err_tail = ""
        if proc.stderr is not None:
            stderr_txt = proc.stderr.read().strip()
            err_tail = stderr_txt.splitlines()[-1] if stderr_txt else ""
        raise ExtractorError(
            "ytdlp_failed",
            "O yt-dlp não conseguiu extrair o conteúdo deste link. "
            "Verifique se o link é válido e se o yt-dlp está atualizado (ATUALIZAR.bat).",
            err_tail,
        )
    return entries


def extract_media_entries(url: str, cfg: dict, log=lambda msg: None,
                          cancel: threading.Event | None = None) -> list[dict]:
    """Extrai entradas via yt-dlp (YouTube, playlists, e 1800+ sites).

    Usa a biblioteca yt_dlp quando instalada; caso contrário, o executável.
    Se nada for extraído, devolve uma entrada unitária com a URL original
    (fallback histórico), permitindo que o download decida.
    """
    if YTDLP_LIB_AVAILABLE:
        log("  Extraindo com yt-dlp (biblioteca)...")
        entries = _extract_with_lib(url, log=log, cancel=cancel)
    else:
        ytdlp = resolve_tool_path(cfg.get("ytdlp_path", "yt-dlp.exe"), "yt-dlp.exe")
        log("  Executando yt-dlp --flat-playlist (aguarde)...")
        entries = _extract_with_subprocess(url, ytdlp, log=log, cancel=cancel)

    if not entries:
        entries = [{
            "title": url,
            "group": "YouTube" if url_router.is_youtube_url(url) else "Links",
            "logo": "", "tvg_id": "", "tvg_name": "",
            "url": url,
            "type": "youtube" if url_router.is_youtube_url(url) else "canal",
        }]
    return entries


# ── Roteamento de alto nível ─────────────────────────────────────────────────

def extract_entries(raw_url: str, cfg: dict, log=lambda msg: None,
                    cancel: threading.Event | None = None) -> list[dict]:
    """Ponto único de entrada: classifica a URL e extrai as entradas.

    Levanta ExtractorError com mensagem amigável em caso de falha.
    """
    routed = url_router.classify_url(raw_url)
    if routed.kind is url_router.UrlKind.INVALID:
        raise ExtractorError("invalid_url", routed.message or "URL inválida.")
    if cancel is not None and cancel.is_set():
        raise ExtractorError("cancelled", "Carregamento cancelado.")

    log(f"▶ Carregando: {routed.url[:80]}")

    if routed.kind is url_router.UrlKind.DIRECT_STREAM:
        return [m3u_parser.entry_for_direct_url(routed.url)]

    if routed.kind in (url_router.UrlKind.LOCAL_FILE, url_router.UrlKind.M3U_PLAYLIST):
        content = read_playlist_source(routed, log=log)
        log("  Interpretando playlist (pode demorar para listas grandes)...")
        entries = m3u_parser.parse_m3u(content)
        if entries:
            return entries
        # Manifest HLS puro (#EXT-X-*) sem EXTINF com título: tratar como stream.
        if "#EXT-X-" in content:
            log("  Manifest HLS detectado — tratando como vídeo único.")
            return [m3u_parser.entry_for_direct_url(routed.url)]
        if routed.kind is url_router.UrlKind.M3U_PLAYLIST:
            raise ExtractorError(
                "empty_playlist",
                "A playlist foi baixada, mas nenhum item válido foi encontrado.",
            )
        raise ExtractorError(
            "empty_playlist",
            "O arquivo não contém itens de playlist válidos (#EXTINF).",
        )

    # YOUTUBE e GENERIC: yt-dlp resolve.
    return extract_media_entries(routed.url, cfg, log=log, cancel=cancel)
