#!/usr/bin/env python
"""Build do pacote portatil (PRD 5.9, 10.1).

Uso:
    python scripts/build.py [--root .] [--destino build/dist] [--sem-empacotar]
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from light_indexer.build import build_main  # noqa: E402

if __name__ == "__main__":
    sys.exit(build_main())
