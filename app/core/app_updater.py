# -*- coding: utf-8 -*-
"""Atualizador do próprio aplicativo (Fase 6).

Fluxo seguro:
1. consulta um manifesto JSON (APP_UPDATE_URL) com {version, url, sha256};
2. baixa o pacote para um diretório TEMPORÁRIO;
3. valida a integridade via SHA-256 (não basta "começa com MZ");
4. extrai protegendo contra path traversal (Zip Slip);
5. só então dispara o helper de troca, que fecha o app, substitui os
   arquivos e reabre — preservando config.json/history.db (ficam em
   %APPDATA%/VibeCine, fora da pasta do programa).

Nada aqui executa código baixado.
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
import urllib.request
import zipfile

from . import paths
from .branding import APP_VERSION

#: Manifesto de versão (JSON). Configure para o seu canal de release.
APP_UPDATE_URL = os.environ.get(
    "VIBECINE_UPDATE_URL",
    "https://updates.vibcine.app/latest.json",  # placeholder — ajustar no release
)

UA = "VibeCine-Updater/2.0"


class UpdateError(Exception):
    pass


def _fetch(url: str, timeout: int = 60) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def check_for_update(manifest_url: str = APP_UPDATE_URL) -> dict | None:
    """Consulta o manifesto. Retorna dict {version,url,sha256} ou None."""
    data = json.loads(_fetch(manifest_url).decode("utf-8"))
    if not isinstance(data, dict) or not data.get("version"):
        raise UpdateError("Manifesto de atualização inválido.")
    return data


def is_newer(remote: str, current: str = APP_VERSION) -> bool:
    def key(v):
        return tuple(int(p) for p in str(v).split(".") if p.isdigit())
    return key(remote) > key(current)


def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def download_update(manifest: dict, dest_dir: str | None = None,
                    log=lambda m: None) -> str:
    """Baixa o pacote e VALIDA o SHA-256. Retorna o caminho do arquivo."""
    if not manifest.get("url"):
        raise UpdateError("Manifesto sem URL de pacote.")
    dest_dir = dest_dir or tempfile.mkdtemp(prefix="vibcine-update-")
    os.makedirs(dest_dir, exist_ok=True)
    path = os.path.join(dest_dir, "update.zip")
    log("Baixando atualização…")
    blob = _fetch(manifest["url"], timeout=300)
    with open(path, "wb") as fh:
        fh.write(blob)

    expected = str(manifest.get("sha256", "")).lower()
    if expected:
        actual = sha256_file(path)
        if actual != expected:
            os.unlink(path)
            raise UpdateError(
                "Falha de integridade: o hash do pacote não confere. "
                "Atualização abortada por segurança.")
        log("Hash SHA-256 verificado ✔")
    else:
        raise UpdateError("Manifesto sem hash SHA-256 — recusado por segurança.")
    return path


def safe_extract(zip_path: str, dest_dir: str, log=lambda m: None) -> str:
    """Extrai o pacote com proteção contra path traversal (Zip Slip)."""
    out = os.path.join(dest_dir, "payload")
    os.makedirs(out, exist_ok=True)
    with zipfile.ZipFile(zip_path) as z:
        for member in z.namelist():
            target = os.path.abspath(os.path.join(out, member))
            if not target.startswith(os.path.abspath(out) + os.sep):
                raise UpdateError(f"Entrada maliciosa no pacote: {member}")
            z.extract(member, out)
    log("Pacote extraído com segurança ✔")
    return out


def make_swap_script(payload_dir: str, app_dir: str, exe_name: str,
                     work_dir: str | None = None) -> str:
    """Gera um .bat de troca: aguarda o app fechar, substitui e reabre.

    Arquivos de dados do usuário NÃO ficam em app_dir (estão em
    %APPDATA%), portanto a troca do programa não os afeta.
    """
    work_dir = work_dir or tempfile.mkdtemp(prefix="vibcine-swap-")
    bat = os.path.join(work_dir, "apply_update.bat")
    with open(bat, "w", encoding="latin-1") as fh:
        fh.write(
            "@echo off\r\n"
            "setlocal\r\n"
            f'set "SRC={payload_dir}"\r\n'
            f'set "DST={app_dir}"\r\n'
            f'set "EXE={exe_name}"\r\n'
            ":wait\r\n"
            'tasklist /FI "IMAGENAME eq %EXE%" | find /I "%EXE%" >nul\r\n'
            "if not errorlevel 1 (timeout /t 1 /nobreak >nul & goto wait)\r\n"
            'robocopy "%SRC%" "%DST%" /E /IS /IT >nul\r\n'
            f'start "" "%DST%\\%EXE%"\r\n'
            "endlocal\r\n")
    return bat
