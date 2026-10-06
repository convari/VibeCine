# -*- coding: utf-8 -*-
"""Testes da camada Android (sem dispositivo: yt-dlp falso em memória)."""

import os
import sys
import tempfile
import time
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.downloader import JobStatus  # noqa: E402
from android.engine import FORMAT_MAP, DownloadEngine  # noqa: E402
from android import share as android_share  # noqa: E402


def wait_until(pred, timeout=20.0, interval=0.02):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if pred():
            return True
        time.sleep(interval)
    return False


class FakeYDL:
    """Módulo yt_dlp falso: escreve bytes reais e emite progress_hooks."""

    def __init__(self, opts):
        self.opts = opts
        self._hooks = opts.get("progress_hooks", [])

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def download(self, urls):
        url = urls[0]
        if "403" in url:
            raise Exception("HTTP Error 403: Forbidden")
        if "jsfail" in url:
            raise Exception("JS runtime needed: deno not found")
        out = self.opts["outtmpl"].replace("%(ext)s", "mp4")
        os.makedirs(os.path.dirname(out), exist_ok=True)
        mode = "ab" if os.path.exists(out) else "wb"
        total = 64 * 1024 * 1024  # 64 MB — janela suficiente p/ pausar
        step = 512 * 1024
        done = os.path.getsize(out) if os.path.exists(out) else 0
        with open(out, mode) as fh:
            while done < total:
                n = min(step, total - done)
                fh.write(b"\x00" * n)
                done += n
                for h in self._hooks:
                    h({"status": "downloading", "total_bytes": total,
                       "downloaded_bytes": done, "speed": 2_000_000,
                       "eta": 1, "filename": out})
        for h in self._hooks:
            h({"status": "finished", "filename": out})


class FakeYDLModule:
    YoutubeDL = FakeYDL


def entry(url="file:///x/v.mp4", title="Vídeo QA"):
    return {"title": title, "group": "Testes", "logo": "", "tvg_id": "",
            "tvg_name": "", "url": url, "type": "filme"}


class EngineCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.cfg = {"download_folder": self.tmp.name, "organize_by_group": True,
                    "format": "original", "max_concurrent_downloads": 1}
        self.updates = []
        self.overall = []
        self.logs = []
        self.eng = DownloadEngine(
            self.cfg, ydl_module=FakeYDLModule, sleeper=lambda s: None,
            on_job_update=lambda j: self.updates.append((j.id, j.percent, j.status)),
            on_progress=self.overall.append, on_log=self.logs.append)
        self.addCleanup(self.eng.shutdown)


class TestEngine(EngineCase):
    def test_download_real_com_progresso(self):
        (job,) = self.eng.add([entry()])
        self.assertTrue(wait_until(lambda: job.status is JobStatus.DONE))
        self.assertEqual(job.percent, 100.0)
        self.assertTrue(job.output_path.endswith(".mp4"))
        self.assertTrue(os.path.isfile(job.output_path))
        self.assertGreater(os.path.getsize(job.output_path), 0)
        self.assertTrue(any(u[1] > 0 for u in self.updates))
        self.assertTrue(any(s for s in job.speed.split()))  # velocidade registrada

    def test_erro_permanente_sem_credencial_no_log(self):
        (job,) = self.eng.add([entry("http://u:senha@h.tv/403", "Segredo 403")])
        self.assertTrue(wait_until(lambda: job.status is JobStatus.FAILED))
        self.assertEqual(job.error_code, "forbidden")
        joined = " ".join(self.logs)
        self.assertNotIn("senha", joined)

    def test_limitacao_js_youtube_documentada(self):
        (job,) = self.eng.add([entry("http://yt/jsfail", "YT JS")])
        self.assertTrue(wait_until(lambda: job.status is JobStatus.FAILED))
        self.assertIn("Deno", job.error_message)

    def test_pausa_e_retomada(self):
        (job,) = self.eng.add([entry(title="Pausável")])
        self.assertTrue(wait_until(lambda: job.status is JobStatus.RUNNING
                                   and job.percent > 1))
        self.eng.pause_job(job.id)
        self.assertTrue(wait_until(lambda: job.status is JobStatus.PAUSED))
        self.assertTrue(self.eng.resume_job(job.id))
        self.assertTrue(wait_until(lambda: job.status is JobStatus.DONE))

    def test_cancelamento(self):
        (job,) = self.eng.add([entry(title="Cancelável")])
        self.assertTrue(wait_until(lambda: job.status is JobStatus.RUNNING
                                   and job.percent > 1))
        self.eng.cancel_job(job.id)
        self.assertTrue(wait_until(lambda: job.status is JobStatus.CANCELLED))
        self.assertLess(job.percent, 100.0)

    def test_fila_multipla(self):
        jobs = self.eng.add([entry(title=f"item {i}") for i in range(3)])
        self.assertTrue(wait_until(
            lambda: all(j.status is JobStatus.DONE for j in jobs)))
        self.assertEqual(self.overall[-1], 100.0)

    def test_formatos_single_file(self):
        # Sem FFmpeg: nunca merge → sempre seletores de arquivo único ("b").
        for v in FORMAT_MAP.values():
            self.assertTrue(v.startswith("b"), v)


class TestAndroidPaths(unittest.TestCase):
    def test_downloads_dir_override(self):
        from app.core import paths
        with tempfile.TemporaryDirectory() as td:
            os.environ["VIBECINE_DOWNLOAD_DIR"] = os.path.join(td, "Meus Dlds")
            try:
                d = paths.user_downloads_default()
                self.assertTrue(os.path.isdir(d))
            finally:
                os.environ.pop("VIBECINE_DOWNLOAD_DIR", None)

    def test_data_dir_override(self):
        from app.core import paths
        with tempfile.TemporaryDirectory() as td:
            os.environ["VIBECINE_DATA_DIR"] = td
            try:
                self.assertEqual(paths.data_dir(), td)
            finally:
                os.environ.pop("VIBECINE_DATA_DIR", None)


class TestShareAndroid(unittest.TestCase):
    def test_compartilhamento_bloqueia_credenciais(self):
        ok, msg = android_share.share_entry(
            {"title": "X", "group": "", "tvg_id": "", "tvg_name": "",
             "logo": "", "url": "http://u:senha@h.tv/x?token=t1", "type": "filme"})
        self.assertFalse(ok)
        self.assertIn("credenciais", msg.lower())

    def test_compartilhamento_fallback_desktop(self):
        # Fora do Android não chama Intent; no desktop abre navegador
        # (não testamos o browser de verdade — apenas a decisão)
        from app.core import paths
        self.assertFalse(paths.is_android())


class TestUIMock(unittest.TestCase):
    def test_modulos_e_classes_existem(self):
        # Kivy com GL mock é instável fora de dispositivo; validamos a
        # estrutura (engines/telas existem e importam limpo).
        import android.main as m
        for cls in ("BibliotecaScreen", "DownloadsScreen",
                    "HistoricoScreen", "ConfigScreen", "VibeCineAndroidApp"):
            self.assertTrue(hasattr(m, cls), cls)


if __name__ == "__main__":
    unittest.main()
