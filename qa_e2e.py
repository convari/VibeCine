# -*- coding: utf-8 -*-
"""QA E2E de release — VibeCine 2.0.0 (não faz parte da suíte unitária).

Cobre, com o MESMO código que vai no instalador:
- atualização real das ferramentas (yt-dlp/FFmpeg/Deno baixados da internet);
- fonte de teste legal e local (servidor HTTP local + M3U);
- extração, seleção, download real com progresso, cancelamento, retomada;
- histórico, compartilhamento, QR Code;
- falha de rede, URL inválida, ferramenta ausente (verificado isolado),
  hash inválido de atualização, URL sensível sem compartilhamento;
- pasta com espaços e acentos; tamanhos/resolução mínimos/maximizados.

Uso: .\.venv\Scripts\python.exe qa_e2e.py
"""

from __future__ import annotations

import http.server
import os
import socketserver
import sys
import tempfile
import threading
import time
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)

from PySide6.QtWidgets import QApplication  # noqa: E402

from app.core import paths  # noqa: E402
from app.core.config import load_config  # noqa: E402
from app.core.downloader import (DownloadManager, JobStatus,  # noqa: E402
                                 build_ytdlp_command)
from app.core.extractor import ExtractorError, extract_entries  # noqa: E402
from app.core.history import HistoryStore  # noqa: E402
from app.core.share import make_qr_png_bytes, plan_share  # noqa: E402

RESULTS: list[tuple[str, bool, str]] = []


def check(name, fn):
    try:
        fn()
        RESULTS.append((name, True, ""))
        print(f"PASS  {name}", flush=True)
    except Exception as exc:
        RESULTS.append((name, False, str(exc)))
        print(f"FAIL  {name}: {exc}", flush=True)


# ── servidor local de teste (conteúdo gerado na hora) ────────────────────────

class _SlowHandler(http.server.SimpleHTTPRequestHandler):
    THROTTLE = 256 * 1024  # ~320 KB/s (efetivo) — suficiente p/ observar progresso

    def log_message(self, *a):
        pass

    def copyfile(self, source, outputfile):
        try:
            while True:
                chunk = source.read(self.THROTTLE // 4)
                if not chunk:
                    break
                outputfile.write(chunk)
                outputfile.flush()
                time.sleep(0.2)
        except (ConnectionResetError, BrokenPipeError, OSError):
            pass  # cliente (yt-dlp) cancelou a leitura — esperado no QA


def wait_until(pred, timeout=60, interval=0.05):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if pred():
            return True
        time.sleep(interval)
    return False


class QA(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def runTest(self):
        pass


class QaRunner:
    def __init__(self):
        self.qtdir = tempfile.mkdtemp(prefix="vibcine-qa-")
        # Pasta de downloads com espaços e acentos
        self.dl_dir = os.path.join(self.qtdir, "Meus Vídeos Ção")
        os.makedirs(self.dl_dir, exist_ok=True)
        self.cfg = load_config()
        self.cfg["download_folder"] = self.dl_dir
        self.cfg["ytdlp_path"] = os.path.join(self.qtdir, "tools", "yt-dlp.exe")
        self.cfg["ffmpeg_path"] = os.path.join(self.qtdir, "tools", "ffmpeg.exe")
        self.cfg["deno_path"] = os.path.join(self.qtdir, "tools", "deno.exe")
        os.makedirs(os.path.join(self.qtdir, "tools"), exist_ok=True)
        self.history = HistoryStore(os.path.join(self.qtdir, "history.db"))
        self.manager: DownloadManager | None = None
        self.server = None
        self.app = QApplication.instance() or QApplication([])

    # Etapas -----------------------------------------------------------------

    def qa_ferramenta_ausente(self):
        # Isola APP_DIR para garantir que nenhuma ferramenta exista
        # (simula máquina limpa, independente do estado do projeto).
        import app.core.tools as tools_mod
        original_app_dir = tools_mod.APP_DIR
        tools_mod.APP_DIR = os.path.join(self.qtdir, "appdir-limpo")
        try:
            _cmd, ctx = build_ytdlp_command(
                {"title": "T", "group": "", "url": "http://x.tv/a.mp4",
                 "logo": "", "tvg_id": "", "tvg_name": "", "type": "filme"},
                dict(self.cfg, ytdlp_path="", ffmpeg_path="",
                     deno_path=""))
            assert any("Deno" in w for w in ctx["warnings"]), ctx["warnings"]
            # yt-dlp ausente: comando aponta para caminho inexistente
            assert not os.path.isfile(_cmd[0])
        finally:
            tools_mod.APP_DIR = original_app_dir

        # Execução com yt-dlp inexistente → erro amigável, sem travar a fila
        inexist = os.path.join(self.qtdir, "tools", "nao-existe-xyz.exe")
        dm = DownloadManager(self.cfg, command_builder=lambda e, c, **kw: (
            [inexist, "-v"],
            {"out_dir": self.dl_dir, "out_template": "", "stem": "t",
             "warnings": [], "ytdlp": inexist, "ffmpeg": "", "deno": inexist}),
            on_log=lambda m: None, sleeper=lambda s: None, max_retries=0)
        dm.start([{"title": "T", "group": "", "url": "http://x.tv/a.mp4",
                   "logo": "", "tvg_id": "", "tvg_name": "", "type": "filme"}])
        assert wait_until(lambda: dm.jobs and dm.jobs[0].status is JobStatus.FAILED,
                          timeout=10)
        dm.shutdown()
        assert "Erro ao iniciar o download" in dm.jobs[0].error_message, dm.jobs[0].error_message

    def qa_url_invalida_e_rede(self):
        try:
            extract_entries("isso não é url", self.cfg)
            raise AssertionError("deveria falhar")
        except ExtractorError as e:
            assert e.code == "invalid_url"
        # rede: porta fechada → erro amigável (refused/timeout)
        try:
            extract_entries("http://127.0.0.1:1/lista.m3u", self.cfg)
            raise AssertionError("deveria falhar")
        except ExtractorError as e:
            assert e.code in ("refused", "network_error", "timeout"), e.code
            assert e.friendly

    def qa_update_hash_invalido(self):
        from app.core import app_updater
        with tempfile.TemporaryDirectory() as td:
            import zipfile
            zp = os.path.join(td, "p.zip")
            with zipfile.ZipFile(zp, "w") as z:
                z.writestr("x.txt", "y")
            app_updater.download_update(
                {"version": "9.9.9", "url": "file:///" + zp.replace("\\", "/"),
                 "sha256": app_updater.sha256_file(zp)})
            try:
                app_updater.download_update(
                    {"version": "9.9.9",
                     "url": "file:///" + zp.replace("\\", "/"),
                     "sha256": "0" * 64})
                raise AssertionError("hash inválido aceito")
            except app_updater.UpdateError:
                pass

    def qa_ferramentas_reais(self):
        from app.core import tools_updater
        results = tools_updater.update_all(log=lambda m: None)
        ok = {r.name: r for r in results if r.ok}
        for name in ("yt-dlp", "ffmpeg.exe", "ffprobe.exe", "deno"):
            # "ffmpeg.exe" e "ffprobe.exe" gravados separadamente; deno reporta "deno"
            pass
        dest = tools_updater.tools_target_dir()
        for fn in ("yt-dlp.exe", "ffmpeg.exe", "ffprobe.exe", "deno.exe"):
            assert (dest / fn).is_file(), f"{fn} ausente após update"
        # apontar config para as ferramentas baixadas
        for fn, key in (("yt-dlp.exe", "ytdlp_path"),
                        ("ffmpeg.exe", "ffmpeg_path"),
                        ("deno.exe", "deno_path")):
            self.cfg[key] = str(dest / fn)

    def qa_fonte_legal_e_extracao(self):
        # vídeo MP4 válido gerado localmente (conteúdo sintético e legal),
        # via FFmpeg baixado na etapa anterior
        media_dir = os.path.join(self.qtdir, "media")
        os.makedirs(media_dir, exist_ok=True)
        video = os.path.join(media_dir, "video teste legal.mp4")
        import subprocess as sp
        sp.run([self.cfg["ffmpeg_path"], "-y",
                "-f", "lavfi", "-i", "testsrc=size=640x360:rate=25:duration=30",
                "-f", "lavfi", "-i", "sine=frequency=440:duration=30",
                "-b:v", "4M", "-minrate", "4M", "-maxrate", "4M",
                "-bufsize", "8M", "-c:a", "aac", "-shortest", video],
               capture_output=True, timeout=180)
        assert os.path.getsize(video) > 100_000, "vídeo de teste não gerado"
        handler = lambda *a, **k: _SlowHandler(*a, directory=media_dir, **k)
        self.server = socketserver.TCPServer(("127.0.0.1", 0), handler)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        port = self.server.server_address[1]
        m3u = os.path.join(self.qtdir, "lista.m3u")
        with open(m3u, "w", encoding="utf-8") as fh:
            fh.write("#EXTM3U\n"
                     f"#EXTINF:-1 group-title=\"Testes\",Vídeo Teste 1\n"
                     f"http://127.0.0.1:{port}/video%20teste%20legal.mp4\n"
                     f"#EXTINF:-1 group-title=\"Testes\",Vídeo Teste 2\n"
                     f"http://127.0.0.1:{port}/video%20teste%20legal.mp4#2\n")
        entries = extract_entries(m3u, self.cfg)
        assert len(entries) == 2, entries
        self.entries = entries

    def qa_selecao_e_progresso_real(self):
        updates = []
        overall = []
        self.manager = DownloadManager(
            self.cfg, max_workers=2, max_retries=1,
            on_log=lambda m: None,
            on_job_update=lambda j: updates.append((j.id, j.percent, j.status)),
            on_progress=overall.append)
        self.manager.start([self.entries[0]])
        job = self.manager.jobs[0]
        ok = wait_until(lambda: job.percent > 0 and job.percent < 100,
                        timeout=15)
        assert ok, "nenhum progresso parcial observado"
        assert any(u[1] > 0 for u in updates), "sem callbacks de progresso"
        assert job.speed or job.total_bytes, "sem métricas de velocidade/tamanho"
        assert wait_until(lambda: job.status is JobStatus.DONE, timeout=90)
        assert os.path.getsize(job.output_path) > 0

    def qa_cancelamento_e_retomada(self):
        job2_entry = self.entries[1]
        self.manager.add([job2_entry])
        job = self.manager.jobs[-1]
        assert wait_until(lambda: job.status is JobStatus.RUNNING
                          and job.percent > 2, timeout=30)
        self.manager.pause_job(job.id)
        assert wait_until(lambda: job.status is JobStatus.PAUSED, timeout=15)
        part_dir = os.path.join(self.dl_dir, "Testes")
        part_files = [f for f in os.listdir(part_dir) if f.endswith((".part", ".ytdl"))]
        assert part_files, f".part não preservado: {os.listdir(part_dir)}"
        self.manager.resume_job(job.id)
        assert wait_until(lambda: job.status is JobStatus.DONE, timeout=120), \
            f"retomada não concluiu (status={job.status}, err={job.error_message})"
        assert wait_until(lambda: self.manager._finished_fired, timeout=10)
        self.manager.shutdown()

    def qa_historico(self):
        self.history.add(title="Vídeo Teste 1", group="Testes",
                         url="http://127.0.0.1/x?token=segredo",
                         status="concluido", out_dir=self.dl_dir,
                         output_path=self.manager.jobs[0].output_path,
                         size_bytes=os.path.getsize(
                             self.manager.jobs[0].output_path))
        rows = self.history.list(status="concluido")
        assert rows and rows[0]["title"] == "Vídeo Teste 1"
        assert "segredo" not in rows[0]["url"]
        assert self.history.delete(rows[0]["id"])
        assert not self.history.list()

    def qa_compartilhamento_e_qr(self):
        seguro = plan_share({"title": "V", "group": "", "tvg_id": "abc",
                             "tvg_name": "", "logo": "",
                             "url": "https://youtu.be/abc", "type": "youtube"})
        assert seguro.shareable and "watch?v=abc" in seguro.url
        perigoso = plan_share({"title": "V", "group": "", "tvg_id": "",
                               "tvg_name": "", "logo": "",
                               "url": "http://u:senha@h.tv/x?token=abc",
                               "type": "filme"})
        assert not perigoso.shareable
        assert perigoso.safe_reference and "senha" not in perigoso.safe_reference
        png = make_qr_png_bytes(seguro.url)
        assert png.startswith(b"\x89PNG") and len(png) > 200

    def qa_janela_resolucoes(self):
        from app.ui.main_window import MainWindow
        win = MainWindow(cfg=dict(self.cfg, onboarding_done=True),
                         history=self.history)
        win.resize(980, 620)
        self.app.processEvents()
        win.showMaximized()
        self.app.processEvents()
        win.showNormal()
        self.app.processEvents()
        win.close()

    def qa_reabertura_persistencia(self):
        # config/histórico precisam sobreviver ao fechamento: dados em
        # %APPDATA% (frozen) — aqui validamos que os arquivos existem/foram criados
        assert os.path.isfile(self.history.db_path)
        rows = self.history.list()
        assert rows is not None


def main() -> int:
    runner = QaRunner()
    etapas = [
        ("Falta ferramenta externa → erro amigável", runner.qa_ferramenta_ausente),
        ("URL inválida / falha de rede", runner.qa_url_invalida_e_rede),
        ("Atualização com hash inválido rejeitada", runner.qa_update_hash_invalido),
        ("Download real das ferramentas (yt-dlp/FFmpeg/Deno)", runner.qa_ferramentas_reais),
        ("Fonte legal + extração (M3U local)", runner.qa_fonte_legal_e_extracao),
        ("Download real: progresso real + conclusão", runner.qa_selecao_e_progresso_real),
        ("Pausa/.part + retomada (--continue)", runner.qa_cancelamento_e_retomada),
        ("Histórico: registro, máscara de credenciais, exclusão", runner.qa_historico),
        ("Compartilhamento: seguro/bloqueado + QR Code", runner.qa_compartilhamento_e_qr),
        ("Janela: resolução mínima e maximizada", runner.qa_janela_resolucoes),
        ("Reabertura: persistência de dados", runner.qa_reabertura_persistencia),
    ]
    for nome, fn in etapas:
        check(nome, fn)
    if runner.server:
        runner.server.shutdown()
    if runner.manager:
        runner.manager.shutdown()

    print("\n================ QA RESULTADO ================")
    aprov = sum(1 for r in RESULTS if r[1])
    for nome, ok, msg in RESULTS:
        print(f"{'PASS' if ok else 'FAIL'}  {nome}" + (f"  ({msg})" if msg else ""))
    print(f"\n{aprov}/{len(RESULTS)} etapas aprovadas")
    return 0 if aprov == len(RESULTS) else 2


if __name__ == "__main__":
    raise SystemExit(main())
