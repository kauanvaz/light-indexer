"""Testes do teste de fumaca FTS5 (Sprint 6 / PRD 5.9, 12 - R6)."""

from __future__ import annotations

import json
import sqlite3

from light_indexer import smoke


def test_fts5_disponivel():
    resultado = smoke.verificar_fts5()
    assert resultado.ok is True
    assert resultado.detalhes["prefixo"] == 1
    assert resultado.detalhes["diacriticos"] == 1
    assert resultado.detalhes["integrity_check"] == "ok"
    assert "FTS5" in resultado.mensagem


def test_main_grava_saida(tmp_path):
    saida = tmp_path / "smoke.json"
    codigo = smoke.main(["--saida", str(saida)])
    assert codigo == 0
    dados = json.loads(saida.read_text(encoding="utf-8"))
    assert dados["ok"] is True
    assert dados["detalhes"]["prefixo"] == 1


def test_falha_quando_sqlite_sem_fts5(monkeypatch):
    class FakeSqlite:
        sqlite_version = "0"
        Error = sqlite3.Error

        @staticmethod
        def connect(*_args, **_kwargs):
            raise sqlite3.OperationalError("no such module: fts5")

    monkeypatch.setattr(smoke, "sqlite3", FakeSqlite)
    resultado = smoke.verificar_fts5()
    assert resultado.ok is False
    assert "indisponivel" in resultado.mensagem.lower()
    assert smoke.main([]) == 1
