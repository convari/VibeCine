# -*- coding: utf-8 -*-
"""Localização das ferramentas externas (yt-dlp, FFmpeg, Deno).

Ordem de busca (a primeira que existir vence):
1. caminho absoluto configurado pelo usuário;
2. relativo à pasta do programa / pasta do exe (modo portátil);
3. binário local na pasta do programa ou em %APPDATA%/VibeCine/tools;
4. PATH do sistema.

Em modo empacotado (PyInstaller), a pasta de ferramentas gravável é
paths.tools_dir() — as atualizações nunca escrevem em Program Files.
"""

from __future__ import annotations

import os
import shutil

from . import paths

APP_DIR = paths.app_dir()


def resolve_tool_path(value: str | None, local_name: str, allow_missing: bool = False) -> str:
    """Resolve o caminho de uma ferramenta (ver docstring do módulo)."""
    raw = str(value or "").strip()

    candidates: list[str] = []
    if raw:
        if os.path.isabs(raw):
            candidates.append(raw)
        else:
            candidates.append(os.path.join(APP_DIR, raw))
            if not raw.lower().endswith(".exe"):
                candidates.append(os.path.join(APP_DIR, raw + ".exe"))

    if paths.is_frozen():
        candidates.insert(0, os.path.join(paths.tools_dir(), local_name))

    local = os.path.join(APP_DIR, local_name)
    candidates.append(local)

    for candidate in candidates:
        if os.path.isfile(candidate):
            return os.path.abspath(candidate)

    found = shutil.which(raw) if raw else None
    if found:
        return found

    # Destino preferido quando ausente: pasta de tools gravável (frozen)
    # ou pasta do programa (desenvolvimento).
    if allow_missing:
        return os.path.join(paths.tools_dir(), local_name) if paths.is_frozen() else local

    return raw or local


def check_tools(cfg: dict) -> dict:
    """Pré-flight: verifica presença das ferramentas.

    Retorna dict {nome: {"path": str, "ok": bool}} para a UI exibir
    orientação ao usuário antes de iniciar downloads.
    """
    result = {}
    for key, local_name in (
        ("ytdlp_path", "yt-dlp.exe"),
        ("ffmpeg_path", "ffmpeg.exe"),
        ("deno_path", "deno.exe"),
    ):
        path = resolve_tool_path(cfg.get(key), local_name, allow_missing=True)
        result[key] = {"path": path, "ok": os.path.isfile(path)}
    return result
