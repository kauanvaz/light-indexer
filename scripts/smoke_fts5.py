#!/usr/bin/env python
"""Teste de fumaca FTS5 (PRD 5.9, 10.1 - R6).

Uso:
    python scripts/smoke_fts5.py [--saida build/smoke.json]
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from light_indexer.smoke import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
