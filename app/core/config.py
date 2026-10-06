# -*- coding: utf-8 -*-
"""Configuração do aplicativo (config.json).

Mantém compatibilidade com o formato histórico (dict/JSON), mas agora com:
- esquema conhecido e validação;
- migração de valores antigos;
- formato de saída padrão corrigido para "original" (não assume MP3);
- sanitização de valores inválidos.
"""

from __future__ import annotations

import json
import os

from . import paths

# Em desenvolvimento, config.json fica na raiz do projeto (como sempre).
# No app empacotado (frozen), fica em %APPDATA%/VibeCine — sempre gravável
# e preservado entre atualizações.
CONFIG_FILE = (os.path.join(paths.data_dir(), "config.json") if paths.is_frozen()
               else os.path.join(paths.app_dir(), "config.json"))

#: Formatos de saída suportados pelo downloader.
VALID_FORMATS = ("original", "mp3", "mp4", "fullhd")

#: Limites de velocidade aceitos pela UI ("0" = sem limite).
VALID_SPEED_LIMITS = ("0", "1M", "5M", "10M", "20M", "50M")

DEFAULT_CONFIG = {
    "download_folder": "m3u_downloads",
    "ffmpeg_path": "ffmpeg.exe",
    "ytdlp_path": "yt-dlp.exe",
    "deno_path": "deno.exe",
    "organize_by_group": True,
    "speed_limit": "0",
    # Padrão seguro: preserva o conteúdo original.
    # "mp3" só deve ser escolhido explicitamente pelo usuário.
    "format": "original",
    # Fase 3: concorrência da fila de downloads e tema da interface.
    "max_concurrent_downloads": 2,
    "theme": "dark",
    # Fase 5: primeira execução / termos de uso.
    "onboarding_done": False,
    "terms_accepted": False,
}


def validate_config(cfg: dict) -> dict:
    """Corrige valores inválidos/inconsistentes in-place e retorna o dict.

    Nunca levanta exceção: configuração ruim não pode impedir o app de abrir.
    """
    defaults = DEFAULT_CONFIG
    for key, default in defaults.items():
        if key not in cfg or cfg[key] is None:
            cfg[key] = default

    # Migração de caminhos antigos ("ffmpeg" -> "ffmpeg.exe" etc.).
    for key in ("ffmpeg_path", "ytdlp_path", "deno_path"):
        val = str(cfg.get(key) or "").strip()
        if val and not val.lower().endswith(".exe") and os.sep not in val and "/" not in val:
            cfg[key] = val + ".exe"

    fmt = str(cfg.get("format") or "").strip().lower()
    if fmt not in VALID_FORMATS:
        cfg["format"] = DEFAULT_CONFIG["format"]

    speed = str(cfg.get("speed_limit") or "0").strip()
    if speed not in VALID_SPEED_LIMITS:
        # Aceita formatos numéricos com sufixo M/K fora da lista conhecida,
        # desde que o yt-dlp os entenda; caso contrário, sem limite.
        cfg["speed_limit"] = speed if speed[:-1].isdigit() and speed[-1:] in ("M", "K") else "0"

    cfg["organize_by_group"] = bool(cfg.get("organize_by_group"))

    try:
        cfg["max_concurrent_downloads"] = min(
            8, max(1, int(cfg.get("max_concurrent_downloads")
                          or DEFAULT_CONFIG["max_concurrent_downloads"])))
    except (TypeError, ValueError):
        cfg["max_concurrent_downloads"] = DEFAULT_CONFIG["max_concurrent_downloads"]

    theme = str(cfg.get("theme") or "").strip().lower()
    cfg["theme"] = theme if theme in ("dark", "light") else DEFAULT_CONFIG["theme"]

    cfg["onboarding_done"] = bool(cfg.get("onboarding_done"))
    cfg["terms_accepted"] = bool(cfg.get("terms_accepted"))

    folder = str(cfg.get("download_folder") or "").strip()
    cfg["download_folder"] = folder or DEFAULT_CONFIG["download_folder"]

    return cfg


def load_config(path: str = CONFIG_FILE) -> dict:
    """Carrega config.json aplicando defaults, migração e validação."""
    cfg = DEFAULT_CONFIG.copy()
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as fh:
                loaded = json.load(fh)
            if isinstance(loaded, dict):
                cfg.update(loaded)
        except (OSError, json.JSONDecodeError, UnicodeDecodeError):
            pass
    return validate_config(cfg)


def save_config(cfg: dict, path: str = CONFIG_FILE) -> None:
    validate_config(cfg)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(cfg, fh, indent=2, ensure_ascii=False)
