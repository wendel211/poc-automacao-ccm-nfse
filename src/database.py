"""Cache SQLite para CCM por município+CNPJ e log de execuções."""
from __future__ import annotations
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Optional

_DDL = """
CREATE TABLE IF NOT EXISTS ccm_cache (
    municipio   TEXT NOT NULL,
    cnpj        TEXT NOT NULL,
    ccm         TEXT,
    status      TEXT NOT NULL,
    updated_at  TEXT NOT NULL,
    PRIMARY KEY (municipio, cnpj)
);

CREATE TABLE IF NOT EXISTS execucoes (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    id_documento    TEXT NOT NULL,
    municipio       TEXT NOT NULL,
    cnpj            TEXT NOT NULL,
    status          TEXT NOT NULL,
    mensagem        TEXT,
    arquivo_cadastro TEXT,
    arquivo_nota_pdf TEXT,
    arquivo_nota_xml TEXT,
    estrategia      TEXT,
    executado_em    TEXT NOT NULL
);
"""


class Database:
    def __init__(self, path: Path = Path("output/poc.db")) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self._path = path
        with self._conn() as conn:
            conn.executescript(_DDL)

    @contextmanager
    def _conn(self):
        conn = sqlite3.connect(self._path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def get_ccm(self, municipio: str, cnpj: str) -> Optional[str]:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT ccm FROM ccm_cache WHERE municipio=? AND cnpj=? AND status='SUCESSO'",
                (municipio, cnpj),
            ).fetchone()
        return row["ccm"] if row else None

    def set_ccm(self, municipio: str, cnpj: str, ccm: Optional[str], status: str) -> None:
        with self._conn() as conn:
            conn.execute(
                """INSERT INTO ccm_cache (municipio, cnpj, ccm, status, updated_at)
                   VALUES (?, ?, ?, ?, ?)
                   ON CONFLICT(municipio, cnpj) DO UPDATE SET
                       ccm=excluded.ccm, status=excluded.status, updated_at=excluded.updated_at""",
                (municipio, cnpj, ccm, status, datetime.now().isoformat()),
            )

    def log_execucao(self, **kwargs) -> None:
        kwargs.setdefault("executado_em", datetime.now().isoformat())
        cols = ", ".join(kwargs)
        placeholders = ", ".join("?" * len(kwargs))
        with self._conn() as conn:
            conn.execute(
                f"INSERT INTO execucoes ({cols}) VALUES ({placeholders})",
                list(kwargs.values()),
            )
