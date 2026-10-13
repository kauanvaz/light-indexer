"""Testes do destaque de trechos escapado (PRD 5.7, 7.2)."""

from __future__ import annotations

from light_indexer.search.highlight import destacar
from light_indexer.search.normalize import Normalizador


def test_marca_termo_ignorando_acento():
    n = Normalizador(modo="prefixo")
    saida = destacar("Edital de licitação pública", ["licitacao"], n)
    assert "<mark>licitação</mark>" in saida


def test_marca_por_prefixo():
    n = Normalizador(modo="prefixo")
    saida = destacar("Contrato de licitacao", ["licita"], n)
    assert "<mark>licitacao</mark>" in saida


def test_escapa_html_do_acervo():
    n = Normalizador(modo="prefixo")
    saida = destacar("perigo <script>alert(1)</script> fim", ["perigo"], n)
    assert "<script>" not in saida
    assert "&lt;script&gt;" in saida


def test_janela_com_reticencias():
    n = Normalizador(modo="prefixo")
    texto = ("palavra " * 60) + "alvo " + ("palavra " * 60)
    saida = destacar(texto, ["alvo"], n, janela=60)
    assert saida.startswith("…")
    assert saida.endswith("…")
    assert "<mark>alvo</mark>" in saida


def test_sem_termos_retorna_trecho_simples():
    n = Normalizador(modo="prefixo")
    assert destacar("texto simples", [], n) == "texto simples"


def test_texto_vazio():
    n = Normalizador(modo="prefixo")
    assert destacar("", ["x"], n) == ""
    assert destacar(None, ["x"], n) == ""
