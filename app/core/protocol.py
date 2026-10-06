# -*- coding: utf-8 -*-
"""Protocolo vibcine:// (Fase 6).

- parse_vibcine_uri(): valida e extrai a URL decodificada de um link
  vibcine://load?url=<urlenc>. Rejeita esquemas != http(s) e URLs
  inválidas (reuso de url_router.validate_url).
- register_protocol()/unregister_protocol(): registro por usuário em
  HKCU\\Software\\Classes\\vibcine — SEM privilégio de administrador.
- Credenciais embutidas NUNCA são logadas: apenas a forma mascarada.
"""

from __future__ import annotations

import sys
import urllib.parse
import winreg

from .branding import APP_NAME, APP_PRODUCT
from .downloader import redact_url
from .url_router import validate_url

PROTOCOL = "vibcine"


def parse_vibcine_uri(arg: str) -> tuple[str | None, str]:
    """Interpreta um argumento vibcine://... → (url_decodificada, erro).

    Retorna (url, "") em sucesso; (None, motivo) quando inválido.
    Aceita somente ação "load" e URLs http/https válidas e limpas.
    """
    arg = (arg or "").strip()
    if not arg.lower().startswith(f"{PROTOCOL}://"):
        return None, "Não é um link VibeCine."

    rest = arg[len(f"{PROTOCOL}://"):]
    action, _, query = rest.partition("?")
    if action.strip("/").lower() != "load":
        return None, "Ação não suportada."

    params = urllib.parse.parse_qs(query, keep_blank_values=False)
    url = params.get("url", [""])[0]
    if not url:
        return None, "Link sem URL."

    ok, message = validate_url(url)
    if not ok:
        return None, message
    parts = urllib.parse.urlsplit(url)
    if parts.scheme not in ("http", "https"):
        return None, "Apenas URLs http(s) são aceitas por link externo."

    if "@" in parts.netloc:
        # Nunca repassar credenciais embutidas vindas de link externo.
        return None, "A URL contém credenciais e não será carregada por link externo."
    return url, ""


def _exe_command(executable: str | None = None) -> str:
    exe = executable or sys.executable
    if getattr(sys, "frozen", False):
        return f'"{exe}" "%1"'
    return f'"{exe}" "{_entry_script()}" "%1"'


def _entry_script() -> str:
    import os
    return os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..",
                                        "vibcine.py"))


def register_protocol(executable: str | None = None) -> None:
    """Registra vibcine:// no HKCU (apenas usuário atual, sem admin)."""
    base = rf"Software\Classes\{PROTOCOL}"
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, base) as key:
        winreg.SetValueEx(key, None, 0, winreg.REG_SZ,
                          f"URL:{APP_NAME} Protocol")
        winreg.SetValueEx(key, "URL Protocol", 0, winreg.REG_SZ, "")
        with winreg.CreateKey(key, "DefaultIcon") as icon_key:
            exe = executable or sys.executable
            winreg.SetValueEx(icon_key, None, 0, winreg.REG_SZ,
                              f'"{exe}",0' if getattr(sys, "frozen", False)
                              else f'"{exe}"')
        with winreg.CreateKey(key, r"shell\open\command") as cmd_key:
            winreg.SetValueEx(cmd_key, None, 0, winreg.REG_SZ,
                              _exe_command(executable))


def unregister_protocol() -> None:
    """Remove o registro do protocolo (usado pelo desinstalador)."""
    for sub in (r"shell\open\command", r"shell\open", "shell", "DefaultIcon", ""):
        try:
            winreg.DeleteKey(winreg.HKEY_CURRENT_USER,
                             rf"Software\Classes\{PROTOCOL}\{sub}" if sub
                             else rf"Software\Classes\{PROTOCOL}")
        except OSError:
            pass


def log_safe_uri(arg: str) -> str:
    """Forma mascarada do link para logs (nunca vaza credenciais)."""
    url, _ = parse_vibcine_uri(arg)
    if url:
        return f"{PROTOCOL}://load?url={redact_url(url)}"
    return f"{PROTOCOL}://<inválido>"
