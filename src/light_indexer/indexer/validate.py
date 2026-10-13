"""Validacao do indice antes de congelar e copiar (PRD 5.5 etapa 7, 6.6)."""

from __future__ import annotations

from pathlib import Path

from .. import schema
from .cache import CacheExtracao
from .inventory import inventariar
from .report import Relatorio


def validar(
    db_path: str | Path,
    acervo: Path,
    prefixo: str = "documentos",
    cache: CacheExtracao | None = None,
    esperados: set[str] | None = None,
) -> Relatorio:
    """Confere o indice contra o acervo.

    ``esperados`` permite validar uma amostra: quando informado, compara apenas
    com esse conjunto de identificadores em vez de todo o acervo.
    """
    rel = Relatorio()
    caminho = Path(db_path)
    if not caminho.is_file():
        rel.pendencias.append(f"banco ausente: {caminho}")
        return rel

    conn = schema.abrir(str(caminho), somente_leitura=True)
    try:
        rel.integrity_check = schema.verificar_integridade(conn)
        rel.modo_normalizacao = schema.modo_normalizacao(conn) or ""

        rel.documentos_indexados = conn.execute(
            "SELECT COUNT(*) FROM documentos"
        ).fetchone()[0]
        rel.paginas_indexadas = conn.execute(
            "SELECT COUNT(*) FROM paginas"
        ).fetchone()[0]
        rel.paginas_sem_texto = conn.execute(
            "SELECT COUNT(*) FROM paginas WHERE texto IS NULL OR TRIM(texto)=''"
        ).fetchone()[0]

        arquivos_db = {row[0] for row in conn.execute("SELECT arquivo FROM documentos")}
        if esperados is not None:
            encontrados = set(esperados)
        else:
            encontrados = {a.identificador for a in inventariar(Path(acervo), prefixo=prefixo)}
        rel.documentos_encontrados = len(encontrados)
        rel.arquivos_sem_registro = len(encontrados - arquivos_db)
        rel.registros_sem_arquivo = len(arquivos_db - encontrados)

        if cache is not None:
            _, ocr, _ = cache.total_paginas()
            rel.paginas_ocr = ocr
        else:
            valor = schema.ler_meta(conn, "paginas_ocr")
            try:
                rel.paginas_ocr = int(valor) if valor else 0
            except (TypeError, ValueError):
                rel.paginas_ocr = 0
    finally:
        conn.close()

    if rel.integrity_check != "ok":
        rel.pendencias.append(f"integrity_check: {rel.integrity_check}")
    if rel.arquivos_sem_registro:
        rel.pendencias.append(f"arquivos sem registro: {rel.arquivos_sem_registro}")
    if rel.registros_sem_arquivo:
        rel.pendencias.append(f"registros sem arquivo: {rel.registros_sem_arquivo}")
    if rel.documentos_encontrados and rel.documentos_indexados != rel.documentos_encontrados:
        rel.pendencias.append(
            f"documentos indexados ({rel.documentos_indexados}) != "
            f"encontrados ({rel.documentos_encontrados})"
        )
    if rel.documentos_indexados == 0:
        rel.pendencias.append("indice vazio")
    return rel
