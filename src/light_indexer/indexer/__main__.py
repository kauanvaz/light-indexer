"""Ponto de entrada: ``python -m light_indexer.indexer``."""

import sys

from .cli import main

if __name__ == "__main__":
    sys.exit(main())
