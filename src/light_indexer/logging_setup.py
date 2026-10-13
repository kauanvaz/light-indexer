"""Logs com rotacao por tamanho e fallback fora da unidade (PRD 11.3).

Logs vao para ``logs/`` na unidade; se a unidade estiver protegida contra
escrita, caem para ``%LOCALAPPDATA%``.
"""

from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

from .config import Config
from .paths import diretorio_logs, diretorio_estado, get_application_root

_NOME = "light-indexer"


def _tentar_dir(diretorio: Path) -> Path | None:
    try:
        diretorio.mkdir(parents=True, exist_ok=True)
        teste = diretorio / ".escrita.tmp"
        teste.write_text("", encoding="utf-8")
        teste.unlink(missing_ok=True)
        return diretorio
    except OSError:
        return None


def configurar_logging(cfg: Config | None = None, nome: str = _NOME) -> logging.Logger:
    cfg = cfg or Config.carregar()
    logger = logging.getLogger(nome)
    if logger.handlers:
        return logger
    logger.setLevel(getattr(logging, str(cfg.log_level).upper(), logging.INFO))

    destino = _tentar_dir(diretorio_logs(get_application_root()))
    if destino is None:
        destino = _tentar_dir(diretorio_estado() / "logs")

    fmt = logging.Formatter(
        "%(asctime)s %(levelname)s %(name)s: %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
    )
    if destino is not None:
        handler: logging.Handler = RotatingFileHandler(
            destino / "light-indexer.log",
            maxBytes=cfg.log_max_bytes,
            backupCount=cfg.log_backup_count,
            encoding="utf-8",
        )
    else:
        handler = logging.StreamHandler()
    handler.setFormatter(fmt)
    logger.addHandler(handler)
    logger.propagate = False
    return logger
