"""Cache de extracao retomavel (PRD 5.5, 6.3, 6.4).

Grava o texto bruto por arquivo, chaveado por hash do conteudo + parametros de
extracao. E o que permite refazer o indice (e mudar de esquema/normalizacao)
sem repetir o OCR, a etapa mais cara.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

HASH_BLOCO = 1024 * 1024

CACHE_NAMES = ("build", "cache")


@dataclass
class ResultadoExtracao:
    paginas: list[dict] = field(default_factory=list)
    n_ocr: int = 0
    n_sem_texto: int = 0

    @property
    def n_paginas(self) -> int:
        return len(self.paginas)


def hash_arquivo(caminho: Path) -> str:
    h = hashlib.sha1()
    with caminho.open("rb") as fh:
        while True:
            bloco = fh.read(HASH_BLOCO)
            if not bloco:
                break
            h.update(bloco)
    return h.hexdigest()


def chave_cache(arquivo_hash: str, parametros: str) -> str:
    return hashlib.sha1(f"{arquivo_hash}|{parametros}".encode("utf-8")).hexdigest()


SCHEMA_CACHE = """
CREATE TABLE IF NOT EXISTS extracao (
  chave TEXT PRIMARY KEY,
  arquivo TEXT NOT NULL,
  arquivo_hash TEXT NOT NULL,
  parametros TEXT NOT NULL,
  n_paginas INTEGER NOT NULL,
  n_ocr INTEGER NOT NULL,
  n_sem_texto INTEGER NOT NULL,
  dados TEXT NOT NULL,
  criado_em TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_cache_arquivo ON extracao(arquivo_hash);
"""


class CacheExtracao:
    """Cache SQLite de extracao. Seguro para uso concorrente (lock interno)."""

    def __init__(self, caminho: Path) -> None:
        self.caminho = Path(caminho)
        self.caminho.parent.mkdir(parents=True, exist_ok=True)
        self._con = sqlite3.connect(str(self.caminho), check_same_thread=False)
        self._con.row_factory = sqlite3.Row
        self._lock = threading.Lock()
        with self._lock:
            self._con.executescript(SCHEMA_CACHE)
            self._con.execute("PRAGMA journal_mode=WAL")
            self._con.commit()

    @classmethod
    def criar(cls, diretorio: Path) -> "CacheExtracao":
        return cls(Path(diretorio) / "extracao.db")

    def tem(self, chave: str) -> bool:
        with self._lock:
            row = self._con.execute(
                "SELECT 1 FROM extracao WHERE chave=?", (chave,)
            ).fetchone()
        return row is not None

    def obter(self, chave: str) -> ResultadoExtracao | None:
        with self._lock:
            row = self._con.execute(
                "SELECT * FROM extracao WHERE chave=?", (chave,)
            ).fetchone()
        if row is None:
            return None
        paginas = json.loads(row["dados"])
        return ResultadoExtracao(
            paginas=paginas,
            n_ocr=row["n_ocr"],
            n_sem_texto=row["n_sem_texto"],
        )

    def gravar(
        self,
        chave: str,
        arquivo: str,
        arquivo_hash: str,
        parametros: str,
        resultado: ResultadoExtracao,
    ) -> None:
        dados = json.dumps(resultado.paginas, ensure_ascii=False)
        criado = datetime.now(timezone.utc).isoformat(timespec="seconds")
        with self._lock:
            self._con.execute(
                "INSERT OR REPLACE INTO extracao "
                "(chave, arquivo, arquivo_hash, parametros, n_paginas, n_ocr, "
                " n_sem_texto, dados, criado_em) VALUES (?,?,?,?,?,?,?,?,?)",
                (
                    chave,
                    arquivo,
                    arquivo_hash,
                    parametros,
                    resultado.n_paginas,
                    resultado.n_ocr,
                    resultado.n_sem_texto,
                    dados,
                    criado,
                ),
            )
            self._con.commit()

    def remover(self, chave: str) -> None:
        with self._lock:
            self._con.execute("DELETE FROM extracao WHERE chave=?", (chave,))
            self._con.commit()

    def contar(self) -> int:
        with self._lock:
            return int(self._con.execute("SELECT COUNT(*) FROM extracao").fetchone()[0])

    def total_paginas(self) -> int:
        with self._lock:
            row = self._con.execute(
                "SELECT COALESCE(SUM(n_paginas),0), COALESCE(SUM(n_ocr),0), "
                "COALESCE(SUM(n_sem_texto),0) FROM extracao"
            ).fetchone()
        return int(row[0]), int(row[1]), int(row[2])

    def fechar(self) -> None:
        with self._lock:
            self._con.close()
