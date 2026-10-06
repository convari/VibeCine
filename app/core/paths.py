# -*- coding: utf-8 -*-
"""Resolução de diretórios por plataforma: Windows, Android e dev.

Regras de ouro:
- DADOS DO USUÁRIO (config.json, history.db, ferramentas)
  * Windows empacotado: %APPDATA%/VibeCine (gravável, preservado em updates)
  * Desenvolvimento: pasta do projeto (comportamento histórico)
  * Android: user_data_dir do app (área interna/privada)
- ARQUIVO DO PROGRAMA: diretório do exe (frozen) ou raiz do projeto (dev).
  No Android não há "instalação" de executáveis separada.
- Ferramentas externas: só existem em desktop; no Android o yt-dlp roda
  como biblioteca (sem .exe, sem console).
- NUNCA escrever dados do usuário dentro do _MEIPASS (PyInstaller).
"""

from __future__ import annotations

import os
import sys

from .branding import APP_NAME


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def is_android() -> bool:
    """True quando rodando dentro de python-for-android / ambiente Kivy mobile."""
    if sys.platform == "android":
        return True
    if os.environ.get("ANDROID_ARGUMENT") or os.environ.get("ANDROID_PRIVATE"):
        return True
    try:  # kivy presente mas sem app rodando (testes desktop)
        from kivy.utils import platform as kv_platform  # type: ignore
        return kv_platform == "android"
    except Exception:
        return False


def app_dir() -> str:
    """Diretório do aplicativo (onde está o exe / código)."""
    if is_frozen():
        return os.path.dirname(sys.executable)
    return os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))


def data_dir() -> str:
    """Diretório privado de dados do app (config, histórico, ferramentas)."""
    override = os.environ.get("VIBECINE_DATA_DIR")
    if override:
        os.makedirs(override, exist_ok=True)
        return override

    if is_android():
        path = None
        try:
            from kivy.app import App  # type: ignore
            app = App.get_running_app()
            if app is not None:
                path = app.user_data_dir
        except Exception:
            pass
        if not path:
            path = os.path.join(os.path.expanduser("~"), ".vibcine")
        os.makedirs(path, exist_ok=True)
        return path

    if is_frozen() and sys.platform == "win32":
        base = os.environ.get("APPDATA") or os.path.join(
            os.path.expanduser("~"), "AppData", "Roaming")
        path = os.path.join(base, APP_NAME)
    elif sys.platform == "win32":
        # desenvolvimento Windows: pasta do projeto (comportamento histórico)
        path = app_dir()
    else:
        path = os.path.join(os.path.expanduser("~"), ".local", "share", APP_NAME)
    os.makedirs(path, exist_ok=True)
    return path


def tools_dir() -> str:
    """Pasta das ferramentas externas (desktop; no Android não se aplica)."""
    path = os.path.join(data_dir(), "tools")
    os.makedirs(path, exist_ok=True)
    return path


def user_downloads_default() -> str:
    """Pasta padrão de downloads visível ao usuário.

    Android: Download/VibeCine pública via plyer quando possível;
    caso contrário, pasta interna do app. Desktop: ~/Videos/VibeCine.
    """
    override = os.environ.get("VIBECINE_DOWNLOAD_DIR")
    if override:
        os.makedirs(override, exist_ok=True)
        return override

    if is_android():
        try:
            from plyer import storagepath  # type: ignore
            base = storagepath.get_downloads_dir()
            path = os.path.join(base, APP_NAME)
            os.makedirs(path, exist_ok=True)
            return path
        except Exception:
            path = os.path.join(data_dir(), "downloads")
            os.makedirs(path, exist_ok=True)
            return path

    return os.path.join(os.path.expanduser("~"), "Videos", APP_NAME)
