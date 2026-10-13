"""Esquema do banco (definitivo para o MVP) e versionamento (PRD 5.6).

Modulo compartilhado (leitura) entre a aplicacao de consulta e o script de
indexacao. O runtime importa apenas *este* modulo e o de normalizacao; o
indexador e que importa os dois (PRD 6.9).
"""

from __future__ import annotations

import sqlite3

VERSAO_ESQUEMA = 1

TOKENIZER = "unicode61 remove_diacritics 2"
PREFIXOS = "2 3 4"

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS meta (
  chave TEXT PRIMARY KEY,
  valor TEXT
);

CREATE TABLE IF NOT EXISTS documentos (
  id INTEGER PRIMARY KEY,
  arquivo TEXT NOT NULL,
  titulo TEXT,
  n_paginas INTEGER
);

CREATE TABLE IF NOT EXISTS paginas (
  id INTEGER PRIMARY KEY,
  doc_id INTEGER NOT NULL REFERENCES documentos(id),
  pagina INTEGER NOT NULL,
  texto TEXT,
  texto_busca TEXT
);
CREATE INDEX IF NOT EXISTS ix_pag_doc ON paginas(doc_id);

CREATE VIRTUAL TABLE IF NOT EXISTS busca USING fts5(
  texto_busca,
  content='paginas', content_rowid='id',
  tokenize='unicode61 remove_diacritics 2',
  prefix='2 3 4'
);
"""

# Indice unico sobre o caminho relativo: identificador estavel do acervo.
INDICE_ARQUIVO_SQL = "CREATE UNIQUE INDEX IF NOT EXISTS ix_doc_arquivo ON documentos(arquivo);"

META_MODE_NORMALIZACAO = "modo_normalizacao"


def abrir(  # noqa: A001 - nome curto e conveniente
    caminho: str,
    somente_leitura: bool = False,
    imutavel: bool = False,
) -> sqlite3.Connection:
    """Abre o banco.

    Em producao a aplicacao usa ``somente_leitura=True, imutavel=True``
    (``file:...?mode=ro&immutable=1``). O indexador abre para escrita.
    """
    if somente_leitura:
        uri = f"file:{caminho}?mode=ro"
        if imutavel:
            uri += "&immutable=1"
        con = sqlite3.connect(uri, uri=True)
    else:
        con = sqlite3.connect(caminho)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys=ON")
    return con


def criar(con: sqlite3.Connection, modo_normalizacao: str | None = None) -> None:
    """Cria o esquema e registra a versao. Idempotente."""
    con.executescript(SCHEMA_SQL)
    con.execute(INDICE_ARQUIVO_SQL)
    gravar_meta(con, "versao_esquema", str(VERSAO_ESQUEMA))
    if modo_normalizacao:
        gravar_meta(con, META_MODE_NORMALIZACAO, modo_normalizacao)
    con.commit()


def gravar_meta(con: sqlite3.Connection, chave: str, valor: str) -> None:
    con.execute(
        "INSERT INTO meta(chave, valor) VALUES(?, ?) "
        "ON CONFLICT(chave) DO UPDATE SET valor=excluded.valor",
        (chave, str(valor)),
    )


def ler_meta(con: sqlite3.Connection, chave: str, default: str | None = None) -> str | None:
    try:
        row = con.execute("SELECT valor FROM meta WHERE chave=?", (chave,)).fetchone()
    except sqlite3.OperationalError:
        return default
    return row["valor"] if row else default


def versao_esquema(con: sqlite3.Connection) -> int | None:
    valor = ler_meta(con, "versao_esquema")
    try:
        return int(valor) if valor is not None else None
    except (TypeError, ValueError):
        return None


def modo_normalizacao(con: sqlite3.Connection) -> str | None:
    return ler_meta(con, META_MODE_NORMALIZACAO)


def compatibilidade_ok(con: sqlite3.Connection) -> bool:
    return versao_esquema(con) == VERSAO_ESQUEMA


def rebuild_fts(con: sqlite3.Connection) -> None:
    con.execute("INSERT INTO busca(busca) VALUES('rebuild')")


def optimize_fts(con: sqlite3.Connection) -> None:
    con.execute("INSERT INTO busca(busca) VALUES('optimize')")


def pragmas_desempenho(con: sqlite3.Connection) -> None:
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("PRAGMA synchronous=NORMAL")


def verificar_integridade(con: sqlite3.Connection) -> str:
    row = con.execute("PRAGMA integrity_check").fetchone()
    return row[0] if row else "desconhecido"
