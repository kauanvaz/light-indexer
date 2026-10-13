"""Formatacao do relatorio de validacao (PRD 6.6)."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Relatorio:
    documentos_encontrados: int = 0
    documentos_indexados: int = 0
    paginas_indexadas: int = 0
    arquivos_sem_registro: int = 0
    registros_sem_arquivo: int = 0
    paginas_sem_texto: int = 0
    paginas_ocr: int = 0
    integrity_check: str = "ok"
    modo_normalizacao: str = ""
    pendencias: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.pendencias and self.integrity_check == "ok"

    def texto(self) -> str:
        linhas = [
            f"Documentos encontrados:   {self.documentos_encontrados}",
            f"Documentos indexados:     {self.documentos_indexados}",
            f"Paginas indexadas:        {self.paginas_indexadas}",
            f"Arquivos sem registro:    {self.arquivos_sem_registro}",
            f"Registros sem arquivo:    {self.registros_sem_arquivo}",
            (
                f"Paginas sem texto:        {self.paginas_sem_texto} "
                f"({self.paginas_ocr} passaram por OCR)"
            ),
            f"PRAGMA integrity_check:   {self.integrity_check}",
            f"Modo de normalizacao:     {self.modo_normalizacao or '-'}",
        ]
        if self.pendencias:
            linhas.append("Pendencias:")
            linhas.extend(f"  - {p}" for p in self.pendencias)
        else:
            linhas.append("Pendencias:               0")
        return "\n".join(linhas) + "\n"


def escrever_relatorio(relatorio: Relatorio, caminho: Path) -> None:
    caminho = Path(caminho)
    caminho.parent.mkdir(parents=True, exist_ok=True)
    with caminho.open("w", encoding="utf-8") as fh:
        fh.write(relatorio.texto())
