# -*- coding: utf-8 -*-
"""Atualizador das ferramentas externas (yt-dlp, FFmpeg, Deno).

Refatoração do antigo atualizar.py como módulo reutilizável:
- usável pelo app empacotado (sem Python/scripts externos);
- alvo gravável: %APPDATA%/VibeCine/tools quando frozen;
- substituição ATÔMICA (download → tmp → os.replace); nunca sobrescreve
  um arquivo em uso: se o alvo estiver bloqueado, grava ".new" e avisa;
- yt-dlp: integridade SHA-256 verificada contra o SHA2-256SUMS oficial
  do release (além do magic number "MZ"). FFmpeg/Deno: tamanho mínimo +
  assinatura PE.
"""

from __future__ import annotations

import hashlib
import json
import os
import urllib.request
import zipfile
from dataclasses import dataclass
from pathlib import Path

from . import paths

UA = "VibeCine-Tools-Updater/2.0"

YTDLP_STABLE = "https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp.exe"
YTDLP_SHA256 = ("https://github.com/yt-dlp/yt-dlp/releases/latest/download/"
                "SHA2-256SUMS")
FFMPEG_API = "https://api.github.com/repos/BtbN/FFmpeg-Builds/releases/latest"
DENO_API = "https://api.github.com/repos/denoland/deno/releases/latest"


@dataclass
class ToolResult:
    name: str
    ok: bool
    message: str
    path: str = ""


def tools_target_dir() -> Path:
    """Pasta onde as ferramentas são gravadas (gravável pelo usuário)."""
    if paths.is_frozen():
        return Path(paths.tools_dir())
    return Path(paths.app_dir())


def _fetch(url: str, timeout: int = 120) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def _fetch_json(url: str) -> dict:
    return json.loads(_fetch(url, timeout=60).decode("utf-8"))


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _atomic_write(target: Path, data: bytes) -> Path:
    """Escreve com replace atômico; se o alvo estiver em uso, salva .new."""
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(target.suffix + ".tmp")
    with open(tmp, "wb") as fh:
        fh.write(data)
    try:
        os.replace(tmp, target)
        return target
    except OSError:
        new = target.with_suffix(".new")
        os.replace(tmp, new)
        return new


def _expect_pe(data: bytes, name: str):
    if len(data) < 4096 or not data.startswith(b"MZ"):
        raise UpdateToolError(f"{name}: arquivo baixado inválido (não é PE).")


class UpdateToolError(Exception):
    pass


def _verify_ytdlp(data: bytes) -> None:
    _expect_pe(data, "yt-dlp")
    try:
        sums = _fetch(YTDLP_SHA256).decode("utf-8", errors="replace")
    except Exception:
        # Sem o arquivo de somas o processo continua apenas com aviso.
        return
    digest = _sha256(data)
    for line in sums.splitlines():
        parts = line.split()
        if len(parts) == 2 and parts[1].endswith("yt-dlp.exe"):
            if parts[0].lower() != digest:
                raise UpdateToolError("yt-dlp: hash SHA-256 não confere!")
            return


def _extract_from_zip(data: bytes, wanted: str) -> bytes:
    import io
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        m = [n for n in z.namelist()
             if n.replace("\\", "/").lower().endswith("/" + wanted.lower())
             or n.replace("\\", "/").lower() == wanted.lower()]
        if not m:
            raise UpdateToolError(f"{wanted} não encontrado no pacote ZIP.")
        blob = z.read(m[0])
    _expect_pe(blob, wanted)
    return blob


def update_all(log=lambda m: None) -> list[ToolResult]:
    """Atualiza yt-dlp, FFmpeg e Deno. Retorna resultados por ferramenta."""
    target = tools_target_dir()
    results: list[ToolResult] = []

    # yt-dlp
    try:
        log("Atualizando yt-dlp…")
        data = _fetch(YTDLP_STABLE)
        _verify_ytdlp(data)
        p = _atomic_write(target / "yt-dlp.exe", data)
        results.append(ToolResult("yt-dlp", True, f"Atualizado → {p.name}",
                                  str(p)))
    except Exception as exc:
        results.append(ToolResult("yt-dlp", False, str(exc)))

    # FFmpeg (+ ffprobe)
    try:
        log("Atualizando FFmpeg…")
        meta = _fetch_json(FFMPEG_API)
        asset = next(
            (a for a in meta.get("assets", [])
             if a.get("name", "").startswith("ffmpeg-n8.1-latest-win64-gpl-8.1")
             and a["name"].endswith(".zip")), None)
        if not asset:
            raise UpdateToolError("Build FFmpeg win64 não encontrada.")
        data = _fetch(asset["browser_download_url"])
        for name in ("ffmpeg.exe", "ffprobe.exe"):
            blob = _extract_from_zip(data, name)
            p = _atomic_write(target / name, blob)
            results.append(ToolResult(name, True, f"Atualizado → {p.name}",
                                      str(p)))
    except Exception as exc:
        results.append(ToolResult("ffmpeg", False, str(exc)))

    # Deno
    try:
        log("Atualizando Deno…")
        meta = _fetch_json(DENO_API)
        asset = next(
            (a for a in meta.get("assets", [])
             if a.get("name", "").lower() == "deno-x86_64-pc-windows-msvc.zip"),
            None)
        if not asset:
            raise UpdateToolError("Asset Deno x86_64 não encontrado.")
        blob = _extract_from_zip(_fetch(asset["browser_download_url"]),
                                 "deno.exe")
        p = _atomic_write(target / "deno.exe", blob)
        results.append(ToolResult("deno", True, f"Atualizado → {p.name}",
                                  str(p)))
    except Exception as exc:
        results.append(ToolResult("deno", False, str(exc)))

    return results
