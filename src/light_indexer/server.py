"""Aplicacao Flask e servidor waitress (PRD 5.2, 5.3, 5.4, 7.1, 5.11).

Flask e apenas camada fina de rotas sobre o ``SearchService``; o servidor de
producao e o waitress (nunca o servidor de desenvolvimento do Flask). Escuta
somente em ``127.0.0.1`` e rejeita cabecalho ``Host`` nao-local.
"""

from __future__ import annotations

import logging
from pathlib import Path

from flask import Flask, jsonify, request

from . import __version__, schema
from .config import Config
from .paths import caminho_config, caminho_db, diretorio_documentos, get_application_root
from .routes import registrar
from .search.normalize import MODO_PADRAO, Normalizador
from .search.service import SearchService

HOSTS_LOCAIS = {"127.0.0.1", "localhost", "::1"}

_LOG = logging.getLogger("light-indexer")


def _host_do_pedido(host: str) -> str:
    if host.startswith("["):
        return host[1:].split("]", 1)[0].lower()
    return host.split(":", 1)[0].lower()


def criar_servico(
    cfg: Config | None = None,
    root: Path | None = None,
    db_path: str | Path | None = None,
    docs_dir: str | Path | None = None,
) -> SearchService:
    """Monta o ``SearchService`` a partir da config e do indice."""
    root = Path(root) if root else get_application_root()
    cfg = cfg or Config.carregar(caminho_config(root))
    caminho = Path(db_path) if db_path else caminho_db(root)
    documentos = Path(docs_dir) if docs_dir else diretorio_documentos(root)

    modo = cfg.extras.get("modo_normalizacao", MODO_PADRAO)
    try:
        con = schema.abrir(str(caminho), somente_leitura=True)
        try:
            modo = schema.modo_normalizacao(con) or modo
        finally:
            con.close()
    except Exception:  # pragma: no cover - indice ausente cai no default
        _LOG.warning("indice indisponivel em %s; usando modo %s", caminho, modo)

    normalizador = Normalizador(modo=modo, max_termos=cfg.max_termos)
    return SearchService(
        caminho, documentos, normalizador=normalizador, cfg=cfg
    )


def criar_app(
    cfg: Config | None = None,
    root: Path | None = None,
    db_path: str | Path | None = None,
    docs_dir: str | Path | None = None,
    servico: SearchService | None = None,
) -> Flask:
    """Cria a aplicacao Flask com blueprints, guardas e servico injetados."""
    root = Path(root) if root else get_application_root()
    cfg = cfg or Config.carregar(caminho_config(root))
    servico = servico or criar_servico(cfg, root, db_path, docs_dir)

    app = Flask(__name__, static_folder=None)
    app.json.ensure_ascii = False
    app.config["ROOT"] = root
    app.config["CFG"] = cfg
    app.config["SERVICO"] = servico
    app.config["PORTA"] = cfg.porta_preferida

    registrar(app)
    _instalar_guardas(app)
    return app


def _instalar_guardas(app: Flask) -> None:
    @app.before_request
    def _somente_local():
        host = _host_do_pedido(request.host or "")
        if host and host not in HOSTS_LOCAIS:
            return jsonify({"erro": "acesso permitido apenas localmente"}), 403
        return None

    @app.after_request
    def _cabecalhos(resposta):
        resposta.headers["X-Content-Type-Options"] = "nosniff"
        resposta.headers["Referrer-Policy"] = "no-referrer"
        return resposta

    @app.errorhandler(404)
    def _nao_encontrado(_exc):
        if request.path.startswith("/api/"):
            return jsonify({"erro": "recurso nao encontrado"}), 404
        if request.path.startswith("/documentos/"):
            return "Documento nao encontrado. O link pode estar desatualizado.", 404, {
                "Content-Type": "text/plain; charset=utf-8"
            }
        return "Recurso nao encontrado.", 404, {
            "Content-Type": "text/plain; charset=utf-8"
        }

    @app.errorhandler(405)
    def _metodo_invalido(_exc):  # pragma: no cover - defensivo
        return jsonify({"erro": "metodo nao permitido"}), 405

    @app.errorhandler(500)
    def _erro_interno(exc):  # pragma: no cover - defensivo
        _LOG.exception("erro interno na API", exc_info=exc)
        return jsonify({"erro": "erro interno; consulte os logs"}), 500


def servir(
    app: Flask | None = None,
    host: str = "127.0.0.1",
    porta: int | None = None,
    threads: int = 4,
):
    """Inicia o servidor waitress (bloqueante)."""
    from waitress import create_server

    app = app or criar_app()
    porta = porta or int(app.config["PORTA"])
    _LOG.info("servidor em http://%s:%s (waitress)", host, porta)
    return create_server(
        app,
        host=host,
        port=porta,
        threads=threads,
        clear_untrusted_proxy_headers=True,
        ident="light-indexer",
    )


def main(argv: list[str] | None = None) -> int:  # pragma: no cover - entrada manual
    import argparse

    parser = argparse.ArgumentParser(prog="python -m light_indexer.server")
    parser.add_argument("--db", type=Path, default=None)
    parser.add_argument("--docs", type=Path, default=None)
    parser.add_argument("--root", type=Path, default=None)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--porta", type=int, default=None)
    parser.add_argument("--version", action="version", version=f"light-indexer {__version__}")
    args = parser.parse_args(argv)

    app = criar_app(root=args.root, db_path=args.db, docs_dir=args.docs)
    servir(app, host=args.host, porta=args.porta).run()
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
