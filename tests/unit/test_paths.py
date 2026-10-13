"""Testes da raiz do pacote nos tres modos (PRD 5.2, 5.4 - Sprint 5).

Cobre: sobrescrita por ambiente, executavel empacotado (PyInstaller) e o
diretorio temporario interno ``_MEIPASS``.
"""

from __future__ import annotations

import sys

from light_indexer import paths


def test_raiz_por_ambiente(tmp_path, monkeypatch):
    destino = tmp_path / "unidade"
    destino.mkdir()
    monkeypatch.setenv(paths.ENV_ROOT, str(destino))
    assert paths.get_application_root() == destino.resolve()


def test_raiz_empacotada(tmp_path, monkeypatch):
    exe_dir = tmp_path / "pacote"
    exe_dir.mkdir()
    exe = exe_dir / "LightIndexer.exe"
    exe.write_bytes(b"")
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(exe))
    monkeypatch.delattr(sys, "_MEIPASS", raising=False)
    assert paths.get_application_root() == exe_dir.resolve()


def test_raiz_empacotada_com_meipass(tmp_path, monkeypatch):
    exe_dir = tmp_path / "pacote"
    exe_dir.mkdir()
    (exe_dir / "config").mkdir()
    (exe_dir / "config" / "app.json").write_text("{}", encoding="utf-8")
    exe = exe_dir / "LightIndexer.exe"
    exe.write_bytes(b"")

    meipass = tmp_path / "_MEI123"
    meipass.mkdir()
    (meipass / "config").mkdir()
    (meipass / "config" / "app.json").write_text("{}", encoding="utf-8")

    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(exe))
    monkeypatch.setattr(sys, "_MEIPASS", str(meipass), raising=False)
    # Empacotado: a raiz e sempre a pasta do executavel, nunca _MEIPASS.
    assert paths.get_application_root() == exe_dir.resolve()


def test_raiz_meipass_sem_frozen(tmp_path, monkeypatch):
    meipass = tmp_path / "_MEI456"
    meipass.mkdir()
    monkeypatch.delenv(paths.ENV_ROOT, raising=False)
    monkeypatch.delattr(sys, "frozen", raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", str(meipass), raising=False)
    assert paths.get_application_root() == meipass.resolve()


def test_diretorio_estado_por_ambiente(tmp_path, monkeypatch):
    monkeypatch.setenv("LIGHT_INDEXER_STATE_DIR", str(tmp_path / "estado"))
    assert paths.diretorio_estado() == (tmp_path / "estado").resolve()
