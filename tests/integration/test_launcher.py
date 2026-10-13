"""Testes do lancador (Sprint 5 / PRD 5.4, 5.11, 11.3).

Exercita validacao de estrutura/esquema, instancia unica (mutex), escolha de
porta, estado em ``%LOCALAPPDATA%``, readiness e o ciclo completo de iniciar e
encerrar liberando a unidade.
"""

from __future__ import annotations

import json
import socket
import threading
import urllib.request

import pytest

from light_indexer import launcher, schema
from light_indexer.config import Config
from light_indexer.server import criar_app, servir


def _criar_indice(db, modo: str = "prefixo") -> None:
    con = schema.abrir(str(db))
    schema.criar(con, modo_normalizacao=modo)
    con.execute(
        "INSERT INTO documentos(arquivo, titulo, n_paginas) VALUES (?,?,?)",
        ("documentos/a.txt", "A", 1),
    )
    con.execute(
        "INSERT INTO paginas(doc_id, pagina, texto, texto_busca) VALUES (1, 1, ?, ?)",
        ("ola mundo", "ola mundo"),
    )
    con.commit()
    con.close()


@pytest.fixture
def pacote(tmp_path, monkeypatch):
    root = tmp_path / "pacote"
    (root / "web").mkdir(parents=True)
    (root / "web" / "index.html").write_text("<html></html>", encoding="utf-8")
    (root / "documentos").mkdir()
    db = root / "data" / "indice.db"
    db.parent.mkdir()
    _criar_indice(db)
    monkeypatch.setenv("LIGHT_INDEXER_STATE_DIR", str(tmp_path / "estado"))
    monkeypatch.setenv("LIGHT_INDEXER_FORCE_MUTEX_NAME", f"test-{tmp_path.name}")
    return {"root": root, "db": db, "docs": root / "documentos"}


def _cfg() -> Config:
    return Config(porta_preferida=0, abrir_navegador=False)


def _lancador(pacote) -> launcher.Lancador:
    return launcher.Lancador(
        cfg=_cfg(),
        root=pacote["root"],
        db_path=pacote["db"],
        docs_dir=pacote["docs"],
        host="127.0.0.1",
    )


# ---------------------------------------------------------------------------
# Validacao de estrutura e esquema
# ---------------------------------------------------------------------------


def test_validar_estrutura_e_esquema_ok(pacote):
    launcher.validar_estrutura(pacote["root"], pacote["db"])
    launcher.validar_esquema(pacote["db"])


def test_estrutura_sem_indice(pacote):
    with pytest.raises(launcher.ErroLancamento) as exc:
        launcher.validar_estrutura(pacote["root"], pacote["db"].with_name("nao.db"))
    assert "indice" in str(exc.value).lower()


def test_estrutura_sem_interface(pacote):
    (pacote["root"] / "web" / "index.html").unlink()
    with pytest.raises(launcher.ErroLancamento) as exc:
        launcher.validar_estrutura(pacote["root"], pacote["db"])
    assert "web" in str(exc.value).lower()


def test_esquema_incompativel(pacote):
    con = schema.abrir(str(pacote["db"]))
    schema.gravar_meta(con, "versao_esquema", "99")
    con.commit()
    con.close()
    with pytest.raises(launcher.ErroLancamento) as exc:
        launcher.validar_esquema(pacote["db"])
    assert "esquema" in str(exc.value).lower()


# ---------------------------------------------------------------------------
# Instancia unica e porta
# ---------------------------------------------------------------------------


def test_instancia_unica(pacote):
    primeira = launcher.InstanciaUnica()
    assert primeira.adquirir() is True
    segunda = launcher.InstanciaUnica()
    assert segunda.adquirir() is False
    primeira.liberar()
    terceira = launcher.InstanciaUnica()
    assert terceira.adquirir() is True
    terceira.liberar()


def test_escolher_porta_pula_ocupada():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        s.listen(1)
        ocupada = int(s.getsockname()[1])
        livre = launcher.escolher_porta("127.0.0.1", ocupada)
        assert livre != ocupada


def test_escolher_porta_zero():
    porta = launcher.escolher_porta("127.0.0.1", 0)
    assert 1 <= porta <= 65535


# ---------------------------------------------------------------------------
# Estado em %LOCALAPPDATA%
# ---------------------------------------------------------------------------


def test_estado_roundtrip(pacote):
    assert launcher.ler_estado() is None
    launcher.gravar_estado(8765, pid=1, url="http://127.0.0.1:8765")
    dados = launcher.ler_estado()
    assert dados["porta"] == 8765
    assert dados["pid"] == 1
    assert dados["url"] == "http://127.0.0.1:8765"
    assert dados["iniciado_em"]
    launcher.remover_estado()
    assert launcher.ler_estado() is None


# ---------------------------------------------------------------------------
# Readiness
# ---------------------------------------------------------------------------


def test_readiness_verifica_status(pacote):
    cfg = _cfg()
    app = criar_app(
        cfg=cfg, root=pacote["root"], db_path=pacote["db"], docs_dir=pacote["docs"]
    )
    porta = launcher.escolher_porta("127.0.0.1", 0)
    app.config["PORTA"] = porta
    servidor = servir(app, host="127.0.0.1", porta=porta)
    thread = threading.Thread(target=servidor.run, daemon=True)
    thread.start()
    try:
        assert launcher.aguardar_readiness(f"http://127.0.0.1:{porta}", timeout=5)
    finally:
        servidor.close()
        servidor.task_dispatcher.shutdown()
        thread.join(timeout=5)


def test_readiness_timeout():
    porta = launcher.escolher_porta("127.0.0.1", 0)
    assert launcher.aguardar_readiness(f"http://127.0.0.1:{porta}", timeout=0.5) is False


# ---------------------------------------------------------------------------
# Ciclo completo
# ---------------------------------------------------------------------------


def test_lancador_inicia_e_encerra_libera_unidade(pacote):
    lanc = _lancador(pacote)
    url = lanc.preparar()
    assert lanc.porta and url.endswith(str(lanc.porta))
    lanc.iniciar()
    try:
        with urllib.request.urlopen(url + "/api/status", timeout=5) as resposta:
            dados = json.loads(resposta.read().decode("utf-8"))
        assert dados["status"] == "ok"
        estado = launcher.ler_estado()
        assert estado["porta"] == lanc.porta
    finally:
        lanc.encerrar()

    assert launcher.ler_estado() is None
    outro = _lancador(pacote)
    outro.preparar()
    outro.encerrar()


def test_instancia_duplicada_recusada(pacote):
    primeira = _lancador(pacote)
    primeira.preparar()
    try:
        segunda = _lancador(pacote)
        with pytest.raises(launcher.ErroLancamento) as exc:
            segunda.preparar()
        assert "ja esta aberto" in str(exc.value).lower()
    finally:
        primeira.encerrar()


def test_lancador_recusa_pacote_incompleto(pacote):
    (pacote["root"] / "web" / "index.html").unlink()
    with pytest.raises(launcher.ErroLancamento):
        _lancador(pacote).preparar()
