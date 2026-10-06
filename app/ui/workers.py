# -*- coding: utf-8 -*-
"""Threads de trabalho da interface (Qt Signals/Slots).

A UI nunca executa operações de rede/processos na thread principal:
- ExtractWorker: roda app.core.extractor.extract_entries em QThread e emite
  sinais de log, progresso, sucesso (lista de entradas) e erro amigável.
- CoverFetcher: baixa a imagem de capa sem travar a interface.
"""

from __future__ import annotations

import queue
import threading
import urllib.request

from PySide6.QtCore import QThread, Signal

from app.core.extractor import ExtractorError, extract_entries


class ExtractWorker(QThread):
    log = Signal(str)
    done = Signal(list)
    failed = Signal(str, str)  # (mensagem amigável, detalhe técnico)

    def __init__(self, url: str, cfg: dict, parent=None):
        super().__init__(parent)
        self._url = url
        self._cfg = cfg
        self._cancel = threading.Event()

    def cancel(self):
        self._cancel.set()

    def run(self):
        try:
            entries = extract_entries(
                self._url, self._cfg,
                log=self.log.emit, cancel=self._cancel)
            if self._cancel.is_set():
                self.failed.emit("Carregamento cancelado.", "cancelled")
                return
            self.done.emit(entries)
        except ExtractorError as exc:
            self.failed.emit(exc.friendly, exc.technical or exc.code)
        except Exception as exc:  # última linha de defesa da UI
            self.failed.emit(f"Erro inesperado ao carregar: {exc}", repr(exc))


class PlaylistBatchWorker(QThread):
    """Carrega playlists M3U (arquivo/remota) em LOTES, do thread de fundo.

    A UI recebe `batch(list[dict])` ~a cada 200 itens: o modelo insere em
    bloco (beginInsertRows) e a interface permanece responsiva durante o
    parse de listas enormes.
    """
    batch = Signal(list)
    finishedEmpty = Signal()
    done = Signal(int)          # total de entradas
    failed = Signal(str, str)   # (mensagem amigável, detalhe técnico)

    def __init__(self, url: str, cfg: dict, batch_size: int = 200, parent=None):
        super().__init__(parent)
        self._url = url
        self._cfg = cfg
        self._batch_size = max(10, int(batch_size))
        self._cancel = threading.Event()

    def cancel(self):
        self._cancel.set()

    def run(self):
        from app.core import url_router
        from app.core.extractor import ExtractorError, read_playlist_source
        from app.core.m3u_parser import iter_m3u_batches

        routed = url_router.classify_url(self._url)
        if routed.kind is url_router.UrlKind.INVALID:
            self.failed.emit(routed.message or "URL inválida.", "invalid_url")
            return
        try:
            content = read_playlist_source(routed, log=lambda m: None)
        except ExtractorError as exc:
            self.failed.emit(exc.friendly, exc.technical or exc.code)
            return
        except Exception as exc:
            self.failed.emit(str(exc), repr(exc))
            return

        total = 0
        for batch in iter_m3u_batches(content, self._batch_size):
            if self._cancel.is_set():
                self.failed.emit("Carregamento cancelado.", "cancelled")
                return
            self.batch.emit(batch)
            total += len(batch)
            # cede ao event loop
            self.msleep(1)
        if total == 0 and "#EXT-X-" in content:
            # manifest HLS puro: tratado como stream único (ExtractWorker cuida)
            self.finishedEmpty.emit()
            return
        self.done.emit(total)


class CoverPool(QThread):
    """Pool de capas: fila limitada + concorrência pequena (lazy loading).

    - só processa o que é enfileirado (itens visíveis/de detalhe);
    - cada worker busca bytes e retorna QImage (thread-safe) — a conversão
      para QPixmap acontece na thread da UI;
    - a página mantém o cache (LRU) e descarta itens distantes da viewport.
    """
    ready = Signal(str, object)   # (url, QImage)

    def __init__(self, parent=None, workers: int = 3):
        super().__init__(parent)
        self._queue: queue.Queue[tuple] = queue.Queue()
        self._pending: set[str] = set()
        self._stop = False
        self._workers = max(1, int(workers))

    def request(self, url: str):
        if url and url not in self._pending:
            self._pending.add(url)
            self._queue.put(url)

    def run(self):
        threads = [threading.Thread(target=self._worker, daemon=True)
                   for _ in range(self._workers)]
        for t in threads:
            t.start()
        while not self._stop:
            self.msleep(50)  # loop leve até cancelar
        for _ in threads:
            self._queue.put(None)
        for t in threads:
            t.join(timeout=1)

    def _worker(self):
        while not self._stop:
            url = self._queue.get()
            if url is None:
                break
            self._pending.discard(url)
            try:
                req = urllib.request.Request(
                    url, headers={"User-Agent": "VibeCine/2.0"})
                with urllib.request.urlopen(req, timeout=10) as resp:
                    data = resp.read()
                from PySide6.QtGui import QImage
                from PySide6.QtCore import QByteArray
                img = QImage.fromData(QByteArray(data))
                if not img.isNull():
                    self.ready.emit(url, img)
            except Exception:
                pass  # capa é opcional

    def stop(self):
        self._stop = True


class CoverFetcher(QThread):
    loaded = Signal(bytes)  # bytes da imagem (QPixmap decide na thread da UI)

    def __init__(self, url: str, parent=None):
        super().__init__(parent)
        self._url = url

    def run(self):
        try:
            req = urllib.request.Request(
                self._url, headers={"User-Agent": "VibeCine/2.0"})
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = resp.read()
            if data:
                self.loaded.emit(data)
        except Exception:
            pass  # capa é opcional; falha silenciosa mantém o placeholder
