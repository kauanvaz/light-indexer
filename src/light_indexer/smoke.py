"""Teste de fumaca do FTS5 (PRD 5.9, 12 - R6).

Confere que o SQLite embutido suporta FTS5 com o tokenizador e os prefixos do
esquema. Roda tanto no interpretador hospedeiro (build) quanto no executavel
empacotado (``LightIndexer --smoke-fts5``), validando o SQLite que sera distribuido.
Uma falha interrompe o build (PRD 5.9).
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from dataclasses import dataclass, field
from pathlib import Path

from . import schema

__all__ = ["ResultadoSmoke", "verificar_fts5", "main"]


@dataclass
class ResultadoSmoke:
    ok: bool = False
    mensagem: str = ""
    detalhes: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {"ok": self.ok, "mensagem": self.mensagem, "detalhes": self.detalhes}


def verificar_fts5() -> ResultadoSmoke:
    """Cria uma tabela FTS5 com o esquema real e valida tokenizador/prefixo."""
    detalhes: dict = {}
    try:
        con = sqlite3.connect(":memory:")
        try:
            detalhes["sqlite"] = sqlite3.sqlite_version
            con.execute(
                "CREATE VIRTUAL TABLE t USING fts5("
                f"texto, tokenize='{schema.TOKENIZER}', prefix='{schema.PREFIXOS}')"
            )
            con.executemany(
                "INSERT INTO t(texto) VALUES (?)",
                [("licitacao publica",), ("contrato de servico",)],
            )
            con.commit()
            detalhes["prefixo"] = con.execute(
                "SELECT count(*) FROM t WHERE t MATCH ?", ('"licit"*',)
            ).fetchone()[0]

            con.execute("DELETE FROM t")
            con.execute("INSERT INTO t(texto) VALUES ('licitação pública')")
            con.commit()
            detalhes["diacriticos"] = con.execute(
                "SELECT count(*) FROM t WHERE t MATCH ?", ('"licitacao"',)
            ).fetchone()[0]
            detalhes["integrity_check"] = con.execute(
                "PRAGMA integrity_check"
            ).fetchone()[0]
        finally:
            con.close()
    except sqlite3.Error as exc:
        return ResultadoSmoke(False, f"FTS5 indisponivel: {exc}", detalhes)

    ok = (
        detalhes.get("prefixo") == 1
        and detalhes.get("diacriticos") == 1
        and detalhes.get("integrity_check") == "ok"
    )
    mensagem = (
        "FTS5 disponivel (unicode61 remove_diacritics 2, prefixos 2 3 4)."
        if ok
        else "FTS5 respondeu de forma inesperada; build interrompido."
    )
    return ResultadoSmoke(ok, mensagem, detalhes)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="smoke_fts5")
    parser.add_argument(
        "--saida",
        type=Path,
        default=None,
        help="Grava o resultado em JSON (util quando nao ha console).",
    )
    args = parser.parse_args(argv)

    resultado = verificar_fts5()
    print(("OK " if resultado.ok else "FALHA ") + resultado.mensagem)
    if args.saida:
        args.saida.parent.mkdir(parents=True, exist_ok=True)
        args.saida.write_text(
            json.dumps(resultado.to_dict(), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    return 0 if resultado.ok else 1


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
