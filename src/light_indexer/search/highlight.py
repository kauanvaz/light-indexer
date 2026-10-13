"""Destaque de trechos calculado pela aplicacao (PRD 5.7, 7.2).

O texto original e escapado antes de qualquer marcacao; apenas as palavras que
casam com a consulta recebem ``<mark>``. Nenhum HTML do acervo e interpretado,
o que elimina injecao. A janela exibida tem cerca de 180 caracteres e e
cortada em fronteiras de palavra, com reticencias quando ha truncamento.
"""

from __future__ import annotations

import html

from .normalize import WORD_RE, Normalizador

JANELA_PADRAO = 180


def _texto_limpo(texto: str, janela: int) -> str:
    recorte = texto[:janela].strip()
    escapado = html.escape(recorte)
    if len(texto) > janela:
        escapado += "…"
    return escapado


def destacar(
    texto: str | None,
    termos: list[str],
    normalizador: Normalizador,
    janela: int = JANELA_PADRAO,
) -> str:
    """Retorna o trecho relevante com as palavras da consulta em ``<mark>``."""
    if not texto:
        return ""
    if not termos:
        return _texto_limpo(texto, janela)

    tokens = list(WORD_RE.finditer(texto))
    if not tokens:
        return _texto_limpo(texto, janela)

    casa = [any(normalizador.casa(t, m.group(0)) for t in termos) for m in tokens]
    primeiro = next((i for i, marcado in enumerate(casa) if marcado), None)
    if primeiro is None:
        return _texto_limpo(texto, janela)

    lo = hi = primeiro
    comprimento = tokens[primeiro].end() - tokens[primeiro].start()
    while True:
        expandiu = False
        if lo > 0:
            tam = tokens[lo - 1].end() - tokens[lo - 1].start()
            if comprimento + tam + 1 <= janela:
                lo -= 1
                comprimento += tam + 1
                expandiu = True
        if hi < len(tokens) - 1:
            tam = tokens[hi + 1].end() - tokens[hi + 1].start()
            if comprimento + tam + 1 <= janela:
                hi += 1
                comprimento += tam + 1
                expandiu = True
        if not expandiu:
            break

    partes: list[str] = []
    if lo > 0:
        partes.append("…")
    pos = tokens[lo].start()
    for i in range(lo, hi + 1):
        token = tokens[i]
        if token.start() > pos:
            partes.append(html.escape(texto[pos : token.start()]))
        conteudo = html.escape(token.group(0))
        partes.append(f"<mark>{conteudo}</mark>" if casa[i] else conteudo)
        pos = token.end()
    if tokens[hi].end() < len(texto):
        partes.append("…")
    return "".join(partes)
