"""Script de release (PRD 5.9, 10.1 - UC7).

Copia o executavel empacotado, o indice e os documentos, valida o indice,
roda o teste de fumaca FTS5 e gera ``version.json``, produzindo o pacote
portatil pronto para copiar (PRD 5.10). Ferramenta de build (Persona P2).

Codigos de saida (PRD 6.7): 0 sucesso, 1 erro, 2 configuracao/estrutura,
3 falha de validacao.
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

from . import smoke, version
from .indexer.report import escrever_relatorio
from .indexer.validate import validar as validar_indice

__all__ = ["EXE_NOME", "copiar_conteudo", "montar_pacote", "release_main"]

EXE_NOME = "LightIndexer.exe"
RECURSOS = ("web", "config")

EXIT_OK = 0
EXIT_ERRO = 1
EXIT_CONFIG = 2
EXIT_VALIDACAO = 3


def copiar_conteudo(origem: str | Path, destino: str | Path) -> None:
    """Copia o conteudo de ``origem`` para ``destino``, mesclando pastas."""
    origem = Path(origem)
    destino = Path(destino)
    destino.mkdir(parents=True, exist_ok=True)
    for item in sorted(origem.iterdir()):
        alvo = destino / item.name
        if item.is_dir():
            shutil.copytree(item, alvo, dirs_exist_ok=True)
        else:
            shutil.copy2(item, alvo)


def montar_pacote(
    app_dir: str | Path,
    db_path: str | Path,
    acervo: str | Path,
    destino: str | Path,
    relatorio: str | Path,
    *,
    validar: bool = True,
    smoke_fts5: bool = True,
    prefixo: str = "documentos",
    recursos_origem: str | Path | None = None,
) -> tuple[int, dict]:
    """Monta o pacote portatil e devolve ``(codigo, resumo)``."""
    app_dir = Path(app_dir)
    db_path = Path(db_path)
    acervo = Path(acervo)
    destino = Path(destino)
    relatorio = Path(relatorio)

    if not app_dir.is_dir():
        raise FileNotFoundError(f"pacote do executavel ausente: {app_dir}")
    if not db_path.is_file():
        raise FileNotFoundError(f"indice ausente: {db_path}")
    if not acervo.is_dir():
        raise FileNotFoundError(f"acervo ausente: {acervo}")

    resumo: dict = {}
    copiar_conteudo(app_dir, destino)

    (destino / "data").mkdir(parents=True, exist_ok=True)
    shutil.copy2(db_path, destino / "data" / "indice.db")

    documentos = destino / "documentos"
    copiar_conteudo(acervo, documentos)

    if recursos_origem is not None:
        for nome in RECURSOS:
            if not (destino / nome).is_dir():
                origem = Path(recursos_origem) / nome
                if origem.is_dir():
                    shutil.copytree(origem, destino / nome, dirs_exist_ok=True)

    if validar:
        rel = validar_indice(destino / "data" / "indice.db", documentos, prefixo=prefixo)
        escrever_relatorio(rel, relatorio)
        resumo["validacao_ok"] = rel.ok
        resumo["pendencias"] = list(rel.pendencias)
        if not rel.ok:
            return EXIT_VALIDACAO, resumo

    if smoke_fts5:
        resultado = smoke.verificar_fts5()
        resumo["smoke_ok"] = resultado.ok
        if not resultado.ok:
            return EXIT_ERRO, resumo

    version.gerar_version_json(
        destino / version.NOME_ARQUIVO, db_path=destino / "data" / "indice.db"
    )
    resumo["destino"] = str(destino)
    return EXIT_OK, resumo


def release_main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="prepare-release", description="Monta o pacote portatil (PRD 5.9)."
    )
    parser.add_argument("--root", type=Path, default=None)
    parser.add_argument("--app", type=Path, default=None)
    parser.add_argument("--db", type=Path, default=None)
    parser.add_argument("--acervo", type=Path, default=None)
    parser.add_argument("--destino", type=Path, default=None)
    parser.add_argument("--relatorio", type=Path, default=None)
    parser.add_argument("--sem-validar", action="store_true")
    parser.add_argument("--sem-smoke", action="store_true")
    args = parser.parse_args(argv)

    from .paths import get_application_root

    root = Path(args.root) if args.root else get_application_root()
    app_dir = Path(args.app) if args.app else root / "build" / "dist" / "LightIndexer"
    db_path = Path(args.db) if args.db else root / "build" / "indice.db"
    acervo = Path(args.acervo) if args.acervo else root / "files"
    destino = Path(args.destino) if args.destino else root / "build" / "release"
    relatorio = (
        Path(args.relatorio) if args.relatorio else root / "build" / "relatorio.txt"
    )

    try:
        codigo, resumo = montar_pacote(
            app_dir,
            db_path,
            acervo,
            destino,
            relatorio,
            validar=not args.sem_validar,
            smoke_fts5=not args.sem_smoke,
            recursos_origem=root,
        )
    except FileNotFoundError as exc:
        print(f"erro: {exc}", file=sys.stderr)
        return EXIT_CONFIG

    if codigo == EXIT_OK:
        print(f"release concluido: {destino}")
    elif codigo == EXIT_VALIDACAO:
        print(
            "erro: relatorio de validacao com pendencias: "
            + "; ".join(resumo.get("pendencias", [])),
            file=sys.stderr,
        )
    else:
        print("erro: falha no teste de fumaca FTS5.", file=sys.stderr)
    return codigo


if __name__ == "__main__":  # pragma: no cover
    sys.exit(release_main())
