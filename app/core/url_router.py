# -*- coding: utf-8 -*-
"""Validação e roteamento de URLs de entrada.

Decide COMO cada entrada deve ser processada:
- LOCAL_FILE     -> arquivo .m3u/.m3u8/.txt no disco (ou file://)
- YOUTUBE        -> youtube.com / youtu.be (vídeo, playlist, canal)
- DIRECT_STREAM  -> URL http(s) apontando para stream/mídia (.m3u8, .ts, .mp4...)
- M3U_PLAYLIST   -> URL http(s) remota de playlist
- GENERIC        -> outra URL http(s) — tentar yt-dlp, com fallback a playlist
- INVALID        -> entrada rejeitada com mensagem de validação
"""

from __future__ import annotations

import os
import urllib.parse
from dataclasses import dataclass
from enum import Enum


class UrlKind(str, Enum):
    LOCAL_FILE = "local_file"
    YOUTUBE = "youtube"
    DIRECT_STREAM = "direct_stream"
    M3U_PLAYLIST = "m3u_playlist"
    GENERIC = "generic"
    INVALID = "invalid"


@dataclass
class RoutedUrl:
    kind: UrlKind
    url: str           # URL normalizada
    message: str = ""  # explicação quando INVALID (ou observações)
    local_path: str = ""  # preenchido para LOCAL_FILE


_YOUTUBE_HOSTS = ("youtube.com", "youtu.be", "www.youtube.com", "m.youtube.com", "music.youtube.com")

_PLAYLIST_EXT = (".m3u", ".m3u8")
_DIRECT_MEDIA_EXT = (
    ".ts", ".mp4", ".mkv", ".avi", ".mov", ".webm", ".mp3", ".aac",
    ".ogg", ".flac", ".wav", ".m4a",
)
_PLAYLIST_CONTENT_HINTS = ("mpegurl", "x-mpegurl", "application/vnd.apple.mpegurl")


def is_youtube_url(url: str) -> bool:
    host = urllib.parse.urlsplit(url).netloc.lower() if "://" in url else ""
    if not host:
        # URLs sem esquema: checagem textual (compat. com o código original).
        return "youtube.com" in url or "youtu.be" in url
    return any(host == h or host.endswith("." + h) for h in _YOUTUBE_HOSTS)


def _split(url: str) -> urllib.parse.SplitResult | None:
    try:
        parts = urllib.parse.urlsplit(url)
    except ValueError:
        return None
    return parts


def validate_url(raw: str) -> tuple[bool, str]:
    """Validação rápida para feedback imediato na UI (antes de carregar)."""
    url = (raw or "").strip()
    if not url:
        return False, "Digite uma URL ou caminho de arquivo."
    if url.startswith("file://") or os.path.exists(url):
        if os.path.exists(url.replace("file://", "")):
            return True, ""
        return False, "Arquivo não encontrado no disco."
    parts = _split(url)
    if parts is None or parts.scheme not in ("http", "https") or not parts.netloc:
        return False, "URL inválida. Use http(s):// ou um caminho de arquivo local."
    if "." not in parts.netloc:
        return False, "Domínio inválido na URL."
    return True, ""


def classify_url(raw: str) -> RoutedUrl:
    """Classifica a entrada e retorna a rota de processamento."""
    url = (raw or "").strip()
    ok, message = validate_url(url)
    if not url:
        return RoutedUrl(UrlKind.INVALID, url, message or "URL vazia.")

    if url.startswith("file://") or os.path.exists(url):
        path = url.replace("file://", "")
        if os.path.isfile(path):
            return RoutedUrl(UrlKind.LOCAL_FILE, url, local_path=path)
        return RoutedUrl(UrlKind.INVALID, url, message or "Arquivo não encontrado.")

    parts = _split(url)
    if not ok or parts is None:
        return RoutedUrl(UrlKind.INVALID, url, message)

    if is_youtube_url(url):
        return RoutedUrl(UrlKind.YOUTUBE, url)

    path = parts.path.lower()
    ext = os.path.splitext(path)[1]

    # .m3u/.m3u8 são playlists; se o conteúdo for um manifest HLS puro
    # (#EXT-X-*), o extractor o reclassifica como stream direto.
    if ext in _PLAYLIST_EXT:
        return RoutedUrl(UrlKind.M3U_PLAYLIST, url)
    if ext in _DIRECT_MEDIA_EXT:
        return RoutedUrl(UrlKind.DIRECT_STREAM, url)

    # Sem extensão clara: a decisão final pode usar o Content-Type
    # (ver extractor). Por padrão, assumimos playlist.
    return RoutedUrl(UrlKind.GENERIC, url)


def looks_like_playlist_content_type(content_type: str) -> bool:
    ct = (content_type or "").lower()
    return any(h in ct for h in _PLAYLIST_CONTENT_HINTS) or "text/plain" in ct
