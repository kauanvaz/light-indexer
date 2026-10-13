#!/usr/bin/env python
"""Wrapper do script de indexacao (PRD secao 6.2 / 10.1).

Uso:
    python scripts/index.py <comando> [opcoes]
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from light_indexer.indexer.cli import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
