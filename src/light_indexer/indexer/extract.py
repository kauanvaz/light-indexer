"""Extracao de texto nativo e OCR por pagina, com cache retomavel.

Etapas 2-3 do pipeline (PRD 5.5, 5.8, 6.3). OCR roda apenas nas paginas sem
texto nativo, detectadas pagina a pagina. A extracao e paralelizavel e
retomavel por arquivo.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path

from .cache import CacheExtracao, ResultadoExtracao, chave_cache, hash_arquivo
from .inventory import EXTENSOES_IMAGEM, ArquivoAcervo

from PIL.ImageFile import ImageFile
from io import BytesIO

FONTE_NATIVO = "nativo"
FONTE_OCR = "ocr"
FONTE_VAZIO = "sem_texto"


class ErroExtracao(Exception):
    """Falha ao abrir/ler um arquivo do acervo."""


@dataclass(frozen=True)
class ParametrosExtracao:
    ocr_lang: str = "por"
    dpi: int = 200
    min_chars: int = 20

    def chave(self) -> str:
        return f"lang={self.ocr_lang};dpi={self.dpi};min={self.min_chars}"


class Extrator:
    """Extrai texto de um arquivo. Importa as dependencias sob demanda."""

    def __init__(
        self,
        parametros: ParametrosExtracao | None = None,
        strict: bool = False,
        logger=None,
    ) -> None:
        self.params = parametros or ParametrosExtracao()
        self.strict = strict
        self.logger = logger
        self._tesseract_indisponivel = False

    def _aviso(self, msg: str, *args) -> None:
        if self.logger:
            self.logger.warning(msg, *args)

    def extrair(self, caminho: Path) -> ResultadoExtracao:
        caminho = Path(caminho)
        try:
            suffix = caminho.suffix.lower()
            if suffix == ".pdf":
                return self._extrair_pdf(caminho)
            if suffix in EXTENSOES_IMAGEM:
                return self._extrair_imagem(caminho)
            return self._extrair_texto(caminho)
        except ErroExtracao:
            raise
        except Exception as exc:  # pragma: no cover - defensivo
            raise ErroExtracao(f"falha ao extrair {caminho}: {exc}") from exc

    def _extrair_pdf(self, caminho: Path) -> ResultadoExtracao:
        try:
            import pymupdf
        except ImportError as exc:  # pragma: no cover
            raise ErroExtracao("pymupdf nao instalado (uv sync --extra build)") from exc

        try:
            doc = pymupdf.open(str(caminho))
        except Exception as exc:
            raise ErroExtracao(f"PDF invalido: {caminho}") from exc

        paginas: list[dict] = []
        n_ocr = 0
        n_sem = 0
        try:
            import io

            for i in range(doc.page_count):
                page = doc.load_page(i)
                texto = page.get_text("text") or ""
                fonte = FONTE_NATIVO
                if len(texto.strip()) < self.params.min_chars:

                    pix = page.get_pixmap(dpi=self.params.dpi)
                    buffer = io.BytesIO(pix.tobytes("png"))

                    texto_ocr = self._ocr(buffer)
                    if texto_ocr.strip():
                        texto = texto_ocr
                        fonte = FONTE_OCR
                        n_ocr += 1
                    else:
                        fonte = FONTE_VAZIO
                        n_sem += 1
                paginas.append({"pagina": i + 1, "texto": texto, "fonte": fonte})
        finally:
            doc.close()
        return ResultadoExtracao(paginas=paginas, n_ocr=n_ocr, n_sem_texto=n_sem)

    def _ocr(self, obj) -> str:
        if self._tesseract_indisponivel:
            return ""

        try:
            from PIL import Image, ImageOps
            import pytesseract
        except ImportError as exc:  # pragma: no cover
            raise ErroExtracao("pacotes requeridos nao instalados (uv sync --extra build)") from exc
        
        try:
            imagem = Image.open(obj)

            imagem_processada = ImageOps.autocontrast(ImageOps.grayscale(imagem)) 

            return pytesseract.image_to_string(imagem_processada, lang=self.params.ocr_lang)
        except Exception as exc:
            if self.strict:
                raise ErroExtracao(f"falha de OCR: {exc}") from exc
            self._tesseract_indisponivel = True
            self._aviso("OCR indisponivel (%s); paginas sem texto ficam vazias", exc)
            return ""

    def _extrair_imagem(self, caminho: Path) -> ResultadoExtracao:
        texto = self._ocr(caminho)

        return ResultadoExtracao(
            paginas=[{"pagina": 1, "texto": texto, "fonte": FONTE_OCR}],
            n_ocr=1,
            n_sem_texto= 0 if texto.strip() else 1
        )

    def _extrair_texto(self, caminho: Path) -> ResultadoExtracao:
        bruto = caminho.read_bytes()
        try:
            texto = bruto.decode("utf-8")
        except UnicodeDecodeError:
            texto = bruto.decode("latin-1", errors="replace")
        fonte = FONTE_NATIVO if texto.strip() else FONTE_VAZIO
        n_sem = 0 if texto.strip() else 1
        return ResultadoExtracao(
            paginas=[{"pagina": 1, "texto": texto, "fonte": fonte}],
            n_ocr=0,
            n_sem_texto=n_sem,
        )


def _processar_um(
    arquivo: ArquivoAcervo,
    cache: CacheExtracao,
    params: ParametrosExtracao,
    extrator: Extrator,
    resume: bool,
    force: bool,
) -> tuple[ArquivoAcervo, ResultadoExtracao, bool]:
    h = hash_arquivo(arquivo.caminho)
    chave = chave_cache(h, params.chave())
    if resume and not force:
        resultado = cache.obter(chave)
        if resultado is not None:
            return arquivo, resultado, True
    resultado = extrator.extrair(arquivo.caminho)
    cache.gravar(chave, arquivo.identificador, h, params.chave(), resultado)
    return arquivo, resultado, False


def processar_arquivos(
    arquivos: list[ArquivoAcervo],
    cache: CacheExtracao,
    params: ParametrosExtracao,
    extrator: Extrator,
    resume: bool = True,
    force: bool = False,
    workers: int = 1,
    sample: int | None = None,
    logger=None,
) -> tuple[list[tuple[ArquivoAcervo, ResultadoExtracao]], int]:
    """Extrai (ou reaproveita do cache) o texto de cada arquivo.

    Retorna a lista na mesma ordem do inventario e o numero de falhas.
    ``sample`` limita o total de paginas processadas (amostra de 5-10 mil).
    """
    saida: list[tuple[ArquivoAcervo, ResultadoExtracao]] = []
    falhas = 0
    usados_cache = 0

    def contabilizar() -> int:
        return sum(r.n_paginas for _, r in saida)

    if workers > 1 and sample is None:
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futuros = {
                pool.submit(
                    _processar_um, arq, cache, params, extrator, resume, force
                ): arq
                for arq in arquivos
            }
            por_arquivo = {}
            for futuro in as_completed(futuros):
                arq = futuros[futuro]
                try:
                    por_arquivo[arq.identificador] = futuro.result()
                except ErroExtracao as exc:
                    falhas += 1
                    if logger:
                        logger.error("falha de extracao em %s: %s", arq.identificador, exc)
        for arq in arquivos:
            item = por_arquivo.get(arq.identificador)
            if item is None:
                continue
            _, _, veio_cache = item
            usados_cache += int(veio_cache)
            saida.append((item[0], item[1]))
    else:
        for arq in arquivos:
            if sample is not None and contabilizar() >= sample:
                if logger:
                    logger.info("amostra atingida (%d paginas); demais arquivos ignorados", sample)
                break
            try:
                arq_out, resultado, veio_cache = _processar_um(
                    arq, cache, params, extrator, resume, force
                )
            except ErroExtracao as exc:
                falhas += 1
                if logger:
                    logger.error("falha de extracao em %s: %s", arq.identificador, exc)
                continue
            usados_cache += int(veio_cache)
            saida.append((arq_out, resultado))

    if logger:
        logger.info(
            "extracao: %d arquivos (%d do cache), %d paginas, %d falhas",
            len(saida),
            usados_cache,
            contabilizar(),
            falhas,
        )
    return saida, falhas
