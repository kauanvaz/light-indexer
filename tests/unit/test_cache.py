"""Testes do cache de extracao retomavel (PRD 6.4)."""

from __future__ import annotations

from light_indexer.indexer.cache import (
    CacheExtracao,
    ResultadoExtracao,
    chave_cache,
)


def test_gravar_obter(tmp_path):
    cache = CacheExtracao.criar(tmp_path)
    res = ResultadoExtracao(
        paginas=[{"pagina": 1, "texto": "ola", "fonte": "nativo"}],
        n_ocr=0,
        n_sem_texto=0,
    )
    chave = chave_cache("hash1", "lang=por;dpi=200;min=20")
    assert not cache.tem(chave)
    cache.gravar(chave, "documentos/a.pdf", "hash1", "lang=por;dpi=200;min=20", res)
    assert cache.tem(chave)
    obtido = cache.obter(chave)
    assert obtido is not None
    assert obtido.paginas[0]["texto"] == "ola"
    assert obtido.n_paginas == 1
    cache.fechar()


def test_chave_muda_com_parametros(tmp_path):
    cache = CacheExtracao.criar(tmp_path)
    chave1 = chave_cache("h", "lang=por;dpi=200;min=20")
    chave2 = chave_cache("h", "lang=eng;dpi=200;min=20")
    cache.gravar(chave1, "a", "h", "lang=por;dpi=200;min=20", ResultadoExtracao())
    assert cache.tem(chave1)
    assert not cache.tem(chave2)
    cache.fechar()


def test_total_paginas(tmp_path):
    cache = CacheExtracao.criar(tmp_path)
    c = chave_cache("h", "p")
    cache.gravar(
        c,
        "a",
        "h",
        "p",
        ResultadoExtracao(
            paginas=[{"pagina": 1}, {"pagina": 2}], n_ocr=1, n_sem_texto=1
        ),
    )
    n_pag, n_ocr, n_sem = cache.total_paginas()
    assert (n_pag, n_ocr, n_sem) == (2, 1, 1)
    cache.fechar()
