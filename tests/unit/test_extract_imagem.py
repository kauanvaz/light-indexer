"""Testes de extracao de imagens (OCR) - contrato ResultadoExtracao.

O OCR e simulado pelo fixture ``pytesseract_falso``; as imagens sao arquivos
reais gerados com Pillow. O comportamento de degradacao atual e fixado:
falha generica de OCR afeta apenas a pagina; Tesseract ausente ou falha de
rasterizacao desativam o OCR da execucao. Sem Pillow o modulo inteiro e
ignorado (ambiente minimo de testes).
"""

from __future__ import annotations

import io

import pytest

from light_indexer.indexer.extract import (
    FONTE_OCR,
    FONTE_VAZIO,
    ErroExtracao,
    Extrator,
    ParametrosExtracao,
)
from light_indexer.indexer.inventory import EXTENSOES_IMAGEM

pytest.importorskip("PIL", reason="pillow indisponivel (uv sync --extra build)")

from PIL import Image  # noqa: E402

EXTENSOES = (".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".webp")


def _salvar_imagem(caminho):
    Image.new("RGB", (60, 30), "white").save(caminho)
    return caminho


def _png_bytes() -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (60, 30), "white").save(buffer, "png")
    return buffer.getvalue()


class _PixmapFalso:
    def __init__(self, png: bytes, formatos: list) -> None:
        self._png = png
        self._formatos = formatos

    def tobytes(self, formato):
        self._formatos.append(formato)
        return self._png


class _PaginaFalsa:
    """Duble de pagina PDF (sem pymupdf) para exercitar ``Extrator._ocr``."""

    def __init__(self, png: bytes | None = None, erro: Exception | None = None) -> None:
        self._png = png
        self._erro = erro
        self.n_pixmaps = 0
        self.dpis: list = []
        self.formatos: list = []

    def get_pixmap(self, dpi):
        self.n_pixmaps += 1
        self.dpis.append(dpi)
        if self._erro is not None:
            raise self._erro
        return _PixmapFalso(self._png, self.formatos)


def test_duble_reflete_hierarquia_real_do_pytesseract(pytesseract_falso):
    assert issubclass(pytesseract_falso.TesseractError, RuntimeError)
    assert issubclass(pytesseract_falso.TesseractNotFoundError, OSError)
    assert not issubclass(
        pytesseract_falso.TesseractNotFoundError, pytesseract_falso.TesseractError
    )


def test_imagem_ocr_com_sucesso(tmp_path, pytesseract_falso):
    pytesseract_falso.resposta = "recibo de pagamento"
    arquivo = _salvar_imagem(tmp_path / "nota.png")

    resultado = Extrator(ParametrosExtracao()).extrair(arquivo)

    assert resultado.paginas == [
        {"pagina": 1, "texto": "recibo de pagamento", "fonte": FONTE_OCR}
    ]
    assert resultado.n_ocr == 1
    assert resultado.n_sem_texto == 0
    assert resultado.n_paginas == 1
    assert len(pytesseract_falso.chamadas) == 1
    assert isinstance(pytesseract_falso.chamadas[0], Image.Image)
    assert pytesseract_falso.idiomas == ["por"]


def test_imagem_ocr_vazio_vira_sem_texto(tmp_path, pytesseract_falso):
    pytesseract_falso.resposta = " \n\t "
    arquivo = _salvar_imagem(tmp_path / "branco.png")

    resultado = Extrator(ParametrosExtracao()).extrair(arquivo)

    assert resultado.paginas == [{"pagina": 1, "texto": "", "fonte": FONTE_VAZIO}]
    assert resultado.n_ocr == 0
    assert resultado.n_sem_texto == 1


def test_imagem_ocr_curto_conta_como_ocr(tmp_path, pytesseract_falso):
    pytesseract_falso.resposta = "x"
    arquivo = _salvar_imagem(tmp_path / "curto.png")

    resultado = Extrator(ParametrosExtracao()).extrair(arquivo)

    assert resultado.paginas[0]["fonte"] == FONTE_OCR
    assert resultado.n_ocr == 1
    assert resultado.n_sem_texto == 0


def test_extensoes_de_imagem_coerentes_com_inventario():
    assert set(EXTENSOES) == set(EXTENSOES_IMAGEM)


def test_todas_as_extensoes_despacham_para_ocr(tmp_path, pytesseract_falso):
    pytesseract_falso.resposta = "texto"
    for extensao in EXTENSOES:
        arquivo = _salvar_imagem(tmp_path / f"arquivo{extensao}")
        resultado = Extrator(ParametrosExtracao()).extrair(arquivo)
        assert resultado.paginas[0]["fonte"] == FONTE_OCR, extensao
    assert len(pytesseract_falso.chamadas) == len(EXTENSOES)


def test_extensao_maiuscula_despacha_para_ocr(tmp_path, pytesseract_falso):
    pytesseract_falso.resposta = "texto"
    arquivo = _salvar_imagem(tmp_path / "FOTO.PNG")

    resultado = Extrator(ParametrosExtracao()).extrair(arquivo)

    assert resultado.paginas[0]["fonte"] == FONTE_OCR


def test_imagem_corrompida_e_falha_do_arquivo(tmp_path, pytesseract_falso):
    pytesseract_falso.resposta = "texto"
    corrompida = tmp_path / "lixo.png"
    corrompida.write_bytes(b"isso nao e um png")
    extrator = Extrator(ParametrosExtracao())

    with pytest.raises(ErroExtracao, match="imagem invalida"):
        extrator.extrair(corrompida)

    assert len(pytesseract_falso.chamadas) == 0
    resultado = extrator.extrair(_salvar_imagem(tmp_path / "boa.png"))
    assert resultado.paginas[0]["fonte"] == FONTE_OCR


def test_imagem_truncada_degrada_para_sem_texto(tmp_path, pytesseract_falso):
    pytesseract_falso.resposta = "texto"
    png = _png_bytes()
    truncada = tmp_path / "truncada.png"
    truncada.write_bytes(png[: png.index(b"IDAT") + 10])
    extrator = Extrator(ParametrosExtracao())

    resultado = extrator.extrair(truncada)

    assert resultado.paginas == [{"pagina": 1, "texto": "", "fonte": FONTE_VAZIO}]
    assert resultado.n_ocr == 0
    assert resultado.n_sem_texto == 1
    assert len(pytesseract_falso.chamadas) == 1

    seguinte = extrator.extrair(_salvar_imagem(tmp_path / "boa.png"))
    assert seguinte.paginas[0]["fonte"] == FONTE_OCR


def test_falha_de_ocr_afeta_apenas_a_pagina(tmp_path, pytesseract_falso):
    pytesseract_falso.erro = pytesseract_falso.TesseractError(1, "boom")
    extrator = Extrator(ParametrosExtracao())

    arquivo_a = _salvar_imagem(tmp_path / "a.png")
    falhou = extrator.extrair(arquivo_a)
    assert falhou.paginas == [{"pagina": 1, "texto": "", "fonte": FONTE_VAZIO}]
    assert falhou.n_ocr == 0
    assert falhou.n_sem_texto == 1

    pytesseract_falso.erro = None
    pytesseract_falso.resposta = "texto recuperado"
    arquivo_b = _salvar_imagem(tmp_path / "b.png")
    seguinte = extrator.extrair(arquivo_b)
    assert seguinte.paginas[0]["fonte"] == FONTE_OCR
    assert len(pytesseract_falso.chamadas) == 2


def test_tesseract_ausente_degrada_e_desativa_ocr(tmp_path, pytesseract_falso):
    pytesseract_falso.ausente()
    extrator = Extrator(ParametrosExtracao())

    arquivo_a = _salvar_imagem(tmp_path / "a.png")
    arquivo_b = _salvar_imagem(tmp_path / "b.png")
    primeira = extrator.extrair(arquivo_a)
    segunda = extrator.extrair(arquivo_b)

    assert primeira.paginas == [{"pagina": 1, "texto": "", "fonte": FONTE_VAZIO}]
    assert primeira.n_ocr == 0
    assert primeira.n_sem_texto == 1
    assert segunda.paginas[0]["fonte"] == FONTE_VAZIO
    assert len(pytesseract_falso.chamadas) == 1


def test_strict_levanta_erro_de_ocr(tmp_path, pytesseract_falso):
    pytesseract_falso.erro = pytesseract_falso.TesseractError(1, "boom")
    arquivo = _salvar_imagem(tmp_path / "a.png")

    with pytest.raises(ErroExtracao, match="falha de OCR") as info:
        Extrator(ParametrosExtracao(), strict=True).extrair(arquivo)
    assert isinstance(info.value.__cause__, pytesseract_falso.TesseractError)


def test_tiff_multiquadro_indexa_apenas_o_primeiro(tmp_path, pytesseract_falso):
    pytesseract_falso.resposta = "texto do primeiro quadro"
    caminho = tmp_path / "scan.tif"
    Image.new("RGB", (60, 30), "white").save(
        caminho, save_all=True, append_images=[Image.new("RGB", (60, 30), "black")]
    )

    resultado = Extrator(ParametrosExtracao()).extrair(caminho)

    assert resultado.n_paginas == 1
    assert resultado.paginas[0]["pagina"] == 1
    assert resultado.paginas[0]["fonte"] == FONTE_OCR
    assert len(pytesseract_falso.chamadas) == 1
    assert pytesseract_falso.chamadas[0].getpixel((0, 0)) == (255, 255, 255)


def test_ocr_de_pdf_rasteriza_e_devolve_texto(pytesseract_falso):
    pytesseract_falso.resposta = "texto do pdf"
    extrator = Extrator(ParametrosExtracao())
    pagina = _PaginaFalsa(png=_png_bytes())

    texto = extrator._ocr(pagina)

    assert texto == "texto do pdf"
    assert pagina.dpis == [200]
    assert pagina.formatos == ["png"]
    assert len(pytesseract_falso.chamadas) == 1
    assert isinstance(pytesseract_falso.chamadas[0], Image.Image)


def test_falha_ao_rasterizar_desativa_ocr(pytesseract_falso):
    pytesseract_falso.resposta = "texto"
    extrator = Extrator(ParametrosExtracao())
    pagina_valida = _PaginaFalsa(png=_png_bytes())

    assert extrator._ocr(_PaginaFalsa(erro=RuntimeError("boom"))) == ""
    assert len(pytesseract_falso.chamadas) == 0

    assert extrator._ocr(pagina_valida) == ""
    assert pagina_valida.n_pixmaps == 0
    assert len(pytesseract_falso.chamadas) == 0
