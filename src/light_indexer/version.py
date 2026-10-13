"""Geracao de ``version.json`` (PRD 5.9, 6.5, 7.1, 10.1).

Registra a versao do aplicativo, do esquema, do indice e do acervo, alem do
volume indexado. Serve ao suporte (Persona P3) para diagnostico sem acessar a
maquina (PRD 1.4, RNF10). Ferramenta de build/release, nao do runtime.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

from . import __version__, schema

__all__ = [
    "NOME_ARQUIVO",
    "coletar_versoes",
    "gerar_version_json",
    "ler_version_json",
]

NOME_ARQUIVO = "version.json"


def coletar_versoes(
    db_path: str | Path | None = None, app_version: str | None = None
) -> dict:
    """Reune as versoes de app/esquema/indice/acervo e o volume indexado.

    Sem indice informado (ou ausente), devolve as versoes do app e do esquema e
    deixa os campos do indice como ``None``.
    """
    dados: dict = {
        "versao_app": app_version or __version__,
        "versao_esquema": schema.VERSAO_ESQUEMA,
        "versao_indice": None,
        "versao_acervo": None,
        "documentos": None,
        "paginas": None,
    }
    if db_path is None:
        return dados

    caminho = Path(db_path)
    if not caminho.is_file():
        return dados

    con = schema.abrir(str(caminho), somente_leitura=True, imutavel=True)
    try:
        dados["versao_esquema"] = schema.versao_esquema(con)
        dados["versao_indice"] = schema.ler_meta(con, "versao_indice")
        dados["versao_acervo"] = schema.ler_meta(con, "versao_acervo")
        dados["documentos"] = con.execute(
            "SELECT COUNT(*) FROM documentos"
        ).fetchone()[0]
        dados["paginas"] = con.execute("SELECT COUNT(*) FROM paginas").fetchone()[0]
    finally:
        con.close()
    return dados


def gerar_version_json(
    destino: str | Path,
    db_path: str | Path | None = None,
    app_version: str | None = None,
    extras: dict | None = None,
) -> dict:
    """Escreve ``version.json`` e devolve o conteudo gravado."""
    dados = coletar_versoes(db_path, app_version)
    dados["gerado_em"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    if extras:
        dados.update(extras)
    destino = Path(destino)
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(
        json.dumps(dados, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return dados


def ler_version_json(caminho: str | Path) -> dict | None:
    caminho = Path(caminho)
    if not caminho.is_file():
        return None
    try:
        return json.loads(caminho.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
