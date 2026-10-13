"""Testes de normalizacao e montagem segura de MATCH (PRD 5.7, 5.8)."""

from __future__ import annotations

import sqlite3

import pytest

from light_indexer.search.normalize import (
    Normalizador,
    corrigir_hifenizacao,
    normalizar_texto,
    remover_cabecalho_rodape,
)


def test_normalizar_texto_minusculas_e_hifen():
    assert normalizar_texto("Licitação\nPúBliCa") == "licitação\npública"
    assert corrigir_hifenizacao("lici-\ntação") == "licitação"


def test_remover_cabecalho_rodape():
    paginas = [
        "CABECALHO\nconteudo 1\nRODAPE",
        "CABECALHO\nconteudo 2\nRODAPE",
        "CABECALHO\nconteudo 3\nRODAPE",
    ]
    limpas, removidas = remover_cabecalho_rodape(paginas)
    assert removidas == {"cabecalho", "rodape"}
    assert limpas == ["conteudo 1", "conteudo 2", "conteudo 3"]


def test_remover_cabecalho_curto_demais():
    paginas = ["a\nb", "a\nc"]
    limpas, removidas = remover_cabecalho_rodape(paginas)
    assert removidas == set()
    assert limpas == paginas


def test_montar_match_prefixo():
    n = Normalizador(modo="prefixo", max_termos=3)
    assert n.montar_match("licitação pública 2026 extra") == (
        '"licitação"* AND "pública"* AND "2026"*'
    )


def test_montar_match_stemming():
    n = Normalizador(modo="stemming")
    match = n.montar_match("débitos")
    assert match == '"debit"'


def test_montar_match_vazio():
    n = Normalizador(modo="prefixo")
    assert n.montar_match("") == ""
    assert n.montar_match(None) == ""


def test_montar_match_ignora_pontuacao():
    n = Normalizador(modo="prefixo")
    match = n.montar_match('-- "licitação" -2026;')
    assert match == '"licitação"* AND "2026"*'


def test_modo_invalido():
    with pytest.raises(ValueError):
        Normalizador(modo="inexistente")


def _fts():
    con = sqlite3.connect(":memory:")
    con.execute(
        "CREATE VIRTUAL TABLE t USING fts5(x, "
        "tokenize='unicode61 remove_diacritics 2', prefix='2 3 4')"
    )
    return con


def test_prefixo_encontra_variacao_no_fim():
    con = _fts()
    con.execute("INSERT INTO t(x) VALUES ('licitacao publica')")
    n = Normalizador(modo="prefixo")
    row = con.execute("SELECT count(*) FROM t WHERE t MATCH ?", (n.montar_match("licita"),)).fetchone()
    assert row[0] == 1
    con.close()


def test_stemming_encontra_singular_plural():
    con = _fts()
    con.execute("INSERT INTO t(x) VALUES ('debito')")
    n = Normalizador(modo="stemming")
    con.execute("INSERT INTO t(x) VALUES (?)", (n.preparar_texto("débito"),))
    row = con.execute("SELECT count(*) FROM t WHERE t MATCH ?", (n.montar_match("débitos"),)).fetchone()
    assert row[0] == 1
    con.close()
