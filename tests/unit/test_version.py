"""Testes da geracao de version.json (Sprint 6 / PRD 5.9, 6.5, 7.1)."""

from __future__ import annotations

from light_indexer import schema, version


def _criar_indice(db) -> None:
    con = schema.abrir(str(db))
    schema.criar(con, modo_normalizacao="prefixo")
    con.execute(
        "INSERT INTO documentos(arquivo, titulo, n_paginas) VALUES (?,?,?)",
        ("documentos/a.txt", "A", 1),
    )
    con.execute(
        "INSERT INTO paginas(doc_id, pagina, texto, texto_busca) VALUES (1,1,?,?)",
        ("ola", "ola"),
    )
    schema.gravar_meta(con, "versao_indice", "2026-10-08")
    schema.gravar_meta(con, "versao_acervo", "2026-10")
    con.commit()
    con.close()


def test_coletar_versoes_sem_indice():
    dados = version.coletar_versoes()
    assert dados["versao_esquema"] == schema.VERSAO_ESQUEMA
    assert dados["versao_indice"] is None
    assert dados["versao_acervo"] is None
    assert dados["versao_app"]


def test_coletar_versoes_com_indice(tmp_path):
    db = tmp_path / "indice.db"
    _criar_indice(db)
    dados = version.coletar_versoes(db)
    assert dados["versao_esquema"] == schema.VERSAO_ESQUEMA
    assert dados["versao_indice"] == "2026-10-08"
    assert dados["versao_acervo"] == "2026-10"
    assert dados["documentos"] == 1
    assert dados["paginas"] == 1


def test_indice_ausente_nao_falha(tmp_path):
    dados = version.coletar_versoes(tmp_path / "nao.db")
    assert dados["versao_indice"] is None


def test_gerar_e_ler_version_json(tmp_path):
    db = tmp_path / "indice.db"
    _criar_indice(db)
    destino = tmp_path / "pacote" / "version.json"
    gravado = version.gerar_version_json(destino, db_path=db)
    assert destino.is_file()
    assert gravado["gerado_em"]
    lido = version.ler_version_json(destino)
    assert lido["versao_app"] == gravado["versao_app"]
    assert lido["versao_indice"] == "2026-10-08"
    assert lido["documentos"] == 1


def test_ler_version_json_ausente(tmp_path):
    assert version.ler_version_json(tmp_path / "nada.json") is None
