"""Teste de integracao do servico e da API local (Sprint 2).

Monta um indice FTS5 a partir de arquivos .txt e exercita SearchService e os
endpoints Flask (search, status, documents) pelo test client, sem rede.
"""

from __future__ import annotations

import os
import sqlite3

import pytest

from light_indexer.config import Config
from light_indexer.indexer.cache import CacheExtracao
from light_indexer.indexer.extract import Extrator, ParametrosExtracao, processar_arquivos
from light_indexer.indexer.inventory import inventariar
from light_indexer.indexer.load import construir
from light_indexer.search.normalize import Normalizador
from light_indexer.search.service import DocumentoNaoEncontrado, SearchService
from light_indexer.server import criar_app

CONTEUDO = {
    "edital-licitacao.txt": "Edital de licitação pública municipal 2026 para compra de material",
    "contrato-limpeza.txt": "Contrato de prestação de serviços de limpeza predial",
    "nota-debito.txt": "Nota de débito referente ao mês de setembro",
}


def _construir_indice(tmp_path, conteudo=None):
    acervo = tmp_path / "acervo"
    acervo.mkdir()
    for nome, texto in (conteudo or CONTEUDO).items():
        (acervo / nome).write_text(texto, encoding="utf-8")
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
    return acervo, db


@pytest.fixture
def ambiente(tmp_path):
    acervo, db = _construir_indice(tmp_path)
    cfg = Config()
    servico = SearchService(
        db, acervo, normalizador=Normalizador(modo="prefixo"), cfg=cfg
    )
    app = criar_app(
        cfg=cfg, root=tmp_path, db_path=db, docs_dir=acervo, servico=servico
    )
    app.config["TESTING"] = True
    return app, acervo, db, servico


def test_search_basica_com_destaque(ambiente):
    app, _, _, _ = ambiente
    resp = app.test_client().get("/api/search?q=licitacao")
    assert resp.status_code == 200
    dados = resp.get_json()
    assert dados["total"] == 1
    assert dados["page"] == 1 and dados["size"] == 20
    item = dados["results"][0]
    assert item["arquivo"] == "documentos/edital-licitacao.txt"
    assert item["pagina"] == 1
    assert "<mark>licitação</mark>" in item["trecho"]


def test_search_prefixo(ambiente):
    app, _, _, _ = ambiente
    dados = app.test_client().get("/api/search?q=licita").get_json()
    assert dados["total"] == 1
    assert dados["results"][0]["doc_id"] > 0


def test_search_vazia(ambiente):
    app, _, _, _ = ambiente
    dados = app.test_client().get("/api/search?q=").get_json()
    assert dados == {"total": 0, "page": 1, "size": 20, "results": []}


def test_search_limita_size(ambiente):
    app, _, _, _ = ambiente
    dados = app.test_client().get("/api/search?q=de&size=999").get_json()
    assert dados["size"] == 50  # tamanho_pagina_max


def test_search_size_invalido(ambiente):
    app, _, _, _ = ambiente
    resp = app.test_client().get("/api/search?q=de&size=abc")
    assert resp.status_code == 400
    assert "erro" in resp.get_json()


def test_search_consulta_longa(ambiente):
    app, _, _, _ = ambiente
    resp = app.test_client().get("/api/search?q=" + "a" * 300)
    assert resp.status_code == 400


def test_search_paginacao(ambiente):
    app, _, _, _ = ambiente
    c = app.test_client()
    p1 = c.get("/api/search?q=de&size=1&page=1").get_json()
    p2 = c.get("/api/search?q=de&size=1&page=2").get_json()
    assert p1["total"] == p2["total"] >= 2
    assert p1["results"][0] != p2["results"][0]


def test_status(ambiente):
    app, _, _, _ = ambiente
    resp = app.test_client().get("/api/status")
    assert resp.status_code == 200
    dados = resp.get_json()
    assert dados["status"] == "ok"
    assert dados["versao_esquema"] == 1
    assert dados["documentos"] == 3
    assert dados["porta"] == 8765


def test_documents_entrega_arquivo(ambiente):
    app, _, _, _ = ambiente
    c = app.test_client()
    item = c.get("/api/search?q=licitacao").get_json()["results"][0]
    resp = c.get(f"/documentos/{item['doc_id']}")
    assert resp.status_code == 200
    assert "licitação".encode("utf-8") in resp.data


def test_documents_inexistente(ambiente):
    app, _, _, _ = ambiente
    resp = app.test_client().get("/documentos/999999")
    assert resp.status_code == 404


def test_host_nao_local_rejeitado(ambiente):
    app, _, _, _ = ambiente
    resp = app.test_client().get("/api/status", headers={"Host": "evil.example"})
    assert resp.status_code == 403


def test_documento_recusa_traversal(ambiente):
    _, _, _, servico = ambiente
    con = sqlite3.connect(servico.db_path)
    con.execute(
        "INSERT INTO documentos(arquivo, titulo, n_paginas) VALUES (?,?,?)",
        ("documentos/../fora.txt", "malicioso", 1),
    )
    con.commit()
    novo_id = con.execute("SELECT MAX(id) FROM documentos").fetchone()[0]
    con.close()
    with pytest.raises(DocumentoNaoEncontrado):
        servico.documento(novo_id)


# ---------------------------------------------------------------------------
# Sprint 4 - entrega de documentos (PRD 7.1, 7.3, UC3)
# ---------------------------------------------------------------------------


def _inserir_documento(servico, arquivo: str, titulo: str = "manual") -> int:
    con = sqlite3.connect(servico.db_path)
    cur = con.execute(
        "INSERT INTO documentos(arquivo, titulo, n_paginas) VALUES (?,?,?)",
        (arquivo, titulo, 1),
    )
    con.commit()
    novo_id = cur.lastrowid
    con.close()
    return novo_id


def _primeiro_doc(cliente, termo: str = "licitacao") -> int:
    return cliente.get(f"/api/search?q={termo}").get_json()["results"][0]["doc_id"]


def test_documents_suporta_range(ambiente):
    app, _, _, _ = ambiente
    cliente = app.test_client()
    doc_id = _primeiro_doc(cliente)
    resp = cliente.get(f"/documentos/{doc_id}", headers={"Range": "bytes=0-9"})
    assert resp.status_code == 206
    assert resp.headers["Accept-Ranges"] == "bytes"
    assert resp.headers["Content-Range"].startswith("bytes 0-9/")
    assert len(resp.data) == 10


def test_documents_inline_e_accept_ranges(ambiente):
    app, _, _, _ = ambiente
    cliente = app.test_client()
    doc_id = _primeiro_doc(cliente)
    resp = cliente.get(f"/documentos/{doc_id}")
    assert resp.status_code == 200
    assert resp.headers["Accept-Ranges"] == "bytes"
    assert "inline" in resp.headers["Content-Disposition"]
    assert resp.headers["Cache-Control"] == "no-store"


def test_documents_pdf_abre_inline(ambiente):
    """Content-Type de PDF permite ao navegador abrir no #page=N (UC3)."""
    app, acervo, _, servico = ambiente
    (acervo / "grande.pdf").write_bytes(b"%PDF-1.4\n" + b"0" * 4096)
    doc_id = _inserir_documento(servico, "documentos/grande.pdf")
    resp = app.test_client().get(f"/documentos/{doc_id}")
    assert resp.status_code == 200
    assert resp.headers["Content-Type"].startswith("application/pdf")
    assert resp.headers["Accept-Ranges"] == "bytes"


def test_documents_arquivo_ausente(ambiente):
    app, acervo, _, _ = ambiente
    cliente = app.test_client()
    doc_id = _primeiro_doc(cliente)
    (acervo / "edital-licitacao.txt").unlink()
    resp = cliente.get(f"/documentos/{doc_id}")
    assert resp.status_code == 404
    corpo = resp.get_data(as_text=True).lower()
    assert "ausente" in corpo
    assert "light-indexer.log" in corpo


def test_documents_arquivo_ilegivel(ambiente):
    if not hasattr(os, "geteuid"):  # pragma: no cover - Windows
        pytest.skip("permissoes de arquivo POSIX indisponiveis")
    if os.geteuid() == 0:  # pragma: no cover - root ignora permissoes
        pytest.skip("root ignora permissoes de arquivo")
    app, acervo, _, _ = ambiente
    cliente = app.test_client()
    doc_id = _primeiro_doc(cliente)
    alvo = acervo / "edital-licitacao.txt"
    os.chmod(alvo, 0)
    try:
        resp = cliente.get(f"/documentos/{doc_id}")
    finally:
        os.chmod(alvo, 0o644)
    assert resp.status_code == 500
    assert "ler o arquivo" in resp.get_data(as_text=True).lower()


def test_documents_caminho_invalido_pela_rota(ambiente):
    app, _, _, servico = ambiente
    doc_id = _inserir_documento(servico, "documentos/../fora.txt", "traversal")
    resp = app.test_client().get(f"/documentos/{doc_id}")
    assert resp.status_code == 404
    assert "nao encontrado" in resp.get_data(as_text=True).lower()


def test_documents_id_nao_numerico(ambiente):
    app, _, _, _ = ambiente
    resp = app.test_client().get("/documentos/abc")
    assert resp.status_code == 404
    assert resp.headers["Content-Type"].startswith("text/plain")
    assert "documento" in resp.get_data(as_text=True).lower()
