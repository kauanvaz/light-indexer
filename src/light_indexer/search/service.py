"""SearchService: isola todo o SQL da aplicacao (PRD 5.2, 7.1, 11.3).

E a unica peca que conhece o motor de busca. As rotas nunca contem consulta;
trocar o motor (ex.: busca aproximada) nao toca na API nem na interface.
"""

from __future__ import annotations

import sqlite3
import time
from dataclasses import dataclass, field
from pathlib import Path

from .. import schema
from .highlight import destacar
from .normalize import MODO_PADRAO, Normalizador
from .query import Consulta, ConsultaInvalida, analisar

__all__ = [
    "SearchService",
    "ErroBusca",
    "BuscaTimeout",
    "DocumentoNaoEncontrado",
    "ConsultaInvalida",
    "ResultadoBusca",
    "Documento",
]


class ErroBusca(RuntimeError):
    """Falha ao executar a busca."""


class BuscaTimeout(ErroBusca):
    """A consulta excedeu o tempo maximo de execucao (PRD 11.1)."""


class DocumentoNaoEncontrado(LookupError):
    """Documento inexistente ou com caminho fora da raiz do acervo."""


@dataclass
class ResultadoBusca:
    total: int = 0
    page: int = 1
    size: int = 20
    results: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "total": self.total,
            "page": self.page,
            "size": self.size,
            "results": self.results,
        }


@dataclass
class Documento:
    doc_id: int
    arquivo: str
    titulo: str
    n_paginas: int | None
    caminho: Path


def _resolver_caminho(base: Path, relativo: str) -> Path:
    """Resolve ``relativo`` sob ``base`` e recusa qualquer escape (anti-traversal)."""
    rel = (relativo or "").strip()
    if not rel:
        raise DocumentoNaoEncontrado("registro sem caminho de arquivo")
    puro = Path(rel)
    if puro.is_absolute() or puro.drive:
        raise DocumentoNaoEncontrado(f"caminho invalido: {relativo}")
    base = base.resolve()
    candidato = (base / puro).resolve()
    if candidato != base and base not in candidato.parents:
        raise DocumentoNaoEncontrado(f"caminho fora da raiz: {relativo}")
    return candidato


class SearchService:
    def __init__(
        self,
        db_path: str | Path,
        docs_dir: str | Path,
        normalizador: Normalizador | None = None,
        prefixo: str = "documentos",
        cfg=None,
    ) -> None:
        self.db_path = str(db_path)
        self.docs_dir = Path(docs_dir)
        self.normalizador = normalizador or Normalizador(modo=MODO_PADRAO)
        self.prefixo = (prefixo or "").strip("/")
        self.cfg = cfg
        self.size_padrao = int(getattr(cfg, "tamanho_pagina", 20))
        self.size_max = int(getattr(cfg, "tamanho_pagina_max", 50))
        self.max_query_len = int(getattr(cfg, "max_query_len", 256))
        self.timeout_ms = int(getattr(cfg, "timeout_busca_ms", 5000))
        self._cache_size = int(getattr(cfg, "cache_size", -8000))
        self._mmap_size = int(getattr(cfg, "mmap_size", 268435456))

    def _abrir(self) -> sqlite3.Connection:
        con = schema.abrir(self.db_path, somente_leitura=True, imutavel=True)
        try:
            con.execute(f"PRAGMA cache_size={self._cache_size}")
            con.execute(f"PRAGMA mmap_size={self._mmap_size}")
        except sqlite3.OperationalError:  # pragma: no cover - tuning opcional
            pass
        return con

    def _instalar_timeout(self, con: sqlite3.Connection) -> None:
        if self.timeout_ms <= 0:
            return
        limite = time.monotonic() + self.timeout_ms / 1000.0

        def _vigia() -> int:
            return 1 if time.monotonic() > limite else 0

        con.set_progress_handler(_vigia, 10000)

    def limitar_size(self, size) -> int:
        if size is None:
            return min(self.size_padrao, self.size_max)
        try:
            valor = int(size)
        except (TypeError, ValueError) as exc:
            raise ConsultaInvalida("size invalido") from exc
        if valor < 1:
            raise ConsultaInvalida("size deve ser >= 1")
        return min(valor, self.size_max)

    def buscar(self, q: str | None, page: int = 1, size=None) -> dict:
        size = self.limitar_size(size)
        try:
            pagina = max(1, int(page))
        except (TypeError, ValueError):
            pagina = 1
        consulta = analisar(q, self.normalizador, self.max_query_len)
        resultado = ResultadoBusca(page=pagina, size=size)
        if consulta.vazia:
            return resultado.to_dict()

        con = self._abrir()
        try:
            self._instalar_timeout(con)
            try:
                total = con.execute(
                    "SELECT COUNT(*) FROM busca WHERE busca MATCH ?",
                    (consulta.match,),
                ).fetchone()[0]
                if total:
                    offset = (pagina - 1) * size
                    sql = (
                        "SELECT p.id AS pagina_id, p.pagina AS pagina, "
                        "p.texto AS texto, d.id AS doc_id, d.arquivo AS arquivo, "
                        "d.titulo AS titulo, bm25(busca) AS score "
                        "FROM busca "
                        "JOIN paginas p ON p.id = busca.rowid "
                        "JOIN documentos d ON d.id = p.doc_id "
                        "WHERE busca MATCH ? "
                        "ORDER BY score ASC, d.arquivo ASC, p.pagina ASC "
                        "LIMIT ? OFFSET ?"
                    )
                    linhas = con.execute(
                        sql, (consulta.match, size, offset)
                    ).fetchall()
                    resultado.results = [
                        self._montar_resultado(linha, consulta) for linha in linhas
                    ]
                resultado.total = total
            except sqlite3.OperationalError as exc:
                if "interrupt" in str(exc).lower():
                    raise BuscaTimeout("consulta excedeu o tempo limite") from exc
                raise ErroBusca(str(exc)) from exc
        finally:
            con.close()
        return resultado.to_dict()

    def _montar_resultado(self, linha: sqlite3.Row, consulta: Consulta) -> dict:
        return {
            "doc_id": linha["doc_id"],
            "titulo": linha["titulo"] or "",
            "arquivo": linha["arquivo"],
            "pagina": linha["pagina"],
            "score": round(-float(linha["score"]), 4),
            "trecho": destacar(
                linha["texto"], consulta.termos, self.normalizador
            ),
        }

    def documento(self, doc_id: int) -> Documento:
        con = self._abrir()
        try:
            linha = con.execute(
                "SELECT id, arquivo, titulo, n_paginas FROM documentos WHERE id=?",
                (doc_id,),
            ).fetchone()
        finally:
            con.close()
        if linha is None:
            raise DocumentoNaoEncontrado(f"documento {doc_id} nao encontrado")
        caminho = _resolver_caminho(
            self.docs_dir, self._relativo(linha["arquivo"])
        )
        return Documento(
            doc_id=linha["id"],
            arquivo=linha["arquivo"],
            titulo=linha["titulo"] or "",
            n_paginas=linha["n_paginas"],
            caminho=caminho,
        )

    def _relativo(self, arquivo: str | None) -> str:
        arq = (arquivo or "").replace("\\", "/").lstrip("/")
        if self.prefixo and arq.startswith(self.prefixo + "/"):
            arq = arq[len(self.prefixo) + 1 :]
        return arq

    def status(self) -> dict:
        con = self._abrir()
        try:
            return {
                "versao_esquema": schema.versao_esquema(con),
                "versao_indice": schema.ler_meta(con, "versao_indice"),
                "versao_acervo": schema.ler_meta(con, "versao_acervo"),
                "modo_normalizacao": schema.modo_normalizacao(con),
                "documentos": con.execute(
                    "SELECT COUNT(*) FROM documentos"
                ).fetchone()[0],
                "paginas": con.execute("SELECT COUNT(*) FROM paginas").fetchone()[0],
            }
        finally:
            con.close()
