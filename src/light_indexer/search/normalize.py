"""Normalizacao de texto e montagem segura de MATCH (PRD 5.7, 5.8).

Modulo compartilhado (leitura) entre indexador e aplicacao de consulta: o
mesmo tratamento tem de ser aplicado na indexacao e na busca. O runtime nao
importa o indexador; ambos importam este modulo.
"""

from __future__ import annotations

import re
import unicodedata
from collections import Counter

WORD_RE = re.compile(r"\w+", re.UNICODE)
_HIFEN_LINHA_RE = re.compile(r"(\w)-\s*\n\s*(\w)")
_ESPACOS_RE = re.compile(r"[ \t\u00a0]+")
_LINHAS_RE = re.compile(r"\n{2,}")

MODOS = ("prefixo", "stemming")
MODO_PADRAO = "prefixo"

_stemmer = None
_stemmer_indisponivel = False


def _carregar_stemmer():
    global _stemmer, _stemmer_indisponivel
    if _stemmer is not None or _stemmer_indisponivel:
        return _stemmer
    try:
        from nltk.stem import SnowballStemmer

        _stemmer = SnowballStemmer("portuguese")
    except Exception:  # pragma: no cover - depende do ambiente
        _stemmer_indisponivel = True
    return _stemmer


def remover_acentos(texto: str) -> str:
    nfd = unicodedata.normalize("NFKD", texto)
    return "".join(c for c in nfd if not unicodedata.combining(c))


def corrigir_hifenizacao(texto: str) -> str:
    """Junta palavras hifenizadas no fim da linha: ``lici-\\ntação`` -> ``licitação``."""
    return _HIFEN_LINHA_RE.sub(r"\1\2", texto)


def normalizar_texto(texto: str) -> str:
    """Minusculas, juncao de hifenizadas e espacos colapsados (PRD 5.8)."""
    if not texto:
        return ""
    t = texto.replace("\r\n", "\n").replace("\r", "\n")
    t = corrigir_hifenizacao(t)
    t = t.lower()
    t = _ESPACOS_RE.sub(" ", t)
    t = _LINHAS_RE.sub("\n", t)
    return t.strip()


def remover_cabecalho_rodape(
    paginas: list[str], limiar: float = 0.5, max_len: int = 80
) -> tuple[list[str], set[str]]:
    """Remove linhas repetidas em boa parte das paginas de um documento.

    Retorna as paginas limpas e o conjunto de linhas removidas.
    """
    if len(paginas) < 3:
        return list(paginas), set()

    contagem: Counter[str] = Counter()
    for texto in paginas:
        vistas = {
            ln.strip().lower()
            for ln in texto.splitlines()
            if ln.strip() and len(ln.strip()) <= max_len
        }
        contagem.update(vistas)

    minimo = max(2, int(len(paginas) * limiar))
    repetidas = {ln for ln, n in contagem.items() if n >= minimo}
    if not repetidas:
        return list(paginas), set()

    limpas: list[str] = []
    for texto in paginas:
        linhas = [
            ln for ln in texto.splitlines() if ln.strip().lower() not in repetidas
        ]
        limpas.append("\n".join(linhas))
    return limpas, repetidas


class Normalizador:
    """Aplica o modo de normalizacao (prefixo ou stemming) de forma coerente.

    Prefixo: ``texto_busca`` recebe o texto normalizado e o tokenizador FTS5
    remove acentos; a consulta acrescenta ``*`` a cada termo.
    Stemming: acentos sao removidos antes do radical e os mesmos radicais sao
    aplicados na indexacao e na consulta.
    """

    def __init__(self, modo: str = MODO_PADRAO, max_termos: int = 10) -> None:
        if modo not in MODOS:
            raise ValueError(f"modo invalido: {modo!r}; use {MODOS}")
        self.modo = modo
        self.max_termos = max_termos

    def _radical(self, termo: str) -> str:
        termo = remover_acentos(termo)
        stemmer = _carregar_stemmer()
        if stemmer is None:
            return termo
        return stemmer.stem(termo)

    def preparar_texto(self, texto: str) -> str:
        base = normalizar_texto(texto)
        if self.modo == "stemming":
            return " ".join(self._radical(t) for t in WORD_RE.findall(base))
        return base

    def termos(self, consulta: str | None) -> list[str]:
        if not consulta:
            return []
        return WORD_RE.findall(consulta.lower())[: self.max_termos]

    def casa(self, termo: str, token: str) -> bool:
        """Indica se um token do texto original casa com um termo da consulta.

        Usado no destaque de trechos (PRD 7.2) para marcar exatamente as
        palavras que o FTS5 considerou relevantes, aplicando o mesmo modo de
        normalizacao da indexacao.
        """
        t = remover_acentos((termo or "").lower())
        tok = remover_acentos((token or "").lower())
        if not t or not tok:
            return False
        if self.modo == "stemming":
            return self._radical(tok) == self._radical(t)
        return tok.startswith(t)

    def montar_match(self, consulta: str | None) -> str:
        """Monta a expressao MATCH segura: termos entre aspas, combinacao E."""
        partes: list[str] = []
        for termo in self.termos(consulta):
            if self.modo == "stemming":
                radical = self._radical(termo)
                if radical:
                    partes.append(f'"{radical}"')
            else:
                partes.append(f'"{termo}"*')
        return " AND ".join(partes)
