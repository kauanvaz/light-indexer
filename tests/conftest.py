"""Fixtures compartilhados pelos testes.

``pytesseract_falso`` instala um modulo pytesseract programavel em
``sys.modules``, permitindo testar o contrato de extracao de imagens sem o
binario do Tesseract (ambiente minimo de testes). As classes de excecao
espelham o pytesseract real: ``TesseractError(RuntimeError)`` recebe
``(status, message)`` e ``TesseractNotFoundError(EnvironmentError)`` nao
recebe argumentos - nao sao classe/subclasse entre si.
"""

from __future__ import annotations

import sys
import types

import pytest


class PytesseractFalso(types.ModuleType):
    """Modulo ``pytesseract`` falso com resposta/erro programaveis.

    Atributos: ``resposta`` (str devolvida), ``erro`` (instancia a levantar),
    ``chamadas`` (imagens recebidas) e ``idiomas`` (argumento ``lang`` de cada
    chamada).
    """

    def __init__(self) -> None:
        super().__init__("pytesseract")
        self.resposta = ""
        self.erro: Exception | None = None
        self.chamadas: list = []
        self.idiomas: list = []
        modulo = self

        class TesseractError(RuntimeError):
            """Falha generica do Tesseract (status + message)."""

            def __init__(self, status, message):
                self.status = status
                self.message = message
                self.args = (status, message)

        class TesseractNotFoundError(EnvironmentError):
            """Binario do Tesseract ausente. NAO e subclasse de TesseractError."""

            def __init__(self):
                super().__init__(
                    "tesseract is not installed or it's not in your PATH."
                )

        self.TesseractNotFoundError = TesseractNotFoundError
        self.TesseractError = TesseractError

        def image_to_string(imagem, lang=None):
            modulo.chamadas.append(imagem)
            modulo.idiomas.append(lang)
            imagem.load()
            if modulo.erro is not None:
                raise modulo.erro
            return modulo.resposta

        self.image_to_string = image_to_string

    def ausente(self) -> None:
        """Programa o erro de binario ausente."""
        self.erro = self.TesseractNotFoundError()


@pytest.fixture
def pytesseract_falso(monkeypatch) -> PytesseractFalso:
    modulo = PytesseractFalso()
    monkeypatch.setitem(sys.modules, "pytesseract", modulo)
    return modulo
