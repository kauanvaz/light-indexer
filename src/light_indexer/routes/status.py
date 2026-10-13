"""Blueprint de estado (PRD 7.1 - GET /api/status)."""

from __future__ import annotations

from flask import Blueprint, current_app, jsonify

from .. import __version__

bp = Blueprint("status", __name__)


@bp.get("/api/status")
def api_status():
    servico = current_app.config["SERVICO"]
    dados = servico.status()
    resposta = {
        "status": "ok",
        "versao_app": __version__,
        "versao_esquema": dados["versao_esquema"],
        "versao_indice": dados["versao_indice"],
        "versao_acervo": dados["versao_acervo"],
        "documentos": dados["documentos"],
        "porta": current_app.config.get("PORTA"),
    }
    return jsonify(resposta)
