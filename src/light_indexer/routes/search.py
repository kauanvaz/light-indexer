"""Blueprint de busca (PRD 7.1 - GET /api/search).

Camada fina: valida parametros e delega ao ``SearchService``, que isola o SQL.
"""

from __future__ import annotations

from flask import Blueprint, current_app, jsonify, request

from ..search.service import BuscaTimeout, ConsultaInvalida

bp = Blueprint("search", __name__)


@bp.get("/api/search")
def api_search():
    servico = current_app.config["SERVICO"]
    q = request.args.get("q", "")
    page = request.args.get("page", 1)
    size = request.args.get("size")
    if size in ("", None):
        size = None
    try:
        resultado = servico.buscar(q, page=page, size=size)
    except ConsultaInvalida as exc:
        return jsonify({"erro": str(exc)}), 400
    except BuscaTimeout:
        return jsonify({"erro": "consulta excedeu o tempo limite"}), 400
    return jsonify(resultado)
