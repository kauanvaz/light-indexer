"""Teste de integracao do pipeline de indexacao (Sprint 1).

Usa um acervo temporario de arquivos .txt para exercitar inventory -> extrair
-> carregar -> validar e a busca no FTS5, sem depender de PDFs.
"""

from __future__ import annotations

import sqlite3

from light_indexer import schema
from light_indexer.indexer.cache import CacheExtracao
from light_indexer.indexer.extract import (
    Extrator,
    ParametrosExtracao,
    processar_arquivos,
)
from light_indexer.indexer.inventory import inventariar
from light_indexer.indexer.load import construir
from light_indexer.indexer.validate import validar
from light_indexer.search.normalize import Normalizador


def _montar(tmp_path, conteudo: dict[str, str]):
    acervo = tmp_path / "acervo"
    acervo.mkdir()
    for nome, texto in conteudo.items():
        (acervo / nome).write_text(texto, encoding="utf-8")
    return acervo


def _extrair(acervo, tmp_path, modo="prefixo"):
    arquivos = inventariar(acervo)
    cache = CacheExtracao.criar(tmp_path / "cache")
    params = ParametrosExtracao()
    extrator = Extrator(params)
    entradas, falhas = processar_arquivos(
        arquivos, cache, params, extrator, resume=True, workers=1
    )
    assert falhas == 0
    return cache, entradas


def test_pipeline_completo_e_busca(tmp_path):
    acervo = _montar(
        tmp_path,
        {
            "edital-licitacao.txt": "Edital de licitação pública municipal 2026",
            "contrato-servico.txt": "Contrato de prestação de serviços de limpeza",
        },
    )
    cache, entradas = _extrair(acervo, tmp_path)
    db = tmp_path / "indice.db"
    stats = construir(str(db), entradas, Normalizador(modo="prefixo"), {})
    assert stats.documentos == 2
    assert stats.paginas == 2

    rel = validar(db, acervo, cache=cache)
    assert rel.ok
    assert rel.documentos_encontrados == 2
    assert rel.paginas_indexadas == 2
    assert rel.integrity_check == "ok"

    con = sqlite3.connect(str(db))
    match = Normalizador(modo="prefixo").montar_match("licitacao")
    linhas = con.execute(
        "SELECT d.arquivo FROM busca JOIN paginas p ON p.id=busca.rowid "
        "JOIN documentos d ON d.id=p.doc_id WHERE busca MATCH ?",
        (match,),
    ).fetchall()
    con.close()
    assert linhas == [("documentos/edital-licitacao.txt",)]
    cache.fechar()


def test_pipeline_retomavel_usa_cache(tmp_path):
    acervo = _montar(tmp_path, {"a.txt": "conteudo um"})
    cache, entradas1 = _extrair(acervo, tmp_path)
    n = cache.contar()
    assert n == 1

    # Segunda passada: reaproveita o cache (mesma chave) sem crescer.
    arquivos = inventariar(acervo)
    entradas2, _ = processar_arquivos(
        arquivos, cache, ParametrosExtracao(), Extrator(ParametrosExtracao()),
        resume=True, workers=1,
    )
    assert cache.contar() == 1
    assert entradas2[0][1].paginas[0]["texto"] == "conteudo um"
    cache.fechar()


def test_rebuild_sobrescreve(tmp_path):
    acervo = _montar(tmp_path, {"a.txt": "texto unico"})
    cache, entradas = _extrair(acervo, tmp_path)
    db = tmp_path / "indice.db"
    n = Normalizador(modo="prefixo")
    construir(str(db), entradas, n, {})
    # Segunda construcao no mesmo caminho nao deve falhar por UNIQUE.
    stats = construir(str(db), entradas, n, {})
    assert stats.documentos == 1
    rel = validar(db, acervo, cache=cache)
    assert rel.ok
    cache.fechar()


def test_validar_detecta_pendencia(tmp_path):
    acervo = _montar(tmp_path, {"a.txt": "texto"})
    cache, entradas = _extrair(acervo, tmp_path)
    db = tmp_path / "indice.db"
    construir(str(db), entradas, Normalizador(modo="prefixo"), {})
    # Arquivo a mais no acervo apos a indexacao -> pendencia.
    (acervo / "novo.txt").write_text("novo", encoding="utf-8")
    rel = validar(db, acervo, cache=cache)
    assert not rel.ok
    assert rel.arquivos_sem_registro == 1
    cache.fechar()
