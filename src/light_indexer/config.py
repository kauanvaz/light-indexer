"""Leitura de `config/app.json` com precedencia de variaveis de ambiente.

Tabelas de referencia: PRD 11.1 (chaves do arquivo) e 11.2 (variaveis).
Nenhuma chave contem segredo.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .paths import caminho_config, get_application_root

DEFAULTS: dict[str, Any] = {
    "porta_preferida": 8765,
    "tamanho_pagina": 20,
    "tamanho_pagina_max": 50,
    "abrir_navegador": True,
    "host": "127.0.0.1",
    "log_level": "INFO",
    "log_max_bytes": 1048576,
    "log_backup_count": 5,
    "max_termos": 10,
    "max_query_len": 256,
    "timeout_busca_ms": 5000,
    "cache_size": -8000,
    "mmap_size": 268435456,
}


@dataclass
class Config:
    porta_preferida: int = 8765
    tamanho_pagina: int = 20
    tamanho_pagina_max: int = 50
    abrir_navegador: bool = True
    host: str = "127.0.0.1"
    log_level: str = "INFO"
    log_max_bytes: int = 1048576
    log_backup_count: int = 5
    max_termos: int = 10
    max_query_len: int = 256
    timeout_busca_ms: int = 5000
    cache_size: int = -8000
    mmap_size: int = 268435456
    extras: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def carregar(cls, caminho: Path | None = None) -> "Config":
        dados: dict[str, Any] = dict(DEFAULTS)
        caminho = caminho or caminho_config(get_application_root())
        if caminho.is_file():
            with caminho.open("r", encoding="utf-8") as fh:
                dados.update(json.load(fh))
        cfg = cls(**{k: v for k, v in dados.items() if k in cls.__dataclass_fields__})
        cfg.extras = {k: v for k, v in dados.items() if k not in cls.__dataclass_fields__}
        cfg._aplicar_env()
        return cfg

    def _aplicar_env(self) -> None:
        if os.environ.get("LIGHT_INDEXER_PORT"):
            self.porta_preferida = int(os.environ["LIGHT_INDEXER_PORT"])
        if os.environ.get("LIGHT_INDEXER_HOST"):
            self.host = os.environ["LIGHT_INDEXER_HOST"]
        if os.environ.get("LIGHT_INDEXER_LOG_LEVEL"):
            self.log_level = os.environ["LIGHT_INDEXER_LOG_LEVEL"]

    def to_dict(self) -> dict[str, Any]:
        base = {k: getattr(self, k) for k in DEFAULTS}
        base.update(self.extras)
        return base
