"""Inventario do acervo (PRD 5.5 etapa 1, 6.3 etapa 1).

Varre o acervo, atribui identificador estavel (caminho relativo com barras
normais) e calcula o hash de conteudo usado pelo cache de extracao.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .cache import hash_arquivo

EXTENSOES_IMAGEM = (".png", ".jpg", ".tiff", ".bmp", ".webp")

EXTENSOES_PADRAO = (".pdf", ".txt") + EXTENSOES_IMAGEM
PREFIXO_PADRAO = "documentos"


@dataclass(frozen=True)
class ArquivoAcervo:
    relativo: str
    prefixo: str
    identificador: str
    caminho: Path


def inventariar(
    acervo: Path,
    extensoes: tuple[str, ...] = EXTENSOES_PADRAO,
    prefixo: str = PREFIXO_PADRAO,
) -> list[ArquivoAcervo]:
    """Lista os arquivos do acervo em ordem deterministica."""
    acervo = Path(acervo)
    if not acervo.is_dir():
        raise NotADirectoryError(f"acervo inexistente: {acervo}")

    normalizadas = tuple(e.lower() for e in extensoes)
    itens: list[ArquivoAcervo] = []
    for caminho in sorted(acervo.rglob("*")):
        if not caminho.is_file():
            continue
        if normalizadas and caminho.suffix.lower() not in normalizadas:
            continue
        rel = caminho.relative_to(acervo).as_posix()
        ident = f"{prefixo}/{rel}" if prefixo else rel
        itens.append(
            ArquivoAcervo(
                relativo=rel,
                prefixo=prefixo,
                identificador=ident,
                caminho=caminho,
            )
        )
    return itens


def hash_de(arquivo: ArquivoAcervo) -> str:
    return hash_arquivo(arquivo.caminho)
