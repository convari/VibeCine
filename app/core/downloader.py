# -*- coding: utf-8 -*-
"""Motor de download (Downloader v2).

Camadas:

1. Nomes de arquivo
   - sanitize_filename(): caracteres inválidos no Windows + limite de tamanho;
   - output_dir_for():    organização por grupo;
   - unique_path():       evita sobrescrita, resolve duplicados (-2, -3...).

2. Comando yt-dlp
   - build_ytdlp_command(): mesmo comportamento da versão original
     (Deno quando presente, limite de velocidade, formatos), acrescido de
     --no-overwrites, --continue (retomada de .part) e --newline.
   shell=False em todos os subprocessos.

3. Progresso real
   - parse_progress_line(): percentual, velocidade, ETA e bytes a partir
     do stdout do yt-dlp.

4. Erros e segurança
   - classify_download_error(): classifica a saída do yt-dlp em código
     estável + mensagem amigável; separa erros PERMANENTES (403, 404,
     privado, indisponível...) — sem retry — de TRANSITÓRIOS (timeout,
     rede, 5xx...) — retry com backoff progressivo e limite.
   - redact_url(): mascara credenciais (userinfo e parâmetros sensíveis
     como token/password) para nunca vazarem em logs.

5. Integridade pós-download
   - verify_output(): arquivo existe, tamanho > 0, duração válida via
     ffprobe quando disponível.

6. Fila de downloads (DownloadManager)
   - concorrência configurável (padrão: 2 simultâneos);
   - estados: aguardando, baixando, concluído, erro, cancelado, pausado;
   - cancelamento individual e geral (sem processos órfãos);
   - pause/resume: pausa encerra o yt-dlp preservando o .part; retomar
     recomeça com --continue exatamente de onde parou;
   - callbacks: on_log, on_job_update (estado/progresso de cada item),
     on_progress (percentual agregado da fila em tempo real).

A UI legada continua usando build_ytdlp_command diretamente; o manager é
a base da página de downloads da nova interface (Fase 3+).
"""

from __future__ import annotations

import os
import re
import subprocess
import threading
import time
import urllib.parse
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from enum import Enum

from .tools import resolve_tool_path
from . import proc as _proc

# ── Nomes de arquivo ─────────────────────────────────────────────────────────

_INVALID_CHARS_RE = re.compile(r'[<>:"/\\|?*\n\r]')
#: Mantém caminho total confortavelmente abaixo do limite de 260 do Windows.
MAX_NAME_LEN = 80


def sanitize_filename(name: str, max_len: int = MAX_NAME_LEN) -> str:
    """Remove caracteres proibidos e limita o comprimento (Windows)."""
    safe = _INVALID_CHARS_RE.sub("_", str(name or "")).strip().strip(".")
    safe = re.sub(r"\s+", " ", safe)
    if len(safe) > max_len:
        safe = safe[:max_len].rstrip(" ._")
    return safe or "download"


def output_dir_for(base: str, entry: dict, organize_by_group: bool = True) -> str:
    """Diretório de saída respeitando 'organizar por grupo'."""
    if organize_by_group and entry.get("group"):
        return os.path.join(base, sanitize_filename(entry["group"]))
    return base


def unique_path(directory: str, stem: str) -> str:
    """Evita sobrescrita silenciosa: devolve stem ou stem-2, stem-3...

    O yt-dlp escolhe a extensão, então a unicidade é verificada por prefixo.
    """
    candidate = stem
    n = 2
    while os.path.isdir(directory) and any(
        f == candidate or f.startswith(candidate + ".")
        for f in os.listdir(directory)
    ):
        candidate = f"{stem}-{n}"
        n += 1
    return os.path.join(directory, candidate)


# ── Mascaramento de URLs (segurança de logs) ─────────────────────────────────

#: Parâmetros de query tipicamente sensíveis em URLs de IPTV.
_SENSITIVE_PARAMS = {
    "token", "password", "passwd", "pass", "pwd", "key", "auth",
    "signature", "sig", "signup", "expire", "expires", "username",
}

#: Padrão seguro para exibição em logs quando a URL contém userinfo.
_CREDENTIAL_RE = re.compile(r"(://)[^/@\s]+@")


def redact_url(url: str) -> str:
    """Mascara credenciais e parâmetros sensíveis de uma URL para logs.

    "http://user:senha@host/x?token=abc&tipo=m3u" ->
    "http://***@host/x?token=***&tipo=m3u"
    """
    url = str(url or "")
    url = _CREDENTIAL_RE.sub(r"\1***@", url)
    try:
        parts = urllib.parse.urlsplit(url)
        if parts.query:
            pairs = urllib.parse.parse_qsl(parts.query, keep_blank_values=True)
            pairs = [(k, "***" if k.lower() in _SENSITIVE_PARAMS else v)
                     for k, v in pairs]
            query = urllib.parse.urlencode(pairs)
            url = urllib.parse.urlunsplit(
                (parts.scheme, parts.netloc, parts.path, query, parts.fragment))
    except ValueError:
        pass
    return url


# ── Classificação de erros de download ───────────────────────────────────────

#: (regex aplicada à saída do yt-dlp, código estável, mensagem amigável,
#:  permanente?). Ordem importa: a primeira correspondência vence.
_ERROR_PATTERNS: list[tuple[str, str, str, bool]] = [
    (r"Sign in to confirm|sign in|login required|cookies",
     "auth_required",
     "O YouTube pediu verificação de login. Atualize o yt-dlp (ATUALIZAR.bat) "
     "ou tente novamente mais tarde.", True),
    (r"Private video|This video is private",
     "private",
     "Este conteúdo é privado e não pode ser baixado.", True),
    (r"Video unavailable|no longer available|not available in your country|"
     r"has been removed",
     "unavailable",
     "Este conteúdo não está mais disponível (removido ou com restrição).", True),
    (r"HTTP Error 403|403: Forbidden",
     "forbidden",
     "Acesso negado (403). O link expirou ou exige permissões — peça um novo "
     "link ao provedor.", True),
    (r"HTTP Error 404|404: Not Found",
     "not_found",
     "Conteúdo não encontrado (404). O link foi removido ou está errado.", True),
    (r"Failed to resolve|nodename nor servname|Temporary failure in name "
     r"resolution|getaddrinfo failed",
     "dns_error",
     "Endereço não encontrado (falha de DNS). Confira a URL.", True),
    (r"Connection refused|refused",
     "refused",
     "Conexão recusada pelo servidor. Ele pode estar fora do ar.", False),
    (r"timed out|timeout",
     "timeout",
     "O servidor demorou demais para responder.", False),
    (r"HTTP Error 5\d\d",
     "server_error",
     "O servidor do conteúdo falhou (erro 5xx). Tente novamente em instantes.",
     False),
    (r"Unable to download|Download error|network",
     "network_error",
     "Falha de rede durante o download.", False),
]

#: Códigos que NUNCA devem ser repetidos automaticamente.
PERMANENT_ERROR_CODES = {
    code for (_, code, _, permanent) in _ERROR_PATTERNS if permanent
} | {"corrupted", "invalid_url"}


def classify_download_error(output_text: str, returncode: int | None = None
                            ) -> tuple[str, str, bool]:
    """Classifica a falha a partir do texto do yt-dlp.

    Retorna (codigo, mensagem_amigavel, permanente).
    """
    text = output_text or ""
    for pattern, code, friendly, permanent in _ERROR_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE):
            return code, friendly, permanent
    code = "ytdlp_error"
    friendly = (f"O download falhou (código {returncode}). "
                "Consulte o log para detalhes técnicos.")
    return code, friendly, True


# ── Montagem do comando yt-dlp ───────────────────────────────────────────────

_FORMAT_ARGS = {
    "mp3":     ["-f", "ba/b", "-x", "--audio-format", "mp3", "--audio-quality", "0"],
    "fullhd":  ["-f", "bv*[height<=1080]+ba/b[height<=1080]", "--merge-output-format", "mp4"],
    "mp4":     ["-f", "bv*[ext=mp4]+ba[ext=m4a]/bv*+ba/b", "--merge-output-format", "mp4"],
    "original": ["-f", "bv*+ba/b"],
}


def build_ytdlp_command(entry: dict, cfg: dict, unique_names: bool = False
                        ) -> tuple[list[str], dict]:
    """Monta (comando, contexto) para baixar uma entrada.

    Contexto inclui out_dir, out_template, stem e avisos (ex.: deno ausente).
    Com unique_names=True, garante que o nome não colida com arquivos
    já existentes na pasta de saída (usado pela fila).
    """
    warnings: list[str] = []

    ytdlp = resolve_tool_path(cfg.get("ytdlp_path", "yt-dlp.exe"), "yt-dlp.exe")
    ffmpeg = resolve_tool_path(cfg.get("ffmpeg_path", "ffmpeg.exe"), "ffmpeg.exe")
    deno = resolve_tool_path(cfg.get("deno_path", "deno.exe"), "deno.exe", allow_missing=True)

    base = cfg.get("download_folder", "m3u_downloads")
    out_dir = output_dir_for(base, entry, bool(cfg.get("organize_by_group", True)))

    cmd = [
        ytdlp,
        "--ffmpeg-location", os.path.dirname(ffmpeg),
        "--no-warnings",
        "--no-playlist",
        "--no-overwrites",          # nunca sobrescrever um download pronto
        "--continue",               # retomar .part de execuções anteriores
        "--newline",                # uma linha de progresso por atualização
    ]

    if os.path.isfile(deno):
        cmd += ["--js-runtimes", f"deno:{deno}"]
    else:
        warnings.append("Deno não encontrado. Execute ATUALIZAR.bat antes de baixar do YouTube.")

    speed = str(cfg.get("speed_limit") or "0")
    if speed != "0":
        cmd += ["--limit-rate", speed]

    fmt = str(cfg.get("format") or "original").lower()
    cmd += _FORMAT_ARGS.get(fmt, _FORMAT_ARGS["original"])

    stem = sanitize_filename(entry.get("title", ""))
    if unique_names and os.path.isdir(out_dir):
        stem = os.path.basename(unique_path(out_dir, stem))
    out_tpl = os.path.join(out_dir, stem) + ".%(ext)s"
    cmd += ["-o", out_tpl, entry["url"]]

    ctx = {
        "out_dir": out_dir,
        "out_template": out_tpl,
        "stem": stem,
        "warnings": warnings,
        "ytdlp": ytdlp, "ffmpeg": ffmpeg, "deno": deno,
    }
    return cmd, ctx


# ── Progresso real (parse do stdout do yt-dlp) ───────────────────────────────

_PROGRESS_RE = re.compile(
    r"\[download\]\s+"
    r"(?P<pct>[\d.]+)%"
    r"(?:\s+of\s+~?\s*(?P<total>[\d.]+\s*\S+))?"
    r"(?:\s+at\s+(?P<speed>[\d.]+\s*\S+/s))?"
    r"(?:\s+ETA\s+(?P<eta>[\d:]+|Unknown))?"
)

_SIZE_UNITS = {"b": 1, "kib": 1024, "mib": 1024 ** 2, "gib": 1024 ** 3,
               "kb": 1000, "mb": 1000 ** 2, "gb": 1000 ** 3}


def _size_to_bytes(text: str | None) -> float:
    if not text:
        return 0.0
    m = re.match(r"([\d.]+)\s*(\w+)", text.strip(), re.I)
    if not m:
        return 0.0
    return float(m.group(1)) * _SIZE_UNITS.get(m.group(2).lower(), 1.0)


def parse_progress_line(line: str) -> dict | None:
    """Extrai progresso de uma linha do yt-dlp (ou None se não for progresso).

    Exemplo: "[download]  45.2% of ~120.50MiB at 3.20MiB/s ETA 00:12"
    -> {"percent": 45.2, "total_bytes": ..., "speed": "3.20MiB/s",
        "eta": "00:12", "downloaded_bytes": ...}
    """
    m = _PROGRESS_RE.search(line)
    if not m:
        return None
    percent = float(m.group("pct"))
    total = _size_to_bytes(m.group("total"))
    return {
        "percent": percent,
        "total_bytes": total,
        "downloaded_bytes": total * percent / 100.0,
        "speed": (m.group("speed") or "").strip(),
        "speed_bytes": _size_to_bytes((m.group("speed") or "").replace("/s", "")),
        "eta": m.group("eta") or "",
    }


# ── Detecção do arquivo de saída nas linhas do yt-dlp ────────────────────────

_DEST_PATTERNS = (
    re.compile(r"\[download\]\s+Destination:\s+(?P<path>.+)$"),
    re.compile(r"\[Merger\]\s+Merging formats into\s+\"(?P<path>[^\"]+)\""),
    re.compile(r"\[ExtractAudio\]\s+Destination:\s+(?P<path>.+)$"),
    re.compile(r"^(?:\[download\]\s+)?(?P<path>.+?)\s+has already been "
               r"downloaded", re.IGNORECASE),
)


def parse_output_path(line: str) -> str | None:
    """Detecta o caminho do arquivo produzido em uma linha do yt-dlp."""
    for pattern in _DEST_PATTERNS:
        m = pattern.search(line)
        if m:
            return m.group("path").strip().strip('"')
    return None


# ── Verificação pós-download ─────────────────────────────────────────────────

def verify_output(path: str, ffprobe_path: str = "") -> tuple[bool, str]:
    """Valida o arquivo baixado: existe, não é vazio e tem duração legível.

    Retorna (ok, motivo). Se ffprobe não estiver disponível, valida apenas
    existência/tamanho (sem marcar como corrompido indevidamente).
    """
    if not path:
        return False, "Não foi possível identificar o arquivo de saída."
    if not os.path.isfile(path):
        return False, "Arquivo não encontrado após o download."
    if os.path.getsize(path) == 0:
        return False, "Arquivo vazio (0 bytes)."
    if ffprobe_path and os.path.isfile(ffprobe_path):
        try:
            r = _proc.run(
                [ffprobe_path, "-v", "error", "-show_entries", "format=duration",
                 "-of", "default=noprint_wrappers=1:nokey=1", path],
                capture_output=True, text=True, timeout=30)
            duration = r.stdout.strip()
            if not duration or float(duration or 0) <= 0:
                return False, "Arquivo sem duração válida (possivelmente corrompido)."
        except (subprocess.SubprocessError, ValueError):
            # Não conclui integridade — não reprova o arquivo por isso.
            pass
    return True, ""


# ── Fila de downloads (Downloader v2) ────────────────────────────────────────

class JobStatus(str, Enum):
    PENDING = "aguardando"
    RUNNING = "baixando"
    DONE = "concluido"
    FAILED = "erro"
    CANCELLED = "cancelado"
    PAUSED = "pausado"


@dataclass
class DownloadJob:
    """Um item da fila, com estado, métricas e controle individual."""

    id: int
    entry: dict
    status: JobStatus = JobStatus.PENDING
    percent: float = 0.0
    downloaded_bytes: float = 0.0
    total_bytes: float = 0.0
    speed: str = ""
    eta: str = ""
    output_path: str = ""
    error_code: str = ""
    error_message: str = ""
    error_detail: str = ""
    attempt: int = 0

    process: subprocess.Popen | None = field(default=None, repr=False)
    cancel_event: threading.Event = field(default_factory=threading.Event,
                                          repr=False)
    pause_event: threading.Event = field(default_factory=threading.Event,
                                         repr=False)

    @property
    def title(self) -> str:
        return self.entry.get("title", "")


class DownloadManager:
    """Fila com concorrência configurável, progresso real e controle total.

    Callbacks (chamados a partir de threads — a UI deve despachar via
    queue/after):
      on_log(msg)            -> linha de log (URLs já mascaradas)
      on_job_update(job)     -> mudança de estado/progresso de um item
      on_progress(percent)   -> progresso agregado da fila (0..100)
      on_queue_finished()    -> todos os trabalhos finalizaram

    Uso típico:
        dm = DownloadManager(cfg, max_workers=2)
        dm.start(entries)
        dm.cancel_job(job_id) / dm.pause_job(job_id) / dm.resume_job(job_id)
        dm.cancel_all(); dm.shutdown()
    """

    def __init__(self, cfg: dict, max_workers: int = 2, max_retries: int = 2,
                 on_log=lambda m: None, on_job_update=lambda j: None,
                 on_progress=lambda p: None, on_queue_finished=lambda: None,
                 command_builder=None, sleeper=time.sleep):
        self.cfg = cfg
        self.max_workers = max(1, int(max_workers))
        self.max_retries = max(0, int(max_retries))
        self.on_log = on_log
        self.on_job_update = on_job_update
        self.on_progress = on_progress
        self.on_queue_finished = on_queue_finished
        # Pontos de injeção para testes:
        self._build_command = command_builder or build_ytdlp_command
        self._sleep = sleeper

        self.jobs: list[DownloadJob] = []
        self._executor: ThreadPoolExecutor | None = None
        self._lock = threading.Lock()
        self._job_dir: dict[int, DownloadJob] = {}
        self._shutdown = False
        self._finished_fired = False

    # ── API pública ─────────────────────────────────────────────────────

    def start(self, entries: list[dict]) -> list[DownloadJob]:
        """Cria os trabalhos e inicia a fila em background."""
        with self._lock:
            self._shutdown = False
            self._finished_fired = False
            self.jobs = [DownloadJob(id=i, entry=e)
                         for i, e in enumerate(entries)]
            self._job_dir = {j.id: j for j in self.jobs}
            if not self.jobs:
                return self.jobs
            for job in self.jobs:
                self.on_job_update(job)
            self._executor = ThreadPoolExecutor(
                max_workers=self.max_workers,
                thread_name_prefix="vibcine-dl")
            for job in self.jobs:
                self._executor.submit(self._run_job, job)
        return self.jobs

    def add(self, entries: list[dict]) -> list[DownloadJob]:
        """Adiciona itens à fila (em execução, ociosa ou recém-criada).

        Os novos trabalhos são anexados ao final e submetidos ao executor;
        trabalhos anteriores (inclusive os concluídos) são preservados.
        """
        entries = list(entries)
        if not entries:
            return []
        with self._lock:
            self._shutdown = False
            self._finished_fired = False
            if self._executor is None:
                self._executor = ThreadPoolExecutor(
                    max_workers=self.max_workers,
                    thread_name_prefix="vibcine-dl")
            start_id = (max(self._job_dir) + 1) if self._job_dir else 0
            new_jobs = [DownloadJob(id=start_id + i, entry=e)
                        for i, e in enumerate(entries)]
            self.jobs.extend(new_jobs)
            self._job_dir.update({j.id: j for j in new_jobs})
            for job in new_jobs:
                self.on_job_update(job)
                self._executor.submit(self._run_job, job)
        return new_jobs

    def cancel_job(self, job_id: int) -> None:
        job = self._job_dir.get(job_id)
        if job is None or job.status in (JobStatus.DONE, JobStatus.FAILED,
                                         JobStatus.CANCELLED):
            return
        job.cancel_event.set()
        self._terminate_process(job)

    def cancel_all(self) -> None:
        self.on_log("⚠ Cancelando todos os downloads…")
        for job in list(self.jobs):
            if job.status in (JobStatus.DONE, JobStatus.FAILED,
                              JobStatus.CANCELLED):
                continue
            job.cancel_event.set()
            self._terminate_process(job)

    def pause_job(self, job_id: int) -> None:
        """Pausa interrompendo o yt-dlp e PRESERVANDO o arquivo .part.

        A retomada (resume_job) reexecuta o comando, que continua de onde
        parou graças ao --continue.
        """
        job = self._job_dir.get(job_id)
        if job is None or job.status is not JobStatus.RUNNING:
            return
        job.pause_event.set()
        self._terminate_process(job)

    def resume_job(self, job_id: int) -> bool:
        """Retoma um download pausado (o .part é aproveitado)."""
        job = self._job_dir.get(job_id)
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

    def shutdown(self, wait_timeout: float = 10.0) -> None:
        """Encerra tudo: cancela, mata processos e aguarda o executor.

        Garante que nenhum subprocesso fique órfão ao fechar o app.
        """
        with self._lock:
            if self._shutdown:
                return
            self._shutdown = True
        self.cancel_all()
        # Aguarda os jobs finalizarem (com prazo), depois força o encerramento.
        deadline = time.monotonic() + wait_timeout
        while time.monotonic() < deadline:
            if all(j.status in (JobStatus.DONE, JobStatus.FAILED,
                                JobStatus.CANCELLED, JobStatus.PAUSED,
                                JobStatus.PENDING) and
                   (j.process is None or j.process.poll() is not None)
                   for j in self.jobs):
                break
            time.sleep(0.02)
        for job in self.jobs:
            self._terminate_process(job, kill=True)
        if self._executor is not None:
            executor, self._executor = self._executor, None
            executor.shutdown(wait=False)

    # ── Internos ────────────────────────────────────────────────────────

    _TERMINAL = frozenset({JobStatus.DONE, JobStatus.FAILED,
                           JobStatus.CANCELLED})

    def _terminate_process(self, job: DownloadJob, kill: bool = False) -> None:
        proc = job.process
        if proc is None or proc.poll() is not None:
            return
        try:
            proc.kill() if kill else proc.terminate()
        except OSError:
            pass

    def _maybe_finished(self) -> None:
        """Dispara on_queue_finished quando todos os jobs terminaram.

        A fila só 'termina' quando não há nada em andamento/aguardando;
        jobs PAUSADOS permitem retomada posterior (resume_job).
        """
        if self._shutdown or self._finished_fired:
            return
        active = {JobStatus.RUNNING, JobStatus.PENDING}
        if any(j.status in active for j in self.jobs):
            return
        # Todos em estado final ou pausado: dispara uma vez por sessão.
        if not any(j.status is JobStatus.RUNNING for j in self.jobs):
            self._finished_fired = True
            self.on_queue_finished()

    def _overall_progress(self) -> float:
        if not self.jobs:
            return 100.0
        total = sum(
            100.0 if j.status is JobStatus.DONE else j.percent
            for j in self.jobs
        )
        return total / len(self.jobs)

    @staticmethod
    def _safe_title(job: DownloadJob) -> str:
        """Título pronto para log (mascara credenciais se contiver URL)."""
        return redact_url(job.title)

    def _log_line(self, line: str, job: DownloadJob) -> None:
        """Log com URLs mascaradas (nunca vaza credenciais)."""
        self.on_log("  " + redact_url(line))

    def _run_job(self, job: DownloadJob) -> None:
        try:
            # Respeita cancelamento emitido antes do início efetivo.
            if job.cancel_event.is_set():
                job.status = JobStatus.CANCELLED
                self.on_job_update(job)
                self.on_progress(self._overall_progress())
                return

            while True:  # laço de retry (apenas erros transitórios)
                job.attempt += 1
                stop = self._run_attempt(job)
                if stop:
                    break
            self.on_job_update(job)
            self.on_progress(self._overall_progress())
        finally:
            self._maybe_finished()

    def _run_attempt(self, job: DownloadJob) -> bool:
        """Executa uma tentativa. Retorna True para não tentar de novo."""
        entry = job.entry
        try:
            cmd, ctx = self._build_command(entry, self.cfg, unique_names=False)
            os.makedirs(ctx["out_dir"], exist_ok=True)
            for warning in ctx["warnings"]:
                self.on_log(f"  ⚠ {warning}")

            job.status = JobStatus.RUNNING
            self.on_job_update(job)
            self.on_log(f"↓ Baixando: {self._safe_title(job)}"
                        + (f" (tentativa {job.attempt})" if job.attempt > 1 else ""))

            job.process = _proc.popen(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, bufsize=1)  # shell=False; sem janela (CREATE_NO_WINDOW)

            output_tail: list[str] = []  # últimas linhas p/ diagnóstico
            assert job.process.stdout is not None
            for line in job.process.stdout:
                line = line.rstrip()
                if not line:
                    continue
                prog = parse_progress_line(line)
                if prog:
                    job.percent = prog["percent"]
                    job.downloaded_bytes = prog["downloaded_bytes"]
                    job.total_bytes = prog["total_bytes"] or job.total_bytes
                    job.speed = prog["speed"]
                    job.eta = prog["eta"]
                    self.on_job_update(job)
                    self.on_progress(self._overall_progress())
                else:
                    out = parse_output_path(line)
                    if out:
                        job.output_path = out
                    self._log_line(line, job)
                output_tail.append(line)
                if len(output_tail) > 40:
                    output_tail.pop(0)
                if job.cancel_event.is_set() or job.pause_event.is_set():
                    self._terminate_process(job)
                    break

            returncode = job.process.wait()
            try:
                if job.process.stdout is not None:
                    job.process.stdout.close()
            except OSError:
                pass
            job.process = None

            if job.cancel_event.is_set():
                job.status = JobStatus.CANCELLED
                self.on_log(f"⚠ Cancelado: {self._safe_title(job)}")
                return True

            if job.pause_event.is_set():
                job.status = JobStatus.PAUSED
                self.on_log(f"⏸ Pausado (arquivo .part preservado): {self._safe_title(job)}")
                return True

            if returncode == 0:
                ok, reason = verify_output(
                    job.output_path, os.path.join(
                        os.path.dirname(ctx["ffmpeg"]), "ffprobe.exe"))
                if ok:
                    job.status = JobStatus.DONE
                    job.percent = 100.0
                    self.on_log(f"✓ Concluído: {self._safe_title(job)}")
                else:
                    job.status = JobStatus.FAILED
                    job.error_code = "corrupted"
                    job.error_message = (
                        f"Download finalizado, mas o arquivo é inválido: {reason}")
                    job.error_detail = reason
                    self.on_log(f"✗ Arquivo inválido/incompleto: {self._safe_title(job)} — {reason}")
                return True

            # Falha do yt-dlp: classifica e decide sobre retry.
            combined = "\n".join(output_tail)
            code, friendly, permanent = classify_download_error(combined, returncode)
            job.error_code = code
            job.error_message = friendly
            job.error_detail = combined[-2000:]

            if not permanent and job.attempt <= self.max_retries:
                wait = min(2 ** job.attempt, 15)
                self.on_log(
                    f"  Falha transitória ({code}); tentando de novo em {wait}s…")
                self._sleep(wait)
                if job.cancel_event.is_set():
                    job.status = JobStatus.CANCELLED
                    return True
                if job.pause_event.is_set():
                    job.status = JobStatus.PAUSED
                    return True
                return False  # retry

            job.status = JobStatus.FAILED
            self.on_log(f"✗ {friendly} [{self._safe_title(job)}]")
            return True

        except Exception as exc:  # falha local (permissão, disco, yt-dlp ausente)
            job.status = JobStatus.FAILED
            job.error_code = "local_error"
            job.error_message = f"Erro ao iniciar o download: {exc}"
            job.error_detail = repr(exc)
            self.on_log(f"✗ Erro em '{self._safe_title(job)}': {exc}")
            return True


#: Alias de conveniência (nome usado em versões preliminares da Fase 1).
DownloadQueue = DownloadManager
