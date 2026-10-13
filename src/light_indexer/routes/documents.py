"""Blueprint de entrega do documento original (PRD 7.1, 7.3, UC3 - Sprint 4).

O caminho nunca vem do cliente: e resolvido pelo id no banco e verificado
contra a raiz do acervo (anti path traversal, PRD 5.11). A resposta usa
``send_file`` com ``conditional=True``, que implementa ``Range`` (``206``) e
``If-Range`` - essencial para PDFs grandes lidos de uma unidade USB. O arquivo
sai ``inline``, com o nome de download, para que o visualizador do navegador
abra direto no fragmento ``#page=N`` montado pela interface (PRD 7.2, UC3).

Falhas previsiveis - documento desconhecido, caminho invalido, arquivo ausente
ou ilegivel - viram mensagem amigavel com o caminho do log, nunca um traco de
pilha (PRD 11).
"""

from __future__ import annotations

import logging

from flask import Blueprint, current_app, send_file

from ..paths import diretorio_logs
from ..search.service import DocumentoNaoEncontrado

bp = Blueprint("documents", __name__)

_LOG = logging.getLogger("light-indexer")


def _erro(mensagem: str, codigo: int):
    return mensagem, codigo, {"Content-Type": "text/plain; charset=utf-8"}


def _caminho_log() -> str:
    """Caminho do log para orientar o usuario (PRD 11, RNF10)."""
    try:
        return str(diretorio_logs(current_app.config.get("ROOT")) / "light-indexer.log")
    except Exception:  # pragma: no cover - defensivo
        return "logs/light-indexer.log"


@bp.get("/documentos/<int:doc_id>")
def documento(doc_id: int):
    servico = current_app.config["SERVICO"]
    try:
        doc = servico.documento(doc_id)
    except DocumentoNaoEncontrado:
        _LOG.info("documento %s nao encontrado no indice", doc_id)
        return _erro(
            "Documento nao encontrado no indice. O link pode estar desatualizado.",
            404,
        )

    if not doc.caminho.is_file():
        _LOG.warning("arquivo ausente no acervo (doc %s): %s", doc_id, doc.caminho)
        return _erro(
            "Arquivo ausente no acervo. Verifique se a unidade esta conectada. "
            f"Registro: {_caminho_log()}",
            404,
        )

    try:
        resposta = send_file(
            doc.caminho,
            conditional=True,
            etag=False,
            max_age=0,
            download_name=doc.caminho.name,
            as_attachment=False,
        )
    except OSError as exc:
        _LOG.error("arquivo ilegivel (doc %s) %s: %s", doc_id, doc.caminho, exc)
        return _erro(
            "Nao foi possivel ler o arquivo (permissao negada ou unidade removida). "
            f"Registro: {_caminho_log()}",
            500,
        )

    resposta.headers["Accept-Ranges"] = "bytes"
    resposta.headers["Cache-Control"] = "no-store"
    return resposta
