"""Registro dos blueprints (PRD 5.2, 7.1).

Um blueprint por recurso: ``ui`` (interface), ``search`` (busca), ``documents``
(entrega do original) e ``status`` (estado/versoes). As rotas sao camada fina:
apenas chamam o :class:`~light_indexer.search.service.SearchService`.
"""

from __future__ import annotations

from flask import Flask


def registrar(app: Flask) -> None:
    from . import documents, search, status, ui

    app.register_blueprint(ui.bp)
    app.register_blueprint(search.bp)
    app.register_blueprint(documents.bp)
    app.register_blueprint(status.bp)
