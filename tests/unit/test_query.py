"""Testes da analise/validacao da consulta (PRD 5.7)."""

from __future__ import annotations

import pytest

from light_indexer.search.normalize import Normalizador
from light_indexer.search.query import ConsultaInvalida, analisar


def test_analisar_monta_match_seguro():
    c = analisar("licitação 2026", Normalizador(modo="prefixo"))
    assert not c.vazia
    assert c.termos == ["licitação", "2026"]
    assert c.match == '"licitação"* AND "2026"*'


def test_analisar_vazia():
    c = analisar("   ", Normalizador(modo="prefixo"))
    assert c.vazia
    assert c.match == ""
    assert c.termos == []


def test_analisar_limite_de_tamanho():
    with pytest.raises(ConsultaInvalida):
        analisar("a" * 257, Normalizador(modo="prefixo"), max_len=256)


def test_analisar_limita_numero_de_termos():
    c = analisar("um dois tres quatro", Normalizador(modo="prefixo", max_termos=2))
    assert c.match == '"um"* AND "dois"*'
