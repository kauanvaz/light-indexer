"""CLI do script de indexacao (PRD secao 6.2).

Uso::

    python -m light_indexer.indexer <comando> [opcoes]

Comandos: inventory, extract, metadata, load, validate, build, status,
evaluate. Ferramenta tecnica (Persona P2): nao faz parte do pacote portatil.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from ..config import Config
from ..logging_setup import configurar_logging
from ..paths import get_application_root
from . import cache as cache_mod
from . import evaluate as evaluate_mod
from . import inventory as inventory_mod
from . import metadata as metadata_mod
from . import report as report_mod
from . import validate as validate_mod
from .extract import Extrator, ParametrosExtracao, processar_arquivos
from .load import construir
from ..search.normalize import Normalizador

COMANDOS = {
    "inventory": "Inventaria o acervo (caminho relativo + id estavel)",
    "extract": "Extrai texto nativo e roda OCR nas paginas sem texto",
    "metadata": "Extrai/normaliza metadados de exibicao (titulo etc.)",
    "load": "Normaliza, carrega tabelas e constroi o FTS5",
    "validate": "Gera o relatorio de validacao",
    "build": "Pipeline completo: inventory->extract->metadata->load->validate",
    "status": "Mostra progresso do cache e do indice parcial",
    "evaluate": "Compara prefixo vs stemming em consultas conhecidas",
}

EXIT_OK = 0
EXIT_ERRO = 1
EXIT_CONFIG = 2
EXIT_VALIDACAO = 3
EXIT_PARCIAL = 4


def _parser_global() -> argparse.ArgumentParser:
    g = argparse.ArgumentParser(add_help=False)
    g.add_argument("--acervo", type=Path, default=None, help="Diretorio dos documentos originais")
    g.add_argument("--cache", type=Path, default=None, help="Diretorio do cache (default build/cache)")
    g.add_argument("--db", type=Path, default=None, help="Indice de saida (default build/indice.db)")
    g.add_argument("--config", type=Path, default=None, help="Configuracao (default config/app.json)")
    g.add_argument("--workers", type=int, default=os.cpu_count() or 1, help="Paralelismo")
    g.add_argument("--ocr-lang", default="por", help="Idioma do OCR")
    g.add_argument(
        "--modo", choices=("prefixo", "stemming"), default=None,
        help="Normalizacao: prefixo (default) ou stemming",
    )
    g.add_argument("--prefixo", default="documentos", help="Prefixo do caminho no pacote")
    g.add_argument("--dpi", type=int, default=200, help="DPI do raster para OCR")
    g.add_argument("--min-chars", type=int, default=20, help="Minimo de chars para considerar texto nativo")
    g.add_argument("--sample", type=int, default=None, help="Limita a N paginas")
    g.add_argument("--queries", type=Path, default=None, help="Arquivo de consultas conhecidas")
    g.add_argument("--resume", dest="resume", action="store_true", default=True)
    g.add_argument("--no-resume", dest="resume", action="store_false")
    g.add_argument("--force", action="store_true", help="Ignora o cache e reprocessa")
    g.add_argument("--strict", action="store_true", help="Trata falhas de OCR como erro")
    g.add_argument("--verbose", action="store_true", help="Log detalhado")
    return g


def construir_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m light_indexer.indexer",
        description="Script de indexacao do light-indexer (ferramenta tecnica).",
    )
    parser.add_argument("--version", action="version", version="light-indexer indexer")
    sub = parser.add_subparsers(dest="comando", metavar="comando")
    globais = _parser_global()
    for nome, ajuda in COMANDOS.items():
        sub.add_parser(nome, parents=[globais], help=ajuda)
    return parser


def _resolver(args, root: Path) -> None:
    args._root = root
    if args.cache is None:
        args.cache = root / "build" / "cache"
    if args.db is None:
        args.db = root / "build" / "indice.db"
    if args.config is None:
        args.config = root / "config" / "app.json"
    if args.modo is None:
        args.modo = "prefixo"


def _exigir_acervo(args, parser) -> bool:
    if args.acervo is None:
        print("erro: --acervo e obrigatorio", file=sys.stderr)
        return False
    if not Path(args.acervo).is_dir():
        print(f"erro: acervo inexistente: {args.acervo}", file=sys.stderr)
        return False
    return True


def _normalizador(args, cfg) -> Normalizador:
    return Normalizador(modo=args.modo, max_termos=cfg.max_termos)


def _parametros(args) -> ParametrosExtracao:
    return ParametrosExtracao(ocr_lang=args.ocr_lang, dpi=args.dpi, min_chars=args.min_chars)


def _cache(args) -> cache_mod.CacheExtracao:
    return cache_mod.CacheExtracao.criar(args.cache)


def _catalogo(args) -> dict[str, str]:
    caminho = Path(args.cache) / "metadados.json"
    catalogo = metadata_mod.ler_catalogo(caminho)
    if catalogo:
        return catalogo
    arquivos = inventory_mod.inventariar(Path(args.acervo), prefixo=args.prefixo)
    return metadata_mod.catalogar(arquivos)


def cmd_inventory(args, parser, cfg, logger) -> int:
    if not _exigir_acervo(args, parser):
        return EXIT_CONFIG
    arquivos = inventory_mod.inventariar(Path(args.acervo), prefixo=args.prefixo)
    for a in arquivos:
        print(a.identificador)
    print(f"Total: {len(arquivos)} arquivos")
    return EXIT_OK


def cmd_extract(args, parser, cfg, logger) -> int:
    if not _exigir_acervo(args, parser):
        return EXIT_CONFIG
    arquivos = inventory_mod.inventariar(Path(args.acervo), prefixo=args.prefixo)
    cache = _cache(args)
    extrator = Extrator(_parametros(args), strict=args.strict, logger=logger)
    entradas, falhas = processar_arquivos(
        arquivos, cache, _parametros(args), extrator,
        resume=args.resume, force=args.force, workers=args.workers,
        sample=args.sample, logger=logger,
    )
    paginas = sum(r.n_paginas for _, r in entradas)
    print(f"Extraidos: {len(entradas)} arquivos, {paginas} paginas, {falhas} falhas")
    cache.fechar()
    if falhas and args.strict:
        return EXIT_PARCIAL
    return EXIT_OK


def cmd_metadata(args, parser, cfg, logger) -> int:
    if not _exigir_acervo(args, parser):
        return EXIT_CONFIG
    arquivos = inventory_mod.inventariar(Path(args.acervo), prefixo=args.prefixo)
    catalogo = metadata_mod.catalogar(arquivos, logger=logger)
    destino = Path(args.cache) / "metadados.json"
    metadata_mod.gravar_catalogo(catalogo, destino)
    print(f"Metadados: {len(catalogo)} titulos -> {destino}")
    return EXIT_OK


def _extrair_para_load(args, logger):
    if not _exigir_acervo(args, None):
        return None
    arquivos = inventory_mod.inventariar(Path(args.acervo), prefixo=args.prefixo)
    cache = _cache(args)
    extrator = Extrator(_parametros(args), strict=args.strict, logger=logger)
    entradas, falhas = processar_arquivos(
        arquivos, cache, _parametros(args), extrator,
        resume=args.resume, force=args.force, workers=args.workers,
        sample=args.sample, logger=logger,
    )
    return cache, entradas, falhas


def cmd_load(args, parser, cfg, logger) -> int:
    if not _exigir_acervo(args, parser):
        return EXIT_CONFIG
    cache, entradas, falhas = _extrair_para_load(args, logger) or (None, None, 0)
    if entradas is None:
        return EXIT_CONFIG
    normalizador = _normalizador(args, cfg)
    stats = construir(
        str(args.db), entradas, normalizador, _catalogo(args),
        versao_acervo=cfg.extras.get("versao_acervo"),
    )
    print(
        f"Carga: {stats.documentos} documentos, {stats.paginas} paginas "
        f"({stats.paginas_ocr} OCR) -> {args.db}"
    )
    cache.fechar()
    return EXIT_PARCIAL if (falhas and args.strict) else EXIT_OK


def cmd_validate(args, parser, cfg, logger) -> int:
    if not _exigir_acervo(args, parser):
        return EXIT_CONFIG
    cache = _cache(args)
    rel = validate_mod.validar(args.db, Path(args.acervo), prefixo=args.prefixo, cache=cache)
    cache.fechar()
    texto = rel.texto()
    print(texto)
    report_mod.escrever_relatorio(rel, Path(args._root) / "build" / "relatorio.txt")
    return EXIT_OK if rel.ok else EXIT_VALIDACAO


def cmd_build(args, parser, cfg, logger) -> int:
    if not _exigir_acervo(args, parser):
        return EXIT_CONFIG
    cache, entradas, falhas = _extrair_para_load(args, logger) or (None, None, 0)
    if entradas is None:
        return EXIT_CONFIG
    normalizador = _normalizador(args, cfg)
    titulos = metadata_mod.catalogar(
        [a for a, _ in entradas], logger=logger
    )
    metadata_mod.gravar_catalogo(titulos, Path(args.cache) / "metadados.json")
    stats = construir(
        str(args.db), entradas, normalizador, titulos,
        versao_acervo=cfg.extras.get("versao_acervo"),
    )
    print(
        f"Carga: {stats.documentos} documentos, {stats.paginas} paginas "
        f"({stats.paginas_ocr} OCR)"
    )
    esperados = (
        {a.identificador for a, _ in entradas} if args.sample is not None else None
    )
    rel = validate_mod.validar(
        args.db, Path(args.acervo), prefixo=args.prefixo, cache=cache, esperados=esperados
    )
    cache.fechar()
    texto = rel.texto()
    print(texto)
    report_mod.escrever_relatorio(rel, Path(args._root) / "build" / "relatorio.txt")
    if falhas and args.strict:
        return EXIT_PARCIAL
    return EXIT_OK if rel.ok else EXIT_VALIDACAO


def cmd_status(args, parser, cfg, logger) -> int:
    cache = _cache(args)
    n_arq = cache.contar()
    n_pag, n_ocr, n_sem = cache.total_paginas()
    print(f"Cache: {n_arq} arquivos, {n_pag} paginas ({n_ocr} OCR, {n_sem} sem texto)")
    cache.fechar()
    if Path(args.db).is_file():
        from .. import schema

        conn = schema.abrir(str(args.db), somente_leitura=True)
        try:
            docs = conn.execute("SELECT COUNT(*) FROM documentos").fetchone()[0]
            pags = conn.execute("SELECT COUNT(*) FROM paginas").fetchone()[0]
            print(f"Indice: {docs} documentos, {pags} paginas, modo={schema.modo_normalizacao(conn)}")
        finally:
            conn.close()
    else:
        print(f"Indice: ausente ({args.db})")
    return EXIT_OK


def cmd_evaluate(args, parser, cfg, logger) -> int:
    if not _exigir_acervo(args, parser):
        return EXIT_CONFIG
    if args.queries is None or not Path(args.queries).is_file():
        print("erro: --queries aponta para arquivo inexistente", file=sys.stderr)
        return EXIT_CONFIG
    cache, entradas, falhas = _extrair_para_load(args, logger) or (None, None, 0)
    if entradas is None:
        return EXIT_CONFIG
    consultas = evaluate_mod.ler_consultas(args.queries)
    resultados = evaluate_mod.avaliar(
        entradas, consultas, titulos=_catalogo(args),
        max_termos=cfg.max_termos, destino=Path(args._root) / "build",
    )
    _, ocr, sem_texto = cache.total_paginas()
    cache.fechar()
    texto = evaluate_mod.formatar(resultados, (ocr, sem_texto))
    print(texto)
    destino = Path(args._root) / "build" / "avaliacao.txt"
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(texto, encoding="utf-8")
    return EXIT_OK


HANDLERS = {
    "inventory": cmd_inventory,
    "extract": cmd_extract,
    "metadata": cmd_metadata,
    "load": cmd_load,
    "validate": cmd_validate,
    "build": cmd_build,
    "status": cmd_status,
    "evaluate": cmd_evaluate,
}


def main(argv: list[str] | None = None) -> int:
    parser = construir_parser()
    args = parser.parse_args(argv)
    if not args.comando:
        parser.print_help()
        return EXIT_CONFIG
    root = get_application_root()
    _resolver(args, root)
    cfg = Config.carregar(args.config)
    if args.verbose:
        cfg.log_level = "DEBUG"
    logger = configurar_logging(cfg)
    try:
        return HANDLERS[args.comando](args, parser, cfg, logger)
    except KeyboardInterrupt:  # pragma: no cover
        print("interrompido", file=sys.stderr)
        return EXIT_ERRO
    except (NotADirectoryError, ValueError) as exc:
        print(f"erro: {exc}", file=sys.stderr)
        return EXIT_CONFIG
    except Exception as exc:  # pragma: no cover - defensivo
        logger.exception("erro inesperado")
        print(f"erro: {exc}", file=sys.stderr)
        return EXIT_ERRO


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
