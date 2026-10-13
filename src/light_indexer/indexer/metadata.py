"""Metadados de exibicao (PRD 5.5 etapa 4, 6.3 etapa 4).

Extrai/normaliza o titulo mostrado nos resultados. Na ausencia de metadado
confiavel, usa o nome do arquivo sem extensao.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

_TITULO_INVALIDO = re.compile(
    r"(tmp[0-9a-z]{4,}|\.html?$|microsoft word|untitled|documento\d*$)", re.IGNORECASE
)


def limpar_titulo(titulo: str | None) -> str:
    if not titulo:
        return ""
    t = re.sub(r"\s+", " ", titulo).strip()  # noqa: A001
    if len(t) < 3 or len(t) > 200:
        return ""
    if _TITULO_INVALIDO.search(t):
        return ""
    return t


def titulo_do_arquivo(caminho: Path) -> str:
    return caminho.stem.replace("_", " ").strip()


def extrair_titulo(caminho: Path) -> str:
    """Titulo do PDF se confiavel; senao o nome do arquivo."""
    caminho = Path(caminho)
    meta_titulo = ""
    if caminho.suffix.lower() == ".pdf":
        try:
            import pymupdf

            with pymupdf.open(str(caminho)) as doc:
                meta_titulo = limpar_titulo((doc.metadata or {}).get("title"))
        except Exception:
            meta_titulo = ""
    return meta_titulo or titulo_do_arquivo(caminho)


def catalogar(arquivos, logger=None) -> dict[str, str]:
    """Gera o mapa ``identificador -> titulo``."""
    catalogo: dict[str, str] = {}
    for arquivo in arquivos:
        catalogo[arquivo.identificador] = extrair_titulo(arquivo.caminho)
    if logger:
        logger.info("metadados: %d titulos", len(catalogo))
    return catalogo


def gravar_catalogo(catalogo: dict[str, str], caminho: Path) -> None:
    caminho = Path(caminho)
    caminho.parent.mkdir(parents=True, exist_ok=True)
    with caminho.open("w", encoding="utf-8") as fh:
        json.dump(catalogo, fh, ensure_ascii=False, indent=2, sort_keys=True)


def ler_catalogo(caminho: Path) -> dict[str, str]:
    caminho = Path(caminho)
    if not caminho.is_file():
        return {}
    with caminho.open("r", encoding="utf-8") as fh:
        return json.load(fh)
