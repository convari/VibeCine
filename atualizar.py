# -*- coding: utf-8 -*-
"""
Atualizador local do M3U Downloader Pro.

Uso:
    python atualizar.py

Opcional:
    python atualizar.py --nightly

Tudo é salvo dentro da própria pasta do programa:
    yt-dlp.exe
    ffmpeg.exe
    ffprobe.exe
    deno.exe

Nenhum desses componentes é instalado no PATH do Windows.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import stat
import sys
import tempfile
import urllib.request
import zipfile
from datetime import datetime
from pathlib import Path


APP_DIR = Path(__file__).resolve().parent
BACKUP_DIR = APP_DIR / "_backup_atualizacao"
USER_AGENT = "M3U-Downloader-Pro-Updater/1.0"

YTDLP_STABLE_URL = (
    "https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp.exe"
)
YTDLP_NIGHTLY_API = (
    "https://api.github.com/repos/yt-dlp/yt-dlp-nightly-builds/releases/latest"
)
FFMPEG_API = "https://api.github.com/repos/BtbN/FFmpeg-Builds/releases/latest"
DENO_API = "https://api.github.com/repos/denoland/deno/releases/latest"


def log(msg: str) -> None:
    print(msg, flush=True)


def fetch_bytes(url: str, timeout: int = 120) -> bytes:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "*/*",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def fetch_json(url: str):
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "application/vnd.github+json",
        },
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read().decode("utf-8"))


def atomic_replace_bytes(target: Path, data: bytes) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    temp = target.with_suffix(target.suffix + ".tmp")
    with open(temp, "wb") as fh:
        fh.write(data)
    os.replace(temp, target)


def backup_file(path: Path) -> None:
    if not path.exists():
        return
    BACKUP_DIR.mkdir(exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    dst = BACKUP_DIR / f"{path.name}.{stamp}.bak"
    shutil.copy2(path, dst)
    log(f"  Backup: {dst.name}")


def extract_executable_from_zip(data: bytes, wanted_name: str) -> bytes:
    with tempfile.TemporaryDirectory() as td:
        zpath = Path(td) / "download.zip"
        zpath.write_bytes(data)
        with zipfile.ZipFile(zpath) as z:
            matches = [
                n for n in z.namelist()
                if n.replace("\\", "/").lower().endswith("/" + wanted_name.lower())
                or n.replace("\\", "/").lower() == wanted_name.lower()
            ]
            if not matches:
                raise RuntimeError(f"{wanted_name} não encontrado no ZIP.")
            return z.read(matches[0])


def update_ytdlp(nightly: bool) -> None:
    target = APP_DIR / "yt-dlp.exe"
    log("\n[1/3] Atualizando yt-dlp...")

    if nightly:
        meta = fetch_json(YTDLP_NIGHTLY_API)
        assets = meta.get("assets", [])
        asset = next(
            (a for a in assets if a.get("name", "").lower() == "yt-dlp.exe"),
            None,
        )
        if not asset:
            raise RuntimeError("Asset yt-dlp.exe não encontrado no nightly.")
        url = asset["browser_download_url"]
        version = meta.get("tag_name", "nightly")
    else:
        url = YTDLP_STABLE_URL
        version = "stable/latest"

    data = fetch_bytes(url)
    if not data.startswith(b"MZ"):
        raise RuntimeError("O arquivo baixado do yt-dlp não parece ser um executável Windows.")

    backup_file(target)
    atomic_replace_bytes(target, data)
    log(f"  OK: yt-dlp -> {version} ({len(data):,} bytes)")


def choose_asset(assets, predicate):
    for asset in assets:
        name = asset.get("name", "")
        if predicate(name):
            return asset
    return None


def update_ffmpeg() -> None:
    log("\n[2/3] Atualizando FFmpeg...")
    meta = fetch_json(FFMPEG_API)
    assets = meta.get("assets", [])

    asset = choose_asset(
        assets,
        lambda n: (
            n.startswith("ffmpeg-n8.1-latest-win64-gpl-8.1.zip")
            and n.lower().endswith(".zip")
        ),
    )
    if not asset:
        raise RuntimeError(
            "Build FFmpeg 8.1 para Windows x64 não encontrada no release atual."
        )

    data = fetch_bytes(asset["browser_download_url"])
    ffmpeg_exe = extract_executable_from_zip(data, "ffmpeg.exe")
    ffprobe_exe = extract_executable_from_zip(data, "ffprobe.exe")

    for name, blob in (("ffmpeg.exe", ffmpeg_exe), ("ffprobe.exe", ffprobe_exe)):
        target = APP_DIR / name
        backup_file(target)
        atomic_replace_bytes(target, blob)

    log(
        f"  OK: FFmpeg/ffprobe -> release {meta.get('tag_name', 'latest')} "
        f"({len(data):,} bytes baixados)"
    )


def update_deno() -> None:
    log("\n[3/3] Atualizando Deno (runtime JavaScript do YouTube)...")
    meta = fetch_json(DENO_API)
    assets = meta.get("assets", [])
    asset = choose_asset(
        assets,
        lambda n: n.lower() == "deno-x86_64-pc-windows-msvc.zip",
    )
    if not asset:
        raise RuntimeError("Asset Deno x86_64 Windows não encontrado.")

    data = fetch_bytes(asset["browser_download_url"])
    deno_exe = extract_executable_from_zip(data, "deno.exe")
    target = APP_DIR / "deno.exe"

    backup_file(target)
    atomic_replace_bytes(target, deno_exe)

    log(f"  OK: Deno -> {meta.get('tag_name', 'latest')}")


def show_versions() -> None:
    log("\nArquivos locais:")
    for name in ("yt-dlp.exe", "ffmpeg.exe", "ffprobe.exe", "deno.exe"):
        p = APP_DIR / name
        if p.exists():
            log(f"  ✓ {name}: {p.stat().st_size:,} bytes")
        else:
            log(f"  ✗ {name}: AUSENTE")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--nightly",
        action="store_true",
        help="Usa o último yt-dlp nightly em vez do stable.",
    )
    args = parser.parse_args()

    if os.name != "nt":
        log("Este atualizador foi feito para Windows.")
        return 1

    log("============================================")
    log(" M3U Downloader Pro - Atualizador")
    log("============================================")
    log(f"Pasta: {APP_DIR}")
    log("Este processo só substitui arquivos dentro da pasta do programa.")

    try:
        update_ytdlp(args.nightly)
        update_ffmpeg()
        update_deno()
    except Exception as exc:
        log(f"\n[ERRO] {exc}")
        log("Nada fora da pasta do programa foi alterado.")
        show_versions()
        return 1

    show_versions()
    log("\n============================================")
    log(" Atualização concluída.")
    log("============================================")
    log("Agora execute iniciar.bat.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
