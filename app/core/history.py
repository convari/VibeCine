# -*- coding: utf-8 -*-
"""Histórico de downloads em SQLite.

Registra todo download finalizado pela fila (concluído, erro ou cancelado),
com data, título, grupo, URL (mascarada), status, pasta e caminho do arquivo.
Sem dependências externas: usa o sqlite3 da biblioteca padrão.

Nota: `with sqlite3.connect()` faz commit/rollback mas NÃO fecha a
conexão — por isso cada operação abre e fecha explicitamente (Windows
mantém lock de arquivo aberto).
"""

from __future__ import annotations

import os
import sqlite3
from datetime import datetime

from . import paths
from .downloader import redact_url

DB_PATH = os.path.join(
    paths.data_dir() if paths.is_frozen()
    else os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                      "..", "data")),
    "history.db")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    grp TEXT,
    url TEXT,
    status TEXT NOT NULL,
    out_dir TEXT,
    output_path TEXT,
    size_bytes INTEGER,
    error TEXT,
    finished_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_history_status ON history(status);
CREATE INDEX IF NOT EXISTS idx_history_date ON history(finished_at);
"""


class HistoryStore:
    """Acesso thread-safe simples (uma conexão curta por operação)."""

    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path
        parent = os.path.dirname(self.db_path)
        if parent:
            os.makedirs(parent, exist_ok=True)
        con = self._connect()
        try:
            con.executescript(_SCHEMA)
            con.commit()
        finally:
            con.close()

    def _connect(self) -> sqlite3.Connection:
        con = sqlite3.connect(self.db_path)
        con.row_factory = sqlite3.Row
        return con

    def add(self, *, title: str, group: str, url: str, status: str,
            out_dir: str, output_path: str = "", size_bytes: int = 0,
            error: str = "") -> int:
        con = self._connect()
        try:
            cur = con.execute(
                "INSERT INTO history (title, grp, url, status, out_dir,"
                " output_path, size_bytes, error, finished_at)"
                " VALUES (?,?,?,?,?,?,?,?,?)",
                (title, group, redact_url(url), status, out_dir,
                 output_path, int(size_bytes or 0), error,
                 datetime.now().isoformat(timespec="seconds")))
            con.commit()
            return int(cur.lastrowid)
        finally:
            con.close()

    def list(self, status: str | None = None, limit: int = 500) -> list[dict]:
        sql = "SELECT * FROM history"
        params: tuple = ()
        if status:
            sql += " WHERE status = ?"
            params = (status,)
        sql += " ORDER BY id DESC LIMIT ?"
        params += (int(limit),)
        con = self._connect()
        try:
            return [dict(r) for r in con.execute(sql, params).fetchall()]
        finally:
            con.close()

    def clear(self) -> int:
        con = self._connect()
        try:
            cur = con.execute("DELETE FROM history")
            con.commit()
            return cur.rowcount
        finally:
            con.close()

    def delete(self, record_id: int) -> bool:
        """Remove um registro específico. Retorna True se removeu."""
        con = self._connect()
        try:
            cur = con.execute("DELETE FROM history WHERE id = ?",
                              (int(record_id),))
            con.commit()
            return cur.rowcount > 0
        finally:
            con.close()

    def count_by_status(self) -> dict:
        con = self._connect()
        try:
            rows = con.execute(
                "SELECT status, COUNT(*) c FROM history GROUP BY status"
            ).fetchall()
        finally:
            con.close()
        return {r["status"]: r["c"] for r in rows}
