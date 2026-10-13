"""Testes do esquema versionado e compatibilidade (PRD 5.6)."""

from __future__ import annotations

import sqlite3

import pytest

from light_indexer import schema


def test_criar_e_versionar(tmp_path):
    caminho = tmp_path / "indice.db"
    con = schema.abrir(str(caminho))
    schema.criar(con, modo_normalizacao="stemming")
    assert schema.versao_esquema(con) == schema.VERSAO_ESQUEMA
    assert schema.modo_normalizacao(con) == "stemming"
    assert schema.compatibilidade_ok(con)
    con.close()


def test_tabelas_existem(tmp_path):
    caminho = tmp_path / "indice.db"
    con = schema.abrir(str(caminho))
    schema.criar(con)
    nomes = {r[0] for r in con.execute("SELECT name FROM sqlite_master")}
    assert {"documentos", "paginas", "busca", "meta"} <= nomes
    con.close()


def test_abertura_somente_leitura(tmp_path):
    caminho = tmp_path / "indice.db"
    con = schema.abrir(str(caminho))
    schema.criar(con)
    con.close()
    ro = schema.abrir(str(caminho), somente_leitura=True, imutavel=True)
    assert ro.execute("SELECT COUNT(*) FROM documentos").fetchone()[0] == 0
    with pytest.raises(sqlite3.OperationalError):
        ro.execute("INSERT INTO documentos(arquivo) VALUES ('x')")
    ro.close()


def test_versao_ausente_em_banco_vazio(tmp_path):
    con = schema.abrir(str(tmp_path / "vazio.db"))
    assert schema.versao_esquema(con) is None
    con.close()
