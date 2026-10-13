#!/usr/bin/env python
"""Monta o pacote portatil de release (PRD 5.9, 10.1 - UC7).

Uso:
    python scripts/prepare-release.py [--app build/dist/LightIndexer] [--db build/indice.db]
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from light_indexer.release import release_main  # noqa: E402

if __name__ == "__main__":
    sys.exit(release_main())
