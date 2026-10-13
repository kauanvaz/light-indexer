"""Testes do script de build (Sprint 6 / PRD 5.9, 5.10)."""

from __future__ import annotations

import sys

from light_indexer import build


def test_comando_pyinstaller_onedir_noconsole(tmp_path):
    comando = build.montar_comando_pyinstaller(
        tmp_path,
        destino=tmp_path / "dist",
        work=tmp_path / "work",
        spec=tmp_path / "work",
    )
    assert "--onedir" in comando
    assert "--noconsole" in comando
    assert "--console" not in comando
    assert comando[comando.index("--name") + 1] == "LightIndexer"
    assert comando[comando.index("--contents-directory") + 1] == "app"
    assert "--collect-submodules" in comando
    assert "waitress" in comando
    assert str(tmp_path / "scripts" / "lightindexer.py") in comando
    assert comando[0] == sys.executable


def test_comando_console_para_diagnostico(tmp_path):
    comando = build.montar_comando_pyinstaller(
        tmp_path,
        destino=tmp_path / "dist",
        work=tmp_path / "work",
        spec=tmp_path / "work",
        noconsole=False,
    )
    assert "--console" in comando
    assert "--noconsole" not in comando


def test_build_sem_empacotar_estagia_recursos(tmp_path):
    (tmp_path / "web").mkdir()
    (tmp_path / "web" / "index.html").write_text("<html></html>", encoding="utf-8")
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "app.json").write_text("{}", encoding="utf-8")

    destino = tmp_path / "build" / "dist"
    codigo = build.build_main(
        [
            "--root",
            str(tmp_path),
            "--destino",
            str(destino),
            "--sem-empacotar",
            "--sem-smoke",
        ]
    )
    assert codigo == 0
    app = destino / "LightIndexer"
    assert (app / "web" / "index.html").is_file()
    assert (app / "config" / "app.json").is_file()
    assert (app / "version.json").is_file()
    assert (tmp_path / "version.json").is_file()


def test_build_roda_smoke_fts5(tmp_path):
    (tmp_path / "web").mkdir()
    (tmp_path / "config").mkdir()
    codigo = build.build_main(
        [
            "--root",
            str(tmp_path),
            "--destino",
            str(tmp_path / "dist"),
            "--sem-empacotar",
        ]
    )
    assert codigo == 0
