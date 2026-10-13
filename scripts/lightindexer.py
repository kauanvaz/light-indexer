#!/usr/bin/env python
"""Ponto de entrada do executavel empacotado (PRD 5.9, 10.1).

Usado pelo PyInstaller como script de entrada do ``LightIndexer``. Importa o
lancador por caminho absoluto de pacote (o modulo ``__main__`` usa import
relativo e nao serve como entrada do PyInstaller).
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from light_indexer.launcher import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
