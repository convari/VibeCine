# -*- coding: utf-8 -*-
"""Classificação de exceções em mensagens amigáveis ao usuário.

Converte erros técnicos (URLError, HTTPError, timeout, etc.) em um código
estável + mensagem em português, pensada para o usuário final. A mensagem
técnica original fica disponível para o log/detalhes.
"""

from __future__ import annotations

import socket
import urllib.error
import urllib.parse


def classify_exception(exc: BaseException, url: str = "") -> tuple[str, str]:
    """Retorna (codigo_estavel, mensagem_amigavel)."""
    cause = exc
    # Desembrulha URLError -> razão interna (SSL, DNS, refused...).
    inner = getattr(cause, "reason", None)

    if isinstance(cause, urllib.error.HTTPError):
        code = cause.code
        if code in (401, 403):
            return "forbidden", (
                f"Acesso negado (HTTP {code}). Este link pode ter expirado ou exigir "
                "login — listas de IPTV costumam renovar os links; peça um novo ao provedor."
            )
        if code == 404:
            return "not_found", "Conteúdo não encontrado (HTTP 404). O link pode ter sido removido ou estar errado."
        if 500 <= code < 600:
            return "server_error", f"O servidor do conteúdo falhou (HTTP {code}). Tente novamente em alguns minutos."
        return "http_error", f"Falha HTTP {code} ao acessar o endereço."

    if isinstance(cause, urllib.error.URLError):
        if isinstance(inner, socket.gaierror):
            return "dns_error", "Endereço não encontrado (falha de DNS). Confira a URL digitada."
        if isinstance(inner, (ConnectionRefusedError,)) or "refused" in str(inner).lower():
            return "refused", "Conexão recusada pelo servidor. Ele pode estar fora do ar ou bloqueado."
        if isinstance(inner, TimeoutError) or "timed out" in str(inner).lower():
            return "timeout", "O servidor demorou demais para responder. Verifique sua internet ou tente depois."
        return "network_error", "Falha de rede ao acessar o endereço. Verifique sua conexão."

    if isinstance(cause, (TimeoutError, socket.timeout)):
        return "timeout", "Tempo esgotado ao aguardar resposta. Tente novamente."

    if isinstance(cause, FileNotFoundError):
        return "file_not_found", f"Arquivo ou ferramenta não encontrado: {getattr(cause, 'filename', '') or str(cause)}"

    if isinstance(cause, PermissionError):
        return "permission", "Sem permissão para acessar o arquivo/pasta. Verifique as permissões ou escolha outra pasta."

    if isinstance(cause, UnicodeDecodeError):
        return "encoding_error", "A lista não está em uma codificação de texto reconhecida."

    if isinstance(cause, ValueError) and "url" in str(cause).lower():
        return "invalid_url", "URL inválida. Verifique o endereço digitado."

    return "unknown", f"Erro inesperado ao acessar {url or 'o recurso'}: {exc}"


def user_message(exc: BaseException, url: str = "") -> str:
    """Atalho para obter apenas a mensagem amigável."""
    return classify_exception(exc, url)[1]
