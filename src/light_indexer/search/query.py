"""Analise e montagem segura da consulta (PRD 5.7, 7.1).

O texto do usuario nunca vai direto ao FTS5: e dividido em termos, cada um
entre aspas, combinados por E, e passa pelo mesmo normalizador da indexacao.
Aqui tambem ficam os limites de tamanho da consulta e de numero de termos.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .normalize import Normalizador


class ConsultaInvalida(ValueError):
    """Consulta rejeitada por exceder um limite do servidor."""


@dataclass(frozen=True)
class Consulta:
    texto: str
    termos: list[str] = field(default_factory=list)
    match: str = ""

    @property
    def vazia(self) -> bool:
        """Consulta sem termos uteis (o MVP exige texto)."""
        return not self.match


def analisar(
    consulta: str | None,
    normalizador: Normalizador,
    max_len: int = 256,
) -> Consulta:
    """Valida a consulta e monta a expressao ``MATCH`` segura.

    Levanta :class:`ConsultaInvalida` se o texto exceder ``max_len``. O numero
    de termos e limitado pelo proprio :class:`Normalizador`.
    """
    texto = (consulta or "").strip()
    if len(texto) > max_len:
        raise ConsultaInvalida(f"consulta excede {max_len} caracteres")
    if not texto:
        return Consulta(texto="")
    return Consulta(
        texto=texto,
        termos=normalizador.termos(texto),
        match=normalizador.montar_match(texto),
    )
