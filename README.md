# light-indexer

Aplicação **web local, portátil e descartável** para consultar um acervo de
documentos já indexados através de um único campo de texto. Aplicação, índice e
documentos moram em um **HD/SSD externo** que é conectado a uma máquina Windows e
aberto por um executável — **sem instalação, sem privilégio de administrador e
sem internet**.

O motor de busca é o **SQLite FTS5**: um único arquivo elimina servidor, JVM e
procedimento de encerramento. O índice é aberto em modo somente leitura e
imutável (`mode=ro&immutable=1`), de modo que a unidade de destino não consegue
corrompê-lo.

> A aplicação distribuída **apenas consulta**. A construção do índice é feita por
> um **script técnico** separado, executado na máquina mestre antes da
> distribuição (ver [Indexação](#indexação-ferramenta-técnica)).

## Resumo

- **Usuário final (não técnico):** conecta a unidade, dá duplo-clique no
  `LightIndexer.exe` e pesquisa no navegador. Nada para instalar.
- **Operador de acervo (P2):** roda o pipeline de indexação e monta o pacote de
  release na máquina mestre.

Busca textual com destaque de trecho, paginação de 20 resultados e abertura do
documento original **na página correta** (`#page=N`). Escopo do MVP: sem filtros
e sem facetas.

## Tecnologias

| Camada | Tecnologia |
| --- | --- |
| Linguagem | Python 3.12+ (pinned em 3.14.3) |
| Gerenciador de pacotes | [uv](https://docs.astral.sh/uv/) |
| Banco / busca | SQLite com [FTS5](https://www.sqlite.org/fts5.html) |
| Framework web | Flask (WSGI) |
| Servidor WSGI | waitress (produção, Python puro) |
| Interface | HTML + CSS + JS estáticos, 100% local (sem CDN) |
| Extração | PyMuPDF + pytesseract/Pillow (OCR nas páginas sem texto) |
| Empacotamento | PyInstaller (`--onedir --noconsole`) |
| Testes | pytest |
| Plataforma | Windows 10/11 x64, NTFS, sem admin, sem rede |

## Estrutura do projeto

```text
light-indexer/
├── src/light_indexer/        # runtime de consulta
│   ├── __main__.py           # entrada do lançador (python -m light_indexer)
│   ├── launcher.py           # mutex, porta, readiness, navegador, encerramento
│   ├── server.py             # app Flask + servidor waitress
│   ├── paths.py              # get_application_root() e caminhos derivados
│   ├── config.py             # leitura de config/app.json
│   ├── schema.py             # esquema do banco + abertura read-only immutable
│   ├── routes/               # blueprints: ui, search, documents, status
│   ├── search/               # SearchService, montagem de MATCH, destaque, normalização
│   └── indexer/              # script técnico de indexação (NÃO entra no runtime)
├── web/                      # index.html, css, js, assets locais
├── config/app.json           # porta, tamanho de página, abertura do navegador
├── scripts/                  # wrappers: index, lightindexer, build, prepare-release, smoke_fts5
├── tests/                    # unit/ e integration/
├── data/                     # (git-ignored) índice de desenvolvimento
├── documentos/               # (git-ignored) acervo local
└── logs/                     # (git-ignored)
```

## Requisitos

- Python 3.12+ (o repositório fixa `3.14.3` em `.python-version`).
- [uv](https://docs.astral.sh/uv/) para gerenciar o ambiente e as dependências.
- Para OCR: o binário do **Tesseract** instalado e disponível no `PATH`.
- Windows 10/11 x64 e sistema de arquivos **NTFS** (FAT32 limita arquivos a 4 GB
  e o índice pode ultrapassar isso).

## Como executar

### 1. Preparar o ambiente

```bash
# App de consulta + testes
uv sync --extra runtime

# Ambiente completo de desenvolvimento (app, indexação, testes e empacotamento)
uv sync --all-extras
```

### 2. Rodar a aplicação (modo desenvolvimento)

A aplicação exige um índice em `data/indice.db` (veja a seção de indexação). Para
subir o lançador:

```bash
uv run python -m light_indexer
```

Ou o wrapper do projeto:

```bash
uv run python scripts/lightindexer.py
```

Opcionalmente, aponte para outros diretórios durante o desenvolvimento:

```bash
uv run python -m light_indexer --root . --db build/indice.db --sem-janela --sem-navegador
```

O servidor sobe em `http://127.0.0.1:8765` (ou na próxima porta livre) e pode ser
encerrado com `Ctrl+C`.

### 3. Rodar os testes

```bash
uv run pytest -q
uv run pytest tests/integration/test_pipeline.py -q
```

## Indexação (ferramenta técnica)

O script de indexação é uma ferramenta de **linha de comando** usada na máquina
mestre. Ele **não faz parte** do pacote portátil nem do executável. Ponto de
entrada:

```bash
uv run python -m light_indexer.indexer <comando> [opções]
# ou
uv run python scripts/index.py <comando> [opções]
```

**Comandos:**

| Comando | Função |
| --- | --- |
| `inventory` | Inventaria o acervo (caminho relativo + id estável) |
| `extract` | Extrai texto nativo e roda OCR nas páginas sem texto (retomável) |
| `metadata` | Extrai/normaliza metadados de exibição (título etc.) |
| `load` | Normaliza, carrega tabelas e constrói o FTS5 |
| `validate` | Gera o relatório de validação |
| `build` | Pipeline completo: inventory → extract → metadata → load → validate |
| `status` | Mostra progresso do cache e do índice parcial |
| `evaluate` | Compara prefixo vs. stemming em consultas conhecidas |

**Exemplos:**

```bash
# pipeline completo sobre uma amostra
uv run python -m light_indexer.indexer build --acervo CAMINHO_DO_ACERVO --sample 5000

# progresso
uv run python -m light_indexer.indexer status
```

O relatório de validação é escrito em `build/relatorio.txt` e deve sair **sem
pendências**. O índice final fica em `build/indice.db`.

**Principais opções globais:** `--acervo` (obrigatório), `--cache`, `--db`,
`--workers`, `--ocr-lang` (default `por`), `--dpi`, `--min-chars`, `--sample`,
`--modo` (`prefixo`/`stemming`), `--force`, `--strict`, `--verbose`.

## Build e release

```bash
# limpa, roda o teste de fumaça FTS5 e empacota com PyInstaller
uv run python scripts/build.py

# monta o pacote portátil (copia índice + documentos, valida, gera version.json)
uv run python scripts/prepare-release.py
```

O build interrompe se o teste de fumaça do FTS5 falhar. O pacote final segue o
formato de pasta única descrito no `PRD.md` (seção 5.10).

## API local

| Método | Rota | Descrição |
| --- | --- | --- |
| GET | `/` | Entrega a interface web |
| GET | `/api/search` | Busca textual (`q`, `page`, `size`) |
| GET | `/documentos/<id>` | Entrega o documento (suporta `Range`; `#page=N` no cliente) |
| GET | `/api/status` | Estado, versões e quantidade de documentos |

Não existe rota de escrita ou administração. O servidor escuta apenas em
`127.0.0.1`.

## Configuração

Configuração principal em `config/app.json` (porta preferida, tamanho de página,
host, nível de log, limites de consulta, `cache_size`, `mmap_size`). Variáveis de
ambiente têm precedência e servem para desenvolvimento/teste:

`LIGHT_INDEXER_ROOT`, `LIGHT_INDEXER_DB`, `LIGHT_INDEXER_PORT`,
`LIGHT_INDEXER_HOST`, `LIGHT_INDEXER_LOG_DIR`, `LIGHT_INDEXER_LOG_LEVEL`,
`LIGHT_INDEXER_DOCS_DIR`, `LIGHT_INDEXER_STATE_DIR`,
`LIGHT_INDEXER_FORCE_MUTEX_NAME`.

