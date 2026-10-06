# -*- coding: utf-8 -*-
"""Compartilhamento de conteúdo (Fase 4).

Regras de segurança:
- NUNCA compartilha URLs que contenham credenciais (user:pass@host) ou
  parâmetros sensíveis (token, password, key, ...), típicas de IPTV.
- Para YouTube, prioriza a URL canônica da página (watch?v=...).
- Quando a URL não é compartilhável, oferece apenas uma versão mascarada
  para referência — jamais utilizável para download por terceiros.

Sem backend: tudo é montado localmente; a abertura usa webbrowser.open().
O QR Code é gerado 100% offline com a biblioteca qrcode.
"""

from __future__ import annotations

import urllib.parse
from dataclasses import dataclass

from .downloader import _SENSITIVE_PARAMS, redact_url
from .url_router import is_youtube_url

APP_NAME = "VibeCine"

_TYPE_PT = {
    "filme": "Filme", "serie": "Série", "radio": "Rádio",
    "esporte": "Esporte", "youtube": "YouTube", "canal": "Canal",
}


# ── Análise de segurança da URL ──────────────────────────────────────────────

def url_has_credentials(url: str) -> bool:
    """True se a URL contém userinfo (usuário:senha@host)."""
    try:
        parts = urllib.parse.urlsplit(url)
    except ValueError:
        return False
    return bool(parts.password) or ("@" in parts.netloc and bool(parts.username))


def url_has_sensitive_params(url: str) -> bool:
    """True se a query string contém parâmetros sensíveis (token, senha...)."""
    try:
        parts = urllib.parse.urlsplit(url)
        pairs = urllib.parse.parse_qsl(parts.query, keep_blank_values=True)
    except ValueError:
        return False
    return any(k.lower() in _SENSITIVE_PARAMS for k, _ in pairs)


def is_sensitive_url(url: str) -> bool:
    """URL que não deve ser compartilhada nem exibida por completo."""
    return url_has_credentials(url) or url_has_sensitive_params(url)


# ── Escolha da URL compartilhável ────────────────────────────────────────────

def canonical_youtube_url(entry: dict) -> str:
    """URL da página do conteúdo (watch?v=ID), mesmo se a entrada veio
    de um link encurtado ou de playlist."""
    url = entry.get("url", "")
    vid = entry.get("tvg_id", "")
    if vid and is_youtube_url(url) or (vid and not url.startswith("http")):
        return f"https://www.youtube.com/watch?v={vid}"
    if is_youtube_url(url):
        return url
    if vid:
        return f"https://www.youtube.com/watch?v={vid}"
    return url


@dataclass
class SharePlan:
    """Resultado da decisão de compartilhamento."""
    shareable: bool
    url: str = ""                # URL segura e utilizável (vazia se não houver)
    reason: str = ""             # explicação quando não compartilhável
    safe_reference: str = ""     # versão mascarada para referência/cópia


def plan_share(entry: dict) -> SharePlan:
    """Decide o que pode ser compartilhado para uma entrada."""
    url = str(entry.get("url", "") or "").strip()
    if not url:
        return SharePlan(False, reason="Este item não possui URL.")

    if is_youtube_url(url) or entry.get("type") == "youtube":
        canon = canonical_youtube_url(entry)
        if is_sensitive_url(canon):
            return SharePlan(
                False,
                reason="A URL deste conteúdo contém credenciais e não pode "
                       "ser compartilhada diretamente.",
                safe_reference=redact_url(canon))
        return SharePlan(True, url=canon)

    # M3U/IPTV ou outro: nunca expor segredos.
    if is_sensitive_url(url):
        return SharePlan(
            False,
            reason="Este link contém credenciais ou tokens de acesso (IPTV) "
                   "e não pode ser compartilhado diretamente, para proteger "
                   "sua conta.",
            safe_reference=redact_url(url))

    return SharePlan(True, url=url)


# ── Texto e links de compartilhamento ────────────────────────────────────────

def build_share_message(entry: dict, url: str) -> str:
    """Mensagem padrão: título, tipo, URL e assinatura do app."""
    title = entry.get("title", "Conteúdo")
    kind = _TYPE_PT.get(entry.get("type", ""), "Conteúdo")
    return (
        f"🎬 {title}\n"
        f"Tipo: {kind}\n"
        f"▶ {url}\n"
        f"— Compartilhado com {APP_NAME}"
    )


def build_share_links(message: str, url: str) -> dict[str, str]:
    """URLs de intent das redes, com encoding correto (quote_via=quote)."""
    text_enc = urllib.parse.quote(message, safe="")
    url_enc = urllib.parse.quote(url, safe="")
    title = message.splitlines()[0] if message else ""
    return {
        "whatsapp": f"https://wa.me/?text={text_enc}",
        "telegram": f"https://t.me/share/url?url={url_enc}&text={text_enc}",
        "facebook": f"https://www.facebook.com/sharer/sharer.php?u={url_enc}",
        "x": f"https://twitter.com/intent/tweet?text={text_enc}&url={url_enc}",
        "email": (f"mailto:?subject={urllib.parse.quote(title, safe='')}"
                  f"&body={text_enc}"),
    }


# ── QR Code offline ──────────────────────────────────────────────────────────

def make_qr_png_bytes(data: str, box_size: int = 8, border: int = 2) -> bytes:
    """Gera o QR Code localmente e retorna os bytes PNG."""
    import io

    import qrcode

    qr = qrcode.QRCode(box_size=box_size, border=border,
                       error_correction=qrcode.constants.ERROR_CORRECT_M)
    qr.add_data(data)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()
