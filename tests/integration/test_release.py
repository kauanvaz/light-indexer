"""Teste de integracao do script de release (Sprint 6 / PRD 5.9, UC7).

Monta um pacote portatil completo a partir de um indice real de amostra,
sem depender do PyInstaller: cria um "executavel" fake, um acervo .txt e o
indice, e exercita copia, validacao, smoke FTS5 e version.json.
"""

from __future__ import annotations

from light_indexer import release, version
from light_indexer.indexer.cache import CacheExtracao
from light_indexer.indexer.extract import (
    Extrator,
    ParametrosExtracao,
    processar_arquivos,
)
from light_indexer.indexer.inventory import inventariar
from light_indexer.indexer.load import construir
from light_indexer.search.normalize import Normalizador


def _montar_acervo(tmp_path, conteudo: dict[str, str]):
    acervo = tmp_path / "acervo"
    acervo.mkdir()
    for nome, texto in conteudo.items():
        (acervo / nome).write_text(texto, encoding="utf-8")
    return acervo


def _construir_indice(acervo, tmp_path):
    arquivos = inventariar(acervo)
    cache = CacheExtracao.criar(tmp_path / "cache")
    params = ParametrosExtracao()
    entradas, falhas = processar_arquivos(
        arquivos, cache, params, Extrator(params), resume=True, workers=1
    )
    assert falhas == 0
    db = tmp_path / "indice.db"
    construir(str(db), entradas, Normalizador(modo="prefixo"), {})
    cache.fechar()
    return db


def _app_fake(tmp_path):
    app = tmp_path / "app"
    (app / "web").mkdir(parents=True)
    (app / "web" / "index.html").write_text("<html></html>", encoding="utf-8")
    (app / "config").mkdir()
    (app / "config" / "app.json").write_text("{}", encoding="utf-8")
    (app / release.EXE_NOME).write_bytes(b"MZ")
    return app


def test_montar_pacote_completo(tmp_path):
    acervo = _montar_acervo(
        tmp_path,
        {
            "edital.txt": "Edital de licitação pública 2026",
            "contrato.txt": "Contrato de prestação de serviços",
        },
    )
    db = _construir_indice(acervo, tmp_path)
    app = _app_fake(tmp_path)
    destino = tmp_path / "release"
    relatorio = tmp_path / "build" / "relatorio.txt"

    codigo, resumo = release.montar_pacote(app, db, acervo, destino, relatorio)
    assert codigo == release.EXIT_OK
    assert resumo["validacao_ok"] is True
    assert resumo["smoke_ok"] is True

    assert (destino / release.EXE_NOME).is_file()
    assert (destino / "data" / "indice.db").is_file()
    assert (destino / "documentos" / "edital.txt").is_file()
    assert (destino / "web" / "index.html").is_file()

    dados = version.ler_version_json(destino / "version.json")
    assert dados["documentos"] == 2
    assert dados["versao_esquema"] == 1
    assert dados["versao_indice"]

    texto = relatorio.read_text(encoding="utf-8")
    assert "Pendencias:               0" in texto


def test_montar_pacote_falha_validacao(tmp_path):
    acervo = _montar_acervo(tmp_path, {"a.txt": "texto unico"})
    db = _construir_indice(acervo, tmp_path)
    app = _app_fake(tmp_path)
    # Arquivo novo no acervo apos a indexacao -> pendencia.
    (acervo / "novo.txt").write_text("novo", encoding="utf-8")

    codigo, resumo = release.montar_pacote(
        app, db, acervo, tmp_path / "release", tmp_path / "relatorio.txt"
    )
    assert codigo == release.EXIT_VALIDACAO
    assert resumo["validacao_ok"] is False
    assert resumo["pendencias"]


def test_release_main_sem_executavel(tmp_path):
    acervo = _montar_acervo(tmp_path, {"a.txt": "texto"})
    db = _construir_indice(acervo, tmp_path)
    codigo = release.release_main(
        [
            "--root",
            str(tmp_path),
            "--app",
            str(tmp_path / "inexistente"),
            "--db",
            str(db),
            "--acervo",
            str(acervo),
            "--destino",
            str(tmp_path / "release"),
            "--relatorio",
            str(tmp_path / "relatorio.txt"),
        ]
    )
    assert codigo == release.EXIT_CONFIG


def test_release_main_ok(tmp_path):
    acervo = _montar_acervo(tmp_path, {"a.txt": "texto"})
    db = _construir_indice(acervo, tmp_path)
    app = _app_fake(tmp_path)
    codigo = release.release_main(
        [
            "--root",
            str(tmp_path),
            "--app",
            str(app),
            "--db",
            str(db),
            "--acervo",
            str(acervo),
            "--destino",
            str(tmp_path / "release"),
            "--relatorio",
            str(tmp_path / "relatorio.txt"),
        ]
    )
    assert codigo == release.EXIT_OK
    assert (tmp_path / "release" / "version.json").is_file()
