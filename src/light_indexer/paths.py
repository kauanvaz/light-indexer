"""Determinacao da raiz do pacote (PRD 5.2, 5.4, 5.10).

Uma unica funcao define a raiz; todo caminho deriva dela. Cobre tres modos:
desenvolvimento, executavel empacotado (PyInstaller --onedir) e o diretorio
temporario interno do PyInstaller (_MEIPASS) para o caso --onefile.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

ENV_ROOT = "LIGHT_INDEXER_ROOT"


def _marcador(p: Path) -> bool:
    """Diretorio que parece a raiz de um pacote/projeto."""
    return (p / "config" / "app.json").is_file() or (p / "pyproject.toml").is_file()


def get_application_root() -> Path:
    """Retorna a raiz do pacote, nunca derivando de ``__file__`` diretamente.

    Ordem: variavel de ambiente > executavel empacotado > `_MEIPASS` >
    subida a partir do modulo em busca de um marcador.
    """
    env = os.environ.get(ENV_ROOT)
    if env:
        return Path(env).expanduser().resolve()

    if getattr(sys, "frozen", False):
        exe_dir = Path(sys.executable).resolve().parent
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass and (Path(meipass) / "config" / "app.json").is_file():
            return exe_dir
        return exe_dir

    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        return Path(meipass).resolve()

    atual = Path(__file__).resolve()
    for pai in atual.parents:
        if _marcador(pai):
            return pai
    return atual.parents[2]


def caminho_config(root: Path | None = None) -> Path:
    root = root or get_application_root()
    return root / "config" / "app.json"


def caminho_db(root: Path | None = None) -> Path:
    env = os.environ.get("LIGHT_INDEXER_DB")
    if env:
        return Path(env).expanduser().resolve()
    root = root or get_application_root()
    return root / "data" / "indice.db"


def diretorio_logs(root: Path | None = None) -> Path:
    env = os.environ.get("LIGHT_INDEXER_LOG_DIR")
    if env:
        return Path(env).expanduser().resolve()
    root = root or get_application_root()
    return root / "logs"


def diretorio_documentos(root: Path | None = None) -> Path:
    """Diretorio do acervo distribuido (``documentos/``).

    Variavel de ambiente serve para desenvolvimento/teste; em producao o
    acervo fica sempre em ``<raiz>/documentos``.
    """
    env = os.environ.get("LIGHT_INDEXER_DOCS_DIR")
    if env:
        return Path(env).expanduser().resolve()
    root = root or get_application_root()
    return root / "documentos"


def diretorio_estado() -> Path:
    """Estado de runtime (porta/PID) fora da unidade: %LOCALAPPDATA%."""
    env = os.environ.get("LIGHT_INDEXER_STATE_DIR")
    if env:
        return Path(env).expanduser().resolve()
    base = os.environ.get("LOCALAPPDATA")
    if base:
        return (Path(base) / "light-indexer").resolve()
    return (Path.home() / ".light-indexer").resolve()
