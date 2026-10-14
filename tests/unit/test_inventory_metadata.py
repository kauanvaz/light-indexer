"""Testes de inventario e metadados (PRD 6.3 etapas 1 e 4)."""

from __future__ import annotations

from light_indexer.indexer.inventory import inventariar
from light_indexer.indexer.metadata import limpar_titulo, titulo_do_arquivo


def test_inventariar_deterministico(tmp_path):
    (tmp_path / "sub").mkdir()
    (tmp_path / "b.txt").write_text("b", encoding="utf-8")
    (tmp_path / "a.txt").write_text("a", encoding="utf-8")
    (tmp_path / "sub" / "c.pdf").write_bytes(b"%PDF-1.4")
    (tmp_path / "ignorar.md").write_text("x", encoding="utf-8")

    itens = inventariar(tmp_path)
    assert [i.identificador for i in itens] == [
        "documentos/a.txt",
        "documentos/b.txt",
        "documentos/sub/c.pdf",
    ]
    assert itens[2].relativo == "sub/c.pdf"


def test_inventariar_inclui_imagens(tmp_path):
    imagens = (
        "foto.png", "foto.jpg", "foto.jpeg",
        "scan.tif", "scan.tiff", "figura.bmp", "web.webp", "FOTO2.PNG",
    )
    for nome in imagens:
        (tmp_path / nome).write_bytes(b"x")
    (tmp_path / "ignorar.md").write_text("x", encoding="utf-8")
    (tmp_path / "ignorar.docx").write_bytes(b"x")

    itens = inventariar(tmp_path)

    assert {i.identificador for i in itens} == {
        f"documentos/{nome}" for nome in imagens
    }


def test_limpar_titulo():
    assert limpar_titulo("  Edital  2026  ") == "Edital 2026"
    assert limpar_titulo("tmp07sa1344.html") == ""
    assert limpar_titulo("") == ""
    assert limpar_titulo("ab") == ""
    assert limpar_titulo("x" * 300) == ""


def test_titulo_do_arquivo(tmp_path):
    arquivo = tmp_path / "ABR - Nota de débito.pdf"
    arquivo.write_bytes(b"")
    assert titulo_do_arquivo(arquivo) == "ABR - Nota de débito"
