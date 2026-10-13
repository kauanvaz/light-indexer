"""Carga das tabelas e construcao do FTS5 (PRD 5.5 etapas 5-6, 6.3 etapas 5-6).

Normaliza o texto para a coluna pesquisavel, insere documentos/paginas e
executa ``rebuild``, ``optimize``, ``ANALYZE`` e ``VACUUM``.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from .. import schema
from ..search.normalize import Normalizador, remover_cabecalho_rodape
from .cache import ResultadoExtracao
from .inventory import ArquivoAcervo
from .metadata import titulo_do_arquivo


@dataclass
class EstatisticasCarga:
    documentos: int = 0
    paginas: int = 0
    paginas_ocr: int = 0
    paginas_sem_texto: int = 0


def carregar(
    conn: sqlite3.Connection,
    entradas: list[tuple[ArquivoAcervo, ResultadoExtracao]],
    normalizador: Normalizador,
    titulos: dict[str, str] | None = None,
) -> EstatisticasCarga:
    titulos = titulos or {}
    stats = EstatisticasCarga()
    conn.execute("BEGIN")
    for arquivo, resultado in entradas:
        titulo = titulos.get(arquivo.identificador) or titulo_do_arquivo(arquivo.caminho)
        cur = conn.execute(
            "INSERT INTO documentos(arquivo, titulo, n_paginas) VALUES (?,?,?)",
            (arquivo.identificador, titulo, resultado.n_paginas),
        )
        doc_id = cur.lastrowid

        originais = [p.get("texto") or "" for p in resultado.paginas]
        limpos, _ = remover_cabecalho_rodape(originais)
        linhas = [
            (
                doc_id,
                p.get("pagina"),
                p.get("texto"),
                normalizador.preparar_texto(limpo),
            )
            for p, limpo in zip(resultado.paginas, limpos)
        ]
        conn.executemany(
            "INSERT INTO paginas(doc_id, pagina, texto, texto_busca) VALUES (?,?,?,?)",
            linhas,
        )
        stats.documentos += 1
        stats.paginas += resultado.n_paginas
        stats.paginas_ocr += resultado.n_ocr
        stats.paginas_sem_texto += resultado.n_sem_texto
    conn.commit()
    return stats


def finalizar_carga(
    conn: sqlite3.Connection,
    stats: EstatisticasCarga,
    normalizador: Normalizador,
    versao_indice: str | None = None,
    versao_acervo: str | None = None,
) -> None:
    """Rebuild/optimize/ANALYZE/VACUUM e gravacao da versao do esquema."""
    schema.rebuild_fts(conn)
    schema.optimize_fts(conn)
    conn.commit()

    conn.execute("ANALYZE")
    conn.commit()

    conn.execute("VACUUM")

    gravar = schema.gravar_meta
    gravar(conn, "versao_esquema", str(schema.VERSAO_ESQUEMA))
    gravar(conn, schema.META_MODE_NORMALIZACAO, normalizador.modo)
    gravar(conn, "versao_indice", versao_indice or date.today().isoformat())
    if versao_acervo:
        gravar(conn, "versao_acervo", versao_acervo)
    gravar(conn, "documentos", str(stats.documentos))
    gravar(conn, "paginas", str(stats.paginas))
    gravar(conn, "paginas_ocr", str(stats.paginas_ocr))
    gravar(conn, "paginas_sem_texto", str(stats.paginas_sem_texto))
    conn.commit()


def construir(
    caminho: str,
    entradas: list[tuple[ArquivoAcervo, ResultadoExtracao]],
    normalizador: Normalizador,
    titulos: dict[str, str] | None = None,
    versao_indice: str | None = None,
    versao_acervo: str | None = None,
) -> EstatisticasCarga:
    destino = Path(caminho)
    for sufixo in ("", "-wal", "-shm"):
        Path(str(destino) + sufixo).unlink(missing_ok=True)
    conn = schema.abrir(str(destino))
    try:
        schema.criar(conn, modo_normalizacao=normalizador.modo)
        stats = carregar(conn, entradas, normalizador, titulos)
        finalizar_carga(conn, stats, normalizador, versao_indice, versao_acervo)
        return stats
    finally:
        conn.close()
