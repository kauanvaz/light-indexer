"""Script de build (PRD 5.9, 10.1).

Limpa, roda o teste de fumaca FTS5, empacota com PyInstaller
(``--onedir --noconsole``) e copia a interface e a configuracao para o pacote,
gerando ``version.json``. Interrompe se o FTS5 falhar (PRD 5.9, 12 - R6).

Ferramenta de build (Persona P2); nao faz parte do pacote portatil nem do
executavel de consulta.
"""

from __future__ import annotations

import argparse
import importlib.util
import os
import shutil
import subprocess
import sys
from pathlib import Path

from . import smoke, version

__all__ = [
    "NOME_EXE",
    "ENTRY",
    "RECURSOS",
    "montar_comando_pyinstaller",
    "limpar",
    "copiar_recursos",
    "build_main",
]

NOME_EXE = "LightIndexer"
ENTRY = Path("scripts") / "lightindexer.py"
RECURSOS = ("web", "config")


def _pyinstaller_disponivel() -> bool:
    return importlib.util.find_spec("PyInstaller") is not None


def montar_comando_pyinstaller(
    root: str | Path,
    *,
    destino: str | Path,
    work: str | Path,
    spec: str | Path,
    entry: str | Path | None = None,
    nome: str = NOME_EXE,
    contents: str = "app",
    noconsole: bool = True,
    paths: str | Path | None = None,
) -> list[str]:
    """Monta a linha de comando do PyInstaller (PRD 5.9, 5.10)."""
    root = Path(root)
    entry = Path(entry) if entry else root / ENTRY
    paths = Path(paths) if paths else root / "src"
    comando = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--onedir",
        "--name",
        nome,
        "--contents-directory",
        contents,
        "--distpath",
        str(destino),
        "--workpath",
        str(work),
        "--specpath",
        str(spec),
        "--paths",
        str(paths),
        "--collect-submodules",
        "waitress",
        "--hidden-import",
        "light_indexer.smoke",
        "--noconsole" if noconsole else "--console",
        str(entry),
    ]
    return comando


def limpar(*diretorios: str | Path) -> None:
    for diretorio in diretorios:
        shutil.rmtree(diretorio, ignore_errors=True)


def copiar_recursos(root: str | Path, destino: str | Path) -> list[str]:
    """Copia ``web/`` e ``config/`` para o pacote (PRD 5.9)."""
    root = Path(root)
    destino = Path(destino)
    copiados: list[str] = []
    for nome in RECURSOS:
        origem = root / nome
        if origem.is_dir():
            shutil.copytree(origem, destino / nome, dirs_exist_ok=True)
            copiados.append(nome)
    return copiados


def _nome_exe() -> str:
    return NOME_EXE + (".exe" if os.name == "nt" else "")


def _smoke_no_executavel(exe: Path, saida: Path) -> int:
    """Roda ``--smoke-fts5`` dentro do executavel empacotado (PRD 5.9)."""
    if not exe.is_file():
        return 0
    proc = subprocess.run(
        [str(exe), "--smoke-fts5", "--smoke-saida", str(saida)], check=False
    )
    return proc.returncode


def build_main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="build", description="Build do light-indexer (PRD 5.9)."
    )
    parser.add_argument("--root", type=Path, default=None)
    parser.add_argument("--destino", type=Path, default=None)
    parser.add_argument(
        "--sem-empacotar",
        action="store_true",
        help="Nao roda o PyInstaller (apenas smoke, recursos e version.json).",
    )
    parser.add_argument("--sem-smoke", action="store_true")
    parser.add_argument(
        "--console",
        action="store_true",
        help="Gera executavel com console (diagnostico).",
    )
    args = parser.parse_args(argv)

    from .paths import get_application_root

    root = Path(args.root) if args.root else get_application_root()
    destino = Path(args.destino) if args.destino else root / "build" / "dist"
    work = root / "build" / "pyinstaller"
    spec = work

    if not args.sem_smoke:
        resultado = smoke.verificar_fts5()
        print(("OK " if resultado.ok else "FALHA ") + resultado.mensagem)
        if not resultado.ok:
            return 1

    limpar(destino, work, spec)

    if not args.sem_empacotar:
        if not _pyinstaller_disponivel():
            print(
                "erro: PyInstaller nao instalado. "
                "Instale com 'uv sync --extra packaging'.",
                file=sys.stderr,
            )
            return 2
        comando = montar_comando_pyinstaller(
            root, destino=destino, work=work, spec=spec, noconsole=not args.console
        )
        codigo = subprocess.run(comando, check=False).returncode
        if codigo != 0:
            print(f"erro: PyInstaller falhou (codigo {codigo}).", file=sys.stderr)
            return codigo

    app_dir = destino / NOME_EXE
    app_dir.mkdir(parents=True, exist_ok=True)
    copiar_recursos(root, app_dir)
    version.gerar_version_json(app_dir / version.NOME_ARQUIVO, db_path=None)
    version.gerar_version_json(
        root / version.NOME_ARQUIVO, db_path=root / "build" / "indice.db"
    )

    if not args.sem_smoke:
        codigo = _smoke_no_executavel(app_dir / _nome_exe(), work / "smoke.json")
        if codigo != 0:
            print(
                "erro: o executavel empacotado falhou no teste de fumaca FTS5.",
                file=sys.stderr,
            )
            return codigo

    print(f"build concluido: {app_dir}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(build_main())
