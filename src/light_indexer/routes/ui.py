"""Blueprint da interface estatica (PRD 7.1, 7.2).

Serve ``web/`` (``index.html``, ``css/``, ``js/`` e ``assets/``) sem CDN: todos
os recursos sao locais ao pacote. As rotas apenas entregam arquivos estaticos.
"""

from __future__ import annotations

from pathlib import Path

from flask import Blueprint, current_app, send_from_directory

bp = Blueprint("ui", __name__)


def _web_dir() -> Path:
    return (Path(current_app.config["ROOT"]) / "web").resolve()


@bp.get("/")
def index():
    return send_from_directory(_web_dir(), "index.html")


@bp.get("/css/<path:recurso>")
def css(recurso: str):
    return send_from_directory(_web_dir() / "css", recurso)


@bp.get("/js/<path:recurso>")
def js(recurso: str):
    return send_from_directory(_web_dir() / "js", recurso)


@bp.get("/assets/<path:recurso>")
def assets(recurso: str):
    return send_from_directory(_web_dir() / "assets", recurso)
