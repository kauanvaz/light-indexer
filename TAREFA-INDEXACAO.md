# Tarefa de Indexação — PDF, DOCX e Imagens

## 1. Objetivo

A aplicação distribuída **apenas consulta** documentos já indexados. Todo o
trabalho de **extração de texto + carga no índice** é feito pelo **script
técnico** em `src/light_indexer/indexer/` (`python -m light_indexer.indexer`).

Hoje o extrator reconhece **PDF** (texto nativo + OCR) e **texto puro (.txt)**.
**A tarefa é estender a extração para DOCX e imagens**, mantendo o pipeline,
o cache retomável e o esquema existentes.

Formatos-alvo ao fim da tarefa:

| Formato | Como extrair |
| --- | --- |
| PDF | texto nativo por página; **OCR nas páginas sem texto** (já existe — revisar) |
| DOCX | texto das runs/parágrafos (sem OCR) |
| Imagem (PNG/JPG/TIFF/BMP/WebP) | **OCR sempre** (a imagem inteira é uma "página") |

---

## 2. Onde isso vive (mapa do código)

Tudo abaixo está em `src/light_indexer/indexer/` — **é a sua área de trabalho**.
O restante de `src/light_indexer/` é o runtime de consulta e **não deve** importar o indexador.

| Arquivo | Papel | Você mexe? |
| --- | --- | --- |
| `indexer/extract.py` | **Extração de texto/OCR por arquivo** | **Sim — núcleo da tarefa** |
| `indexer/inventory.py` | Lista os arquivos do acervo por extensão | **Sim (só a lista de extensões)** |
| `indexer/cache.py` | Cache retomável (`ResultadoExtracao`) | Não (só usa) |
| `indexer/load.py` | Normaliza e carrega no SQLite/FTS5 | Não (só usa) |
| `indexer/metadata.py` | Título de exibição | Não (só usa) |
| `indexer/validate.py`, `report.py` | Relatório de validação | Não |
| `indexer/evaluate.py` | Avaliação prefixo vs. stemming | Não |
| `indexer/cli.py` | Subcomandos (`build`, `extract`, ...) | Não (a menos que combine) |
| `pyproject.toml` | Dependências do extra `build` | **Sim (adicionar dependência)** |

### Módulos compartilhados (contrato — cuidado)

Importados **também pelo runtime de consulta**; mudar comportamento quebra a busca:

- `src/light_indexer/schema.py` — esquema do banco, `rebuild`/`optimize`, abertura `mode=ro&immutable=1`.
- `src/light_indexer/search/normalize.py` — `Normalizador` (mesma normalização na indexação e na consulta).

> Regra: **não** altere `schema.py` nem `search/normalize.py` sem alinhar antes.
> A tarefa não exige mudá-los.

---

## 3. Contrato que você DEVE respeitar

O pipeline chama sempre **uma** função e espera sempre **um** formato de retorno.
Não invente estruturas novas; encaixe-se nestas.

### 3.1 A porta de entrada — `Extrator.extrair`

Em `indexer/extract.py`:

```python
class Extrator:
    def extrair(self, caminho: Path) -> ResultadoExtracao:
        # despacho por extensão
        if caminho.suffix.lower() == ".pdf":
            return self._extrair_pdf(caminho)
        return self._extrair_texto(caminho)   # <- hoje cai aqui p/ .txt
```

É **aqui** que DOCX e imagens entram (ver seção 5).

### 3.2 O valor de retorno — `ResultadoExtracao`

Definido em `indexer/cache.py` e consumido por `load.py`, `validate.py` e `evaluate.py`:

```python
@dataclass
class ResultadoExtracao:
    paginas: list[dict]   # cada item: {"pagina": int, "texto": str, "fonte": str}
    n_ocr: int            # quantas páginas passaram por OCR
    n_sem_texto: int      # quantas ficaram sem texto após a extração
```

Regras dos itens de `paginas`:

- `"pagina"`: número **1-based** (PDF: 1..N; DOCX e imagem: `1`).
- `"texto"`: texto **bruto** (sem normalizar — a normalização é feita em `load.py`).
- `"fonte"`: uma das constantes de `extract.py`:
  - `FONTE_NATIVO = "nativo"` (texto digital nativo; DOCX também conta como nativo),
  - `FONTE_OCR = "ocr"` (veio do Tesseract; vale para imagem e p/ página de PDF escaneada),
  - `FONTE_VAZIO = "sem_texto"` (não foi possível obter texto).

Contadores: incremente `n_ocr` quando `fonte == FONTE_OCR` e `n_sem_texto` quando
`fonte == FONTE_VAZIO`. `n_paginas` é propriedade derivada (`len(paginas)`).

---

## 4. Estado atual da extração (leia antes de mexer)

Em `indexer/extract.py`:

- `_extrair_pdf`: abre com **PyMuPDF** (`import pymupdf`), percorre
  `doc.page_count`, usa `page.get_text("text")`; se o texto vier vazio/curto
  (`< params.min_chars`), chama `_ocr(page)`.
- `_ocr(page)`: rasteriza a página (`page.get_pixmap(dpi=...)`), converte para
  PNG em memória e chama **pytesseract** (`image_to_string(imagem, lang=...)`).
  Se o Tesseract não estiver disponível, marca `_tesseract_indisponivel`,
  emite aviso e devolve `""` (a menos que `strict=True`, quando levanta erro).
- `_extrair_texto`: lê bytes, decodifica UTF-8 (fallback latin-1) — usado por `.txt`.
- `ParametrosExtracao(ocr_lang="por", dpi=200, min_chars=20)` — parâmetros de
  OCR e o limiar que decide se uma página é "sem texto".

---

## 5. Desenho sugerido (mínimo)

- **Despacho por extensão** em `Extrator.extrair` (dict `extensão → método` ou
  `if/elif`). Evite abstrações grandes: um método por formato basta.
- **Um único caminho de OCR** compartilhado por PDF e imagem, operando sobre
  uma `PIL.Image`. Isso evita duplicar tratamento de erro do Tesseract.
---

## 7. Como testar

Testes existentes a espelhar: `tests/integration/test_pipeline.py` (usa `.txt`
para exercitar inventário → extração → carga → validação → busca) e
`tests/unit/test_inventory_metadata.py` (extensões reconhecidas).

O que escrever:

1. **Unitário, DOCX:** gerar um `.docx` com `python-docx` num `tmp_path`, rodar
   `Extrator.extrair(...)` e checar `resultado.paginas[0]["texto"]` contém o texto,
   `fonte == "nativo"`, `n_paginas == 1`.
2. **Inventário:** garantir que `.docx` e as extensões de imagem entram em
   `inventariar(...)` e que extensões fora da lista (ex.: `.md`) continuam ignoradas.
3. **Integração ponta a ponta:** um acervo com PDF + DOCX + imagem `.txt`-like
   → `construir(...)` → `validar(...)` sem pendências → busca MATCH retorna o
   documento esperado (adapte `tests/integration/test_pipeline.py`).

Executar:

```bash
uv run pytest -q
uv run pytest tests/integration/test_pipeline.py -q
```

Validação manual ponta a ponta (máquina mestre):

```bash
# inventário
uv run python -m light_indexer.indexer inventory --acervo CAMINHO_DO_ACERVO
# extração (gera cache retomável)
uv run python -m light_indexer.indexer extract --acervo CAMINHO_DO_ACERVO
# pipeline completo + relatório
uv run python -m light_indexer.indexer build --acervo CAMINHO_DO_ACERVO --sample 5000
# progresso
uv run python -m light_indexer.indexer status
```

O relatório (`build/relatorio.txt`) deve sair **sem pendências**.
