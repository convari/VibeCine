# -*- coding: utf-8 -*-
"""Motor de download Android/in-process (Fase Android).

Reutiliza do core: estados/métricas (DownloadJob, JobStatus), nomes seguros
(sanitize_filename/unique_path/output_dir_for), classificação de erros
(classify_download_error), mascaramento de URLs (redact_url), detecção de
formato. NÃO herda o subprocess/CLI do Windows.

Estratégia técnica (Android):
- yt-dlp como BIBLIOTECA Python (sem executáveis);
- FFmpeg: ausente no MVP → formatos single-file, sem merge/conversão
  (MP3 indisponível; áudio baixa como m4a/webm "original");
- Deno: não existe build Android → YouTube com assinatura protegida pode
  falhar; a falha vira erro amigável (limitação documentada);
- pausa = cancela mantendo o .part; retomada = nova tentativa com
  continudl=True (yt-dlp retoma automaticamente);
- cancelamento via exceção no progress_hook; 1 download por vez por padrão
  (workers configuráveis);
- notificações do sistema via plyer (quando disponível).
"""

from __future__ import annotations

import os
import threading
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor

from app.core import paths
from app.core.downloader import (DownloadJob, JobStatus, MAX_NAME_LEN,
                                 classify_download_error,
                                 output_dir_for, redact_url,
                                 sanitize_filename, unique_path)

try:
    import yt_dlp  # type: ignore
    YTDLP_AVAILABLE = True
except ImportError:
    yt_dlp = None
    YTDLP_AVAILABLE = False


class _Cancelled(Exception):
    pass


# Sem ffmpeg no Android: apenas formatos de arquivo único (sem merge).
FORMAT_MAP = {
    "original": "b[ext=mp4]/b",
    "mp4": "b[ext=mp4]/b",
    "fullhd": "b[height<=1080][ext=mp4]/b[height<=1080]/b",
    "mp3": "ba/b",  # sem conversão: sai m4a/webm — MP3 exige FFmpeg (limitação)
}


def http_download(url: str, dest: str, cancel: threading.Event,
                  on_progress, log, timeout: int = 30) -> bool:
    """Fallback puro-Python para downloads diretos de arquivo (sem yt-dlp)."""
    req = urllib.request.Request(url, headers={"User-Agent": "VibeCine/2.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        total = int(resp.headers.get("Content-Length") or 0)
        got = 0
        part = dest + ".part"
        if os.path.exists(part):  # retomada simples quando o servidor aceita Range
            got = os.path.getsize(part)
            mode = "ab"
        else:
            mode = "wb"
        with open(part, mode) as fh:
            while True:
                if cancel.is_set():
                    return False
                chunk = resp.read(64 * 1024)
                if not chunk:
                    break
                fh.write(chunk)
                got += len(chunk)
                pct = (got / total * 100.0) if total else 0.0
                on_progress(pct, got, total)
        os.replace(part, dest)
        return True


class DownloadEngine:
    """Fila de downloads em-processo (Apto para Android e testes desktop).

    Callbacks: on_job_update(job), on_progress(0..100), on_log(msg),
    on_queue_finished(). Mesma semântica de estados do DownloadManager.
    """

    def __init__(self, cfg: dict, max_workers: int = 1,
                 on_job_update=lambda j: None, on_progress=lambda p: None,
                 on_log=lambda m: None, on_queue_finished=lambda: None,
                 ydl_module=None, sleeper=time.sleep, max_retries: int = 2):
        self.cfg = cfg
        self.max_workers = max(1, int(max_workers))
        self.on_job_update = on_job_update
        self.on_progress = on_progress
        self.on_log = on_log
        self.on_queue_finished = on_queue_finished
        self.max_retries = max_retries
        self._sleep = sleeper
        self._ydl_mod = ydl_module if ydl_module is not None else yt_dlp
        self.jobs: list[DownloadJob] = []
        self._executor: ThreadPoolExecutor | None = None
        self._lock = threading.Lock()
        self._shutdown = False
        self._finished_fired = False

    # ── API ──────────────────────────────────────────────────────────────

    def add(self, entries: list[dict]) -> list[DownloadJob]:
        entries = list(entries)
        if not entries:
            return []
        with self._lock:
            self._finished_fired = False
            if self._executor is None:
                self._executor = ThreadPoolExecutor(
                    max_workers=self.max_workers,
                    thread_name_prefix="vibcine-android")
            start_id = len(self.jobs)
            new_jobs = [DownloadJob(id=start_id + i, entry=e)
                        for i, e in enumerate(entries)]
            self.jobs.extend(new_jobs)
            for job in new_jobs:
                self.on_job_update(job)
                self._executor.submit(self._run_job, job)
        return new_jobs

    def cancel_job(self, job_id: int) -> None:
        for j in self.jobs:
            if j.id == job_id:
                j.cancel_event.set()

    def cancel_all(self) -> None:
        for j in self.jobs:
            if j.status not in (JobStatus.DONE, JobStatus.FAILED,
                                JobStatus.CANCELLED):
                j.cancel_event.set()

    def pause_job(self, job_id: int) -> None:
        for j in self.jobs:
            if j.id == job_id and j.status is JobStatus.RUNNING:
                j.pause_event.set()

    def resume_job(self, job_id: int) -> bool:
        job = next((j for j in self.jobs if j.id == job_id), None)
        if job is None or job.status is not JobStatus.PAUSED:
            return False
        if self._executor is None:
            return False
        job.pause_event.clear()
        job.status = JobStatus.PENDING
        self._finished_fired = False
        self.on_job_update(job)
        self._executor.submit(self._run_job, job)
        return True

    def shutdown(self) -> None:
        if self._shutdown:
            return
        self._shutdown = True
        self.cancel_all()
        if self._executor is not None:
            ex, self._executor = self._executor, None
            ex.shutdown(wait=False)

    # ── Execução ─────────────────────────────────────────────────────────

    def _out_for(self, entry: dict) -> tuple[str, str]:
        base = self.cfg.get("download_folder") or paths.user_downloads_default()
        out_dir = output_dir_for(base, entry,
                                 bool(self.cfg.get("organize_by_group", True)))
        os.makedirs(out_dir, exist_ok=True)
        stem = sanitize_filename(entry.get("title", ""), MAX_NAME_LEN)
        stem = os.path.basename(unique_path(out_dir, stem))
        return out_dir, os.path.join(out_dir, stem) + ".%(ext)s"

    def _run_job(self, job: DownloadJob) -> None:
        try:
            self._attempt(job)
        finally:
            self.on_job_update(job)
            self.on_progress(self._overall())
            self._maybe_finished()

    def _overall(self) -> float:
        if not self.jobs:
            return 100.0
        return sum(100.0 if j.status is JobStatus.DONE else j.percent
                   for j in self.jobs) / len(self.jobs)

    def _maybe_finished(self):
        if self._shutdown or self._finished_fired:
            return
        if any(j.status in (JobStatus.RUNNING, JobStatus.PENDING)
               for j in self.jobs):
            return
        self._finished_fired = True
        self.on_queue_finished()

    def _attempt(self, job: DownloadJob) -> None:
        while True:  # retry transitório com backoff
            job.attempt += 1
            try:
                self._download_once(job)
                return
            except _Cancelled:
                job.status = (JobStatus.PAUSED if job.pause_event.is_set()
                              else JobStatus.CANCELLED)
                self.on_log(("⏸ Pausado" if job.pause_event.is_set()
                             else "⚠ Cancelado") + f": {job.title}")
                return
            except Exception as exc:
                code, friendly, permanent = classify_download_error(
                    str(exc), None)
                job.error_code, job.error_message = code, friendly
                job.error_detail = str(exc)[-2000:]
                if code == "ytdlp_error" and "JS" in str(exc):
                    job.error_message = (
                        "Este vídeo do YouTube exige runtime JS (Deno), que "
                        "não é suportado no Android nesta versão.")
                    permanent = True
                if not permanent and job.attempt <= self.max_retries:
                    wait = min(2 ** job.attempt, 15)
                    self.on_log(f"  Falha transitória ({code}); nova "
                                f"tentativa em {wait}s…")
                    self._sleep(wait)
                    if job.cancel_event.is_set() or job.pause_event.is_set():
                        continue
                    continue
                job.status = JobStatus.FAILED
                self.on_log(f"✗ {friendly} [{redact_url(job.title)}]")
                return

    def _download_once(self, job: DownloadJob) -> None:
        if job.cancel_event.is_set() or job.pause_event.is_set():
            raise _Cancelled()
        self.on_log(f"↓ Baixando: {redact_url(job.title)}")
        job.status = JobStatus.RUNNING
        self.on_job_update(job)

        out_dir, out_tpl = self._out_for(job.entry)
        fmt = str(self.cfg.get("format", "original")).lower()
        ydl_fmt = FORMAT_MAP.get(fmt, FORMAT_MAP["original"])

        def hook(d):
            if job.cancel_event.is_set() or job.pause_event.is_set():
                raise _Cancelled()
            if d.get("status") == "downloading":
                total = (d.get("total_bytes") or d.get("total_bytes_estimate")
                         or 0)
                done = d.get("downloaded_bytes", 0)
                job.percent = (done / total * 100.0) if total else job.percent
                job.downloaded_bytes = done
                job.total_bytes = total or job.total_bytes
                speed = d.get("speed")
                job.speed = f"{speed / 1024 / 1024:.1f} MB/s" if speed else ""
                eta = d.get("eta")
                job.eta = time.strftime("%H:%M:%S", time.gmtime(eta)) if eta else ""
                if d.get("filename"):
                    job.output_path = d["filename"]
                self.on_job_update(job)
                self.on_progress(self._overall())
            elif d.get("status") == "finished":
                job.percent = 100.0
                if d.get("filename"):
                    job.output_path = d["filename"]

        if not self._ydl_mod:
            # Sem yt-dlp instalado (raro): fallback HTTP direto.
            stem = os.path.basename(out_tpl).replace("%(ext)s", "bin")
            dest = os.path.splitext(out_tpl)[0] + ".mp4" if ".%(ext)s" in out_tpl else out_tpl
            ok = http_download(
                job.entry["url"], dest.replace("%(ext)s", "mp4"),
                job.cancel_event,
                lambda p, g, t: (setattr(job, "percent", p),
                                 self.on_job_update(job),
                                 self.on_progress(self._overall())),
                self.on_log)
            if not ok:
                raise _Cancelled()
            job.output_path = dest.replace("%(ext)s", "mp4")
        else:
            opts = {
                "format": ydl_fmt,
                "outtmpl": out_tpl,
                "noplaylist": True,
                "quiet": True,
                "no_warnings": True,
                "continuedl": True,
                "windowsfilenames": True,
                "restrictfilenames": False,
                "progress_hooks": [hook],
                "merge_output_format": None,
            }
            with self._ydl_mod.YoutubeDL(opts) as ydl:
                ydl.download([job.entry["url"]])

        # Verificação (sem ffprobe no Android: existência + tamanho).
        path = job.output_path
        ok = bool(path) and os.path.isfile(path) and os.path.getsize(path) > 0
        if not ok:
            raise RuntimeError("Arquivo de saída não encontrado ou vazio.")
        job.status = JobStatus.DONE
        job.percent = 100.0
        self.on_log(f"✓ Concluído: {redact_url(job.title)}")
        notify(f"Download concluído", job.title)


# ── Notificações (só Android; desligam em desktop/teste) ─────────────────────

def notify(title: str, message: str) -> None:
    if not paths.is_android():
        return
    try:
        from plyer import notification  # type: ignore
        notification.notify(title=title, message=message, timeout=5)
    except Exception:
        pass
