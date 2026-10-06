# -*- coding: utf-8 -*-
"""Testes abrangentes do Downloader v2 (app.core.downloader).

Cobre: classificação de erros, mascaramento de URLs, detecção do arquivo
de saída, nomes únicos, progresso real, fila, concorrência, cancelamento,
pause/resume, retry de erros transitórios e ausência de órfãos.
"""

import os
import sys
import tempfile
import time
import unittest

from app.core.downloader import (
    DownloadManager, JobStatus, PERMANENT_ERROR_CODES, classify_download_error,
    parse_output_path, parse_progress_line, redact_url, unique_path,
    verify_output,
)

HERE = os.path.dirname(os.path.abspath(__file__))
FAKE = os.path.join(HERE, "_fake_ytdlp.py")


def wait_until(predicate, timeout=15.0, interval=0.05):
    """Espera ativa curta para condição de teste; retorna bool."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(interval)
    return predicate()


class FakeYtDlp:
    """Constrói comandos para o yt-dlp falso (python _fake_ytdlp.py).

    O stem de saída usa o TÍTULO sanitizado da entrada (único nos testes),
    evitando colisões de arquivo entre jobs simultâneos.
    """

    def __init__(self, workdir):
        self.workdir = workdir

    def __call__(self, entry, cfg, unique_names=False):
        from app.core.downloader import sanitize_filename
        stem = sanitize_filename(entry.get("title") or
                                 entry["url"].replace("fake://", "").split("?")[0]
                                 or "item")
        template = os.path.join(self.workdir, stem + "-%(ext)s")
        ctx = {
            "out_dir": self.workdir,
            "out_template": template,
            "stem": stem,
            "warnings": [],
            # ffprobe dentro do workdir (vazio) — sem vazar ferramenta real
            "ytdlp": "fake", "ffmpeg": os.path.join(self.workdir, "fake-ffmpeg.exe"),
            "deno": "fake",
        }
        cmd = [sys.executable, FAKE, "-o", template, entry["url"]]
        return cmd, ctx


def make_entry(url, title=None):
    return {"title": title or url.replace("fake://", ""), "group": "T",
            "logo": "", "tvg_id": "", "tvg_name": "", "url": url,
            "type": "filme"}


class TestErrorClassification(unittest.TestCase):
    def _c(self, text):
        return classify_download_error(text, 1)

    def test_permanentes(self):
        for text, code in (
            ("ERROR: HTTP Error 403: Forbidden", "forbidden"),
            ("HTTP Error 404: Not Found", "not_found"),
            ("ERROR: This video is private", "private"),
            ("Video unavailable", "unavailable"),
            ("Sign in to confirm you're not a bot", "auth_required"),
            ("Failed to resolve hostname", "dns_error"),
        ):
            c, msg, permanent = self._c(text)
            self.assertEqual(c, code, msg=text)
            self.assertTrue(permanent, msg=code)
            self.assertIn(code, PERMANENT_ERROR_CODES)
            self.assertTrue(msg)

    def test_transitorios(self):
        for text, code in (
            ("The read operation timed out", "timeout"),
            ("HTTP Error 503", "server_error"),
            ("Connection refused", "refused"),
        ):
            c, _, permanent = self._c(text)
            self.assertEqual(c, code, msg=text)
            self.assertFalse(permanent, msg=code)

    def test_desconhecido(self):
        c, msg, permanent = classify_download_error("algo estranho", 9)
        self.assertEqual(c, "ytdlp_error")
        self.assertIn("9", msg)


class TestRedactUrl(unittest.TestCase):
    def test_userinfo(self):
        r = redact_url("http://usuario:senha123@host.tv/lista.m3u")
        self.assertNotIn("senha123", r)
        self.assertIn("***@host.tv", r)

    def test_parametros_sensiveis(self):
        r = redact_url("http://h.tv/x?token=abc123&tipo=m3u&password=zzz")
        self.assertNotIn("abc123", r)
        self.assertNotIn("zzz", r)
        self.assertIn("tipo=m3u", r)

    def test_url_normal_intacta(self):
        u = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
        self.assertEqual(redact_url(u), u)


class TestOutputPathDetection(unittest.TestCase):
    def test_destination(self):
        self.assertEqual(
            parse_output_path("[download] Destination: C:/x/video.mp4"),
            "C:/x/video.mp4")

    def test_merger(self):
        self.assertEqual(
            parse_output_path('[Merger] Merging formats into "C:/x/v.mkv"'),
            "C:/x/v.mkv")

    def test_ja_baixado(self):
        self.assertEqual(
            parse_output_path("[download] C:/x/v.mp4 has already been downloaded"),
            "C:/x/v.mp4")

    def test_linhas_comuns_nao_detectam(self):
        self.assertIsNone(parse_output_path("[download]  10.0% of ~5MiB"))


class TestProgressoReal(unittest.TestCase):
    def test_bytes_baixados_e_eta(self):
        p = parse_progress_line(
            "[download]  25.0% of ~100.00MiB at   5.00MiB/s ETA 00:15")
        self.assertEqual(p["percent"], 25.0)
        self.assertAlmostEqual(p["downloaded_bytes"], 25 * 1024 * 1024)
        self.assertAlmostEqual(p["total_bytes"], 100 * 1024 * 1024)
        self.assertEqual(p["eta"], "00:15")
        self.assertIn("MiB/s", p["speed"])


class TestUniquePath(unittest.TestCase):
    def test_duplicados_previsiveis(self):
        with tempfile.TemporaryDirectory() as td:
            open(os.path.join(td, "filme.mp4"), "w").close()
            open(os.path.join(td, "filme-2.mkv"), "w").close()
            p = unique_path(td, "filme")
            self.assertEqual(os.path.basename(p), "filme-3")

    def test_sem_colisao(self):
        with tempfile.TemporaryDirectory() as td:
            self.assertEqual(os.path.basename(unique_path(td, "novo")), "novo")


class ManagerCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.logs: list[str] = []
        self.updates: list[tuple[int, JobStatus, float]] = []
        self.overall: list[float] = []
        self.finished = []
        self.dm = None

    def tearDown(self):
        if self.dm is not None:
            self.dm.shutdown(wait_timeout=5)

    def make_manager(self, entries, **kwargs):
        builder = FakeYtDlp(self.tmp.name)
        callbacks = dict(
            on_log=self.logs.append,
            on_job_update=lambda j: self.updates.append(
                (j.id, j.status, j.percent)),
            on_progress=self.overall.append,
            on_queue_finished=lambda: self.finished.append(True),
            command_builder=builder,
            sleeper=lambda s: time.sleep(0.02),  # backoff acelerado nos testes
        )
        callbacks.update(kwargs)
        self.dm = DownloadManager({}, **callbacks)
        self.dm.start(entries)
        return self.dm


class TestManagerBasico(ManagerCase):
    def test_sucesso_completo(self):
        self.make_manager([make_entry("fake://ok")])
        self.assertTrue(wait_until(lambda: self.finished))
        job = self.dm.jobs[0]
        self.assertIs(job.status, JobStatus.DONE)
        self.assertEqual(job.percent, 100.0)
        self.assertTrue(job.output_path)
        self.assertTrue(os.path.isfile(job.output_path))
        self.assertGreater(os.path.getsize(job.output_path), 0)
        self.assertTrue(any(p[1] is JobStatus.RUNNING for p in self.updates))
        self.assertTrue(any(v > 0 for v in self.overall))
        self.assertEqual(self.overall[-1], 100.0)

    def test_estados_exigidos_existem(self):
        valores = {s.value for s in JobStatus}
        self.assertEqual(valores, {"aguardando", "baixando", "concluido",
                                   "erro", "cancelado", "pausado"})

    def test_erro_permanente_sem_retry(self):
        self.make_manager([make_entry("fake://403")], max_retries=3)
        self.assertTrue(wait_until(lambda: self.finished))
        job = self.dm.jobs[0]
        self.assertIs(job.status, JobStatus.FAILED)
        self.assertEqual(job.error_code, "forbidden")
        self.assertIn("expirou", job.error_message)
        self.assertEqual(job.attempt, 1)  # permanente: nenhuma repetição
        self.assertTrue(job.error_detail)  # detalhe técnico preservado

    def test_retry_em_erro_transitorio(self):
        self.make_manager([make_entry("fake://flaky")], max_retries=2)
        self.assertTrue(wait_until(lambda: self.finished))
        job = self.dm.jobs[0]
        self.assertIs(job.status, JobStatus.DONE)
        self.assertEqual(job.attempt, 2)  # 1 falha transitória + 1 sucesso

    def test_cancelamento_individual_sem_orfaos(self):
        self.make_manager([make_entry("fake://slow?0.3", "lento")])
        self.assertTrue(wait_until(
            lambda: self.dm.jobs[0].status is JobStatus.RUNNING))
        self.dm.cancel_job(0)
        self.assertTrue(wait_until(lambda: self.finished))
        job = self.dm.jobs[0]
        self.assertIs(job.status, JobStatus.CANCELLED)
        self.assertIsNone(job.process)
        # Nenhum processo vivo após o cancelamento
        for j in self.dm.jobs:
            if j.process is not None:
                self.assertIsNotNone(j.process.poll())

    def test_cancelar_todos(self):
        entries = [make_entry("fake://slow?0.3", f"s{i}") for i in range(3)]
        self.make_manager(entries)
        time.sleep(0.3)
        self.dm.cancel_all()
        self.assertTrue(wait_until(lambda: self.finished))
        self.assertTrue(all(
            j.status in (JobStatus.CANCELLED, JobStatus.DONE)
            for j in self.dm.jobs))
        self.assertGreaterEqual(
            sum(1 for j in self.dm.jobs if j.status is JobStatus.CANCELLED), 1)

    def test_pause_e_resume_preserva_part(self):
        entries = [make_entry("fake://slow?0.2", "A"),
                   make_entry("fake://slow?0.25", "B")]
        self.make_manager(entries)
        self.assertTrue(wait_until(
            lambda: self.dm.jobs[0].status is JobStatus.RUNNING))
        self.dm.pause_job(0)
        self.assertTrue(wait_until(
            lambda: self.dm.jobs[0].status is JobStatus.PAUSED))
        self.assertIn("Pausado", "".join(self.logs))
        # Despausa enquanto o outro job mantém o executor vivo
        self.assertTrue(self.dm.resume_job(0))
        self.assertTrue(wait_until(lambda: self.finished, timeout=30))
        self.assertIs(self.dm.jobs[0].status, JobStatus.DONE)
        self.assertIs(self.dm.jobs[1].status, JobStatus.DONE)

    def test_concorrencia_configuravel(self):
        # Mede a sobreposição REAL por timestamps gravados pelo yt-dlp falso
        # (independente da velocidade da máquina).
        conc_base = os.path.join(self.tmp.name, "conc")
        old_env = os.environ.get("VIBE_FAKE_CONC")
        os.environ["VIBE_FAKE_CONC"] = conc_base
        entries = [make_entry("fake://slow?0.15", f"c{i}") for i in range(3)]
        try:
            self.make_manager(entries, max_workers=2)
            self.assertTrue(wait_until(lambda: self.finished, timeout=60))
        finally:
            if old_env is None:
                os.environ.pop("VIBE_FAKE_CONC", None)
            else:
                os.environ["VIBE_FAKE_CONC"] = old_env
        self.assertTrue(all(j.status is JobStatus.DONE for j in self.dm.jobs))
        intervals = []
        for name in os.listdir(self.tmp.name):
            if name.startswith("conc."):
                for line in open(os.path.join(self.tmp.name, name)):
                    a, b = line.split()
                    intervals.append((float(a), float(b)))
        self.assertEqual(len(intervals), 3)
        # Eventos (start=+1, end=-1): o pico de simultaneidade deve ser 2.
        events = sorted([(a, 1) for a, _ in intervals] +
                        [(b, -1) for _, b in intervals])
        cur = peak = 0
        for _, delta in events:
            cur += delta
            peak = max(peak, cur)
        self.assertEqual(peak, 2)

    def test_progresso_agregado_e_tempo_real(self):
        self.make_manager([make_entry("fake://ok"), make_entry("fake://ok")])
        self.assertTrue(wait_until(lambda: self.finished))
        # callbacks incrementais intermediários + 100 no final
        self.assertGreater(len(self.overall), 4)
        self.assertAlmostEqual(self.overall[-1], 100.0)

    def test_logs_mascaram_credenciais(self):
        self.make_manager(
            [make_entry("fake://403",
                        "segredo http://user:senha@h.tv/x?token=abc")])
        self.assertTrue(wait_until(lambda: self.finished))
        joined = "\n".join(self.logs)
        self.assertNotIn("senha", joined)


class TestVerifyOutput(unittest.TestCase):
    def test_arquivos(self):
        with tempfile.TemporaryDirectory() as td:
            vazio = os.path.join(td, "v.mp4")
            open(vazio, "w").close()
            ok, _ = verify_output(vazio)
            self.assertFalse(ok)
            cheio = os.path.join(td, "c.mp4")
            with open(cheio, "wb") as fh:
                fh.write(b"12345")
            ok, _ = verify_output(cheio, ffprobe_path="inexistente.exe")
            self.assertTrue(ok)
            ok, motivo = verify_output(os.path.join(td, "nao_existe.mp4"))
            self.assertFalse(ok)
            self.assertTrue(motivo)


if __name__ == "__main__":
    unittest.main()
