"""Avaliacao de variacoes de palavra e erros de OCR (PRD 5.8, Sprint 1).

Compara os modos ``prefixo`` e ``stemming`` sobre um arquivo de consultas
conhecidas e resume a taxa de acerto. O formato do arquivo e uma consulta por
linha, separada do(s) documento(s) esperado(s) por TAB; varios esperados sao
separados por ``|``. Linhas em branco e iniciadas por ``#`` sao ignoradas.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from pathlib import Path

from .cache import ResultadoExtracao
from .inventory import ArquivoAcervo
from .load import construir
from ..search.normalize import Normalizador


@dataclass
class ConsultaAvaliada:
    consulta: str
    esperados: list[str]
    acertos: list[str] = field(default_factory=list)
    primeiro_ranking: int | None = None
    n_resultados: int = 0

    @property
    def ok(self) -> bool:
        if self.esperados:
            return bool(self.acertos)
        return self.n_resultados > 0


@dataclass
class ResultadoModo:
    modo: str
    consultas: list[ConsultaAvaliada]

    @property
    def total(self) -> int:
        return len(self.consultas)

    @property
    def acertos(self) -> int:
        return sum(1 for c in self.consultas if c.ok)

    @property
    def taxa(self) -> float:
        return (self.acertos / self.total) if self.total else 0.0


def ler_consultas(caminho: Path) -> list[tuple[str, list[str]]]:
    caminho = Path(caminho)
    consultas: list[tuple[str, list[str]]] = []
    with caminho.open("r", encoding="utf-8") as fh:
        for linha in fh:
            linha = linha.strip()
            if not linha or linha.startswith("#"):
                continue
            if "\t" in linha:
                termo, esperados = linha.split("\t", 1)
            else:
                termo, esperados = linha, ""
            esperados_lista = [e.strip() for e in esperados.split("|") if e.strip()]
            consultas.append((termo.strip(), esperados_lista))
    return consultas


def _casa(arquivo: str, esperado: str) -> bool:
    arq = arquivo.replace("\\", "/").lower()
    esp = esperado.replace("\\", "/").strip().lower()
    return bool(esp) and (esp in arq or Path(arq).name == Path(esp).name)


def _executar_consultas(
    conn: sqlite3.Connection,
    normalizador: Normalizador,
    consultas: list[tuple[str, list[str]]],
    limite: int = 100,
) -> list[ConsultaAvaliada]:
    resultado: list[ConsultaAvaliada] = []
    sql = (
        "SELECT d.arquivo FROM busca "
        "JOIN paginas p ON p.id = busca.rowid "
        "JOIN documentos d ON d.id = p.doc_id "
        "WHERE busca MATCH ? ORDER BY bm25(busca) LIMIT ?"
    )
    for termo, esperados in consultas:
        avaliada = ConsultaAvaliada(consulta=termo, esperados=esperados)
        match = normalizador.montar_match(termo)
        if match:
            try:
                linhas = conn.execute(sql, (match, limite)).fetchall()
            except sqlite3.OperationalError:
                linhas = []
            avaliada.n_resultados = len(linhas)
            for pos, row in enumerate(linhas, start=1):
                arquivo = row[0]
                for esperado in esperados:
                    if _casa(arquivo, esperado):
                        if esperado not in avaliada.acertos:
                            avaliada.acertos.append(esperado)
                        if avaliada.primeiro_ranking is None:
                            avaliada.primeiro_ranking = pos
        resultado.append(avaliada)
    return resultado


def avaliar(
    entradas: list[tuple[ArquivoAcervo, ResultadoExtracao]],
    consultas: list[tuple[str, list[str]]],
    modos: tuple[str, ...] = ("prefixo", "stemming"),
    titulos: dict[str, str] | None = None,
    max_termos: int = 10,
    destino: Path | None = None,
) -> dict[str, ResultadoModo]:
    """Constroi um indice por modo e mede a taxa de acerto das consultas."""
    destino = Path(destino) if destino else Path("build")
    destino.mkdir(parents=True, exist_ok=True)
    saida: dict[str, ResultadoModo] = {}
    for modo in modos:
        normalizador = Normalizador(modo=modo, max_termos=max_termos)
        db_modo = destino / f"avaliacao-{modo}.db"
        for sufixo in ("", "-wal", "-shm"):
            Path(str(db_modo) + sufixo).unlink(missing_ok=True)
        construir(str(db_modo), entradas, normalizador, titulos)
        conn = sqlite3.connect(str(db_modo))
        try:
            consultas_aval = _executar_consultas(
                conn, normalizador, consultas
            )
        finally:
            conn.close()
        Path(db_modo).unlink(missing_ok=True)
        saida[modo] = ResultadoModo(modo=modo, consultas=consultas_aval)
    return saida


def formatar(resultados: dict[str, ResultadoModo], erros_ocr: tuple[int, int] = (0, 0)) -> str:
    linhas: list[str] = ["Avaliacao de variacoes de palavra", ""]
    for modo, res in resultados.items():
        linhas.append(
            f"[{modo}] acertos: {res.acertos}/{res.total} "
            f"({res.taxa * 100:.1f}%)"
        )
        for c in res.consultas:
            marca = "OK " if c.ok else "ERRO"
            rank = f" rank={c.primeiro_ranking}" if c.primeiro_ranking else ""
            linhas.append(
                f"  {marca} {c.consulta!r}{rank} - {c.n_resultados} resultados"
            )
        linhas.append("")
    ocr, sem_texto = erros_ocr
    linhas.append(f"Paginas com OCR: {ocr}")
    linhas.append(f"Paginas sem texto apos OCR: {sem_texto}")
    return "\n".join(linhas) + "\n"
