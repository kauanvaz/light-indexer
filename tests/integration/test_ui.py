"""Teste da interface estatica (Sprint 3, PRD 7.2).

Verifica que a interface e servida localmente (sem CDN), que os recursos
existem e que o JavaScript esta ligado aos endpoints da API. Nao depende de
indice: as rotas de UI entregam apenas arquivos de ``web/``.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from light_indexer.config import Config
from light_indexer.server import criar_app

RAIZ = Path(__file__).resolve().parents[2]
WEB = RAIZ / "web"


@pytest.fixture
def cliente():
    app = criar_app(cfg=Config(), root=RAIZ, servico=object())
    app.config["TESTING"] = True
    return app.test_client()


def _texto(relativo: str) -> str:
    return (WEB / relativo).read_text(encoding="utf-8")


def test_interface_servida(cliente):
    resp = cliente.get("/")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert 'lang="pt-BR"' in html
    assert "/css/estilo.css" in html
    assert "/js/app.js" in html
    assert "/assets/favicon.svg" in html


def test_foco_automatico_no_campo(cliente):
    html = cliente.get("/").get_data(as_text=True)
    assert 'id="campo"' in html
    assert "autofocus" in html


def test_css_servido_localmente(cliente):
    resp = cliente.get("/css/estilo.css")
    assert resp.status_code == 200
    assert resp.headers["Content-Type"].startswith("text/css")


def test_js_servido_localmente(cliente):
    resp = cliente.get("/js/app.js")
    assert resp.status_code == 200
    assert "javascript" in resp.headers["Content-Type"]


def test_favicon_servido_localmente(cliente):
    resp = cliente.get("/assets/favicon.svg")
    assert resp.status_code == 200
    assert "image/svg+xml" in resp.headers["Content-Type"]


def test_recurso_inexistente_404(cliente):
    assert cliente.get("/css/nao-existe.css").status_code == 404
    assert cliente.get("/js/nao-existe.js").status_code == 404


def test_sem_recursos_externos():
    """PRD 7.2/RNF2: nenhum recurso de CDN ou rede externa."""
    for relativo in ("index.html", "css/estilo.css", "js/app.js"):
        texto = _texto(relativo)
        assert "http://" not in texto, relativo
        assert "https://" not in texto, relativo
        assert "//cdn" not in texto, relativo
        assert "@import" not in texto, relativo


def test_js_ligado_a_api():
    """A interface deve conversar apenas com os endpoints do PRD 7.1."""
    js = _texto("js/app.js")
    assert "/api/search" in js
    assert "/api/status" in js
    assert "/documentos/" in js


def test_link_do_documento_abre_na_pagina():
    """UC3/PRD 7.2: o resultado liga ao documento com o fragmento #page=N."""
    js = _texto("js/app.js")
    assert "#page=" in js
    assert "target" in js and "noopener" in js


def test_contrato_dos_estados_e_paginacao():
    html = _texto("index.html")
    for identificador in ("form-busca", "campo", "resumo", "estado", "lista", "paginacao"):
        assert f'id="{identificador}"' in html
    js = _texto("js/app.js")
    for estado in ("carregando", "inicial", "vazio", "erro"):
        assert estado in js
    assert "aria-live" in html


def test_estado_na_url():
    """UC9: o termo e a pagina ficam na URL (q/page)."""
    js = _texto("js/app.js")
    assert "URLSearchParams" in js
    assert "pushState" in js
    assert "popstate" in js


def test_instrucao_de_encerramento_visivel():
    """PRD 7.2 (view Encerramento): instrucao visivel/descobrivel."""
    html = _texto("index.html")
    assert "remover o HD/SSD" in html
    assert "encerre o Light indexer" in html
