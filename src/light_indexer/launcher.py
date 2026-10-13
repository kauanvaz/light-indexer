"""Lancador do Light indexer: raiz, validacao, instancia unica, porta e encerramento.

Implementa o fluxo de inicializacao do PRD 5.4 e a Sprint 5 (Fase 5): um clique
inicia tudo e encerrar libera a unidade. Ordem: raiz + config, validacao da
estrutura e da versao do esquema, mutex nomeado (instancia unica), escolha de
porta, servidor em segundo plano, readiness em ``/api/status`` e abertura do
navegador (PRD 5.4, 5.11, 11.2).

Estado de runtime (porta/PID) fica em ``%LOCALAPPDATA%`` (PRD 11.3), nunca na
unidade. O encerramento e feito por uma janela de controle minima (stdlib,
sem dependencia): o localizador de bandeja do Windows fica para a evolucao
futura (PRD 4.2), pois exigiria biblioteca de terceiros no runtime.
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import socket
import sys
import threading
import time
import urllib.error
import urllib.request
import webbrowser
from pathlib import Path

from . import __version__, schema
from .config import Config
from .logging_setup import configurar_logging
from .paths import (
    caminho_config,
    caminho_db,
    diretorio_documentos,
    diretorio_estado,
    diretorio_logs,
    get_application_root,
)
from .server import criar_app, servir

__all__ = [
    "ErroLancamento",
    "InstanciaUnica",
    "Lancador",
    "escolher_porta",
    "gravar_estado",
    "ler_estado",
    "remover_estado",
    "validar_esquema",
    "validar_estrutura",
    "aguardar_readiness",
    "main",
]

MUTEX_ENV = "LIGHT_INDEXER_FORCE_MUTEX_NAME"
NOME_MUTEX_PADRAO = "light-indexer-single-instance"
ESTADO_ARQUIVO = "estado.json"
TIMEOUT_READINESS = 10.0

_ERROR_ALREADY_EXISTS = 183


class ErroLancamento(RuntimeError):
    """Falha previsivel de inicializacao, com mensagem amigavel ao usuario."""


def _caminho_log(root: Path | None = None) -> str:
    try:
        base = diretorio_logs(root) if root else diretorio_logs()
    except Exception:  # pragma: no cover - defensivo
        base = Path("logs")
    return str(base / "light-indexer.log")


# ---------------------------------------------------------------------------
# Validacao de estrutura e versao do esquema (PRD 5.4, 5.6)
# ---------------------------------------------------------------------------


def _problemas_estrutura(root: Path, db_path: Path, web_index: Path) -> list[str]:
    problemas: list[str] = []
    if not root.is_dir():
        problemas.append(f"raiz do pacote inexistente ({root})")
    if not web_index.is_file():
        problemas.append(f"interface web ausente ({web_index})")
    if not db_path.is_file():
        problemas.append(f"indice ausente ({db_path})")
    return problemas


def validar_estrutura(
    root: str | Path, db_path: str | Path, web_index: str | Path | None = None
) -> None:
    """Confere os arquivos minimos do pacote antes de subir o servidor."""
    root = Path(root)
    db_path = Path(db_path)
    web_index = Path(web_index) if web_index else root / "web" / "index.html"
    problemas = _problemas_estrutura(root, db_path, web_index)
    if problemas:
        raise ErroLancamento(
            "O pacote esta incompleto: "
            + "; ".join(problemas)
            + f". Registro: {_caminho_log(root)}"
        )


def validar_esquema(db_path: str | Path) -> None:
    """Confere a versao do esquema; recusa indice corrompido ou incompativel."""
    caminho = str(db_path)
    try:
        con = schema.abrir(caminho, somente_leitura=True, imutavel=True)
    except sqlite3.Error as exc:
        raise ErroLancamento(
            f"Nao foi possivel abrir o indice ({db_path}). "
            "O arquivo pode estar corrompido ou incompleto."
        ) from exc
    try:
        if not schema.compatibilidade_ok(con):
            encontrada = schema.versao_esquema(con)
            raise ErroLancamento(
                "Versao de esquema incompativel: "
                f"indice={encontrada} esperado={schema.VERSAO_ESQUEMA}. "
                "Atualize o pacote (data/ e documentos/)."
            )
    finally:
        con.close()


# ---------------------------------------------------------------------------
# Instancia unica (mutex nomeado) - PRD 5.4, 12 (R10)
# ---------------------------------------------------------------------------


def _slug(nome: str) -> str:
    return "".join(c if c.isalnum() or c in "-_." else "_" for c in nome)


class InstanciaUnica:
    """Garante uma unica instancia.

    Windows: mutex nomeado (``CreateMutexW``). Outros sistemas: trava de
    arquivo com ``fcntl.flock`` (liberada automaticamente se o processo morre,
    evitando trava obsoleta apos um travamento).
    """

    def __init__(self, nome: str | None = None) -> None:
        self.nome = nome or os.environ.get(MUTEX_ENV) or NOME_MUTEX_PADRAO
        self._handle = None
        self._fd: int | None = None
        self._lock = diretorio_estado() / f"{_slug(self.nome)}.lock"

    def _adquirir_nt(self) -> bool:
        import ctypes

        self._handle = ctypes.windll.kernel32.CreateMutexW(None, False, self.nome)
        if not self._handle:
            return False
        if ctypes.windll.kernel32.GetLastError() == _ERROR_ALREADY_EXISTS:
            ctypes.windll.kernel32.CloseHandle(self._handle)
            self._handle = None
            return False
        return True

    def _adquirir_posix(self) -> bool:
        import fcntl

        self._lock.parent.mkdir(parents=True, exist_ok=True)
        self._fd = os.open(self._lock, os.O_CREAT | os.O_RDWR, 0o600)
        try:
            fcntl.flock(self._fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            os.close(self._fd)
            self._fd = None
            return False
        os.ftruncate(self._fd, 0)
        os.write(self._fd, str(os.getpid()).encode("ascii"))
        return True

    def adquirir(self) -> bool:
        if os.name == "nt":
            return self._adquirir_nt()
        return self._adquirir_posix()

    def liberar(self) -> None:
        if self._handle is not None:
            import ctypes

            ctypes.windll.kernel32.ReleaseMutex(self._handle)
            ctypes.windll.kernel32.CloseHandle(self._handle)
            self._handle = None
        if self._fd is not None:
            import fcntl

            try:
                fcntl.flock(self._fd, fcntl.LOCK_UN)
            except OSError:  # pragma: no cover - defensivo
                pass
            os.close(self._fd)
            self._fd = None


# ---------------------------------------------------------------------------
# Escolha de porta (PRD 5.4, 11.1)
# ---------------------------------------------------------------------------


def escolher_porta(host: str, preferida: int, tentativas: int = 20) -> int:
    """Retorna a porta preferida ou a proxima livre; ``0`` deixa o SO escolher."""
    if preferida <= 0:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind((host, 0))
            return int(s.getsockname()[1])
    for deslocamento in range(max(1, tentativas)):
        porta = preferida + deslocamento
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind((host, porta))
                return porta
            except OSError:
                continue
    raise OSError(f"nenhuma porta livre a partir de {preferida}")


# ---------------------------------------------------------------------------
# Estado de runtime em %LOCALAPPDATA% (PRD 11.3)
# ---------------------------------------------------------------------------


def _arquivo_estado() -> Path:
    return diretorio_estado() / ESTADO_ARQUIVO


def gravar_estado(porta: int, pid: int | None = None, url: str | None = None) -> Path:
    destino = _arquivo_estado()
    destino.parent.mkdir(parents=True, exist_ok=True)
    dados = {
        "porta": int(porta),
        "pid": int(pid if pid is not None else os.getpid()),
        "url": url or f"http://127.0.0.1:{porta}",
        "iniciado_em": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }
    destino.write_text(json.dumps(dados, ensure_ascii=False), encoding="utf-8")
    return destino


def ler_estado() -> dict | None:
    destino = _arquivo_estado()
    if not destino.is_file():
        return None
    try:
        return json.loads(destino.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def remover_estado() -> None:
    try:
        _arquivo_estado().unlink(missing_ok=True)
    except OSError:  # pragma: no cover - defensivo
        pass


# ---------------------------------------------------------------------------
# Readiness e navegador (PRD 5.4, UC1)
# ---------------------------------------------------------------------------


def aguardar_readiness(
    url: str, timeout: float = TIMEOUT_READINESS, intervalo: float = 0.1
) -> bool:
    """Aguarda ``GET /api/status`` responder ``ok`` (PRD 5.4, 7.1)."""
    alvo = url.rstrip("/") + "/api/status"
    limite = time.monotonic() + max(0.0, timeout)
    while True:
        try:
            with urllib.request.urlopen(alvo, timeout=2) as resposta:
                if resposta.status == 200:
                    dados = json.loads(resposta.read().decode("utf-8"))
                    if dados.get("status") == "ok":
                        return True
        except (urllib.error.URLError, OSError, ValueError):
            pass
        if time.monotonic() >= limite:
            return False
        time.sleep(intervalo)


def abrir_no_navegador(url: str) -> bool:
    try:
        return webbrowser.open(url)
    except Exception:  # pragma: no cover - defensivo
        return False


# ---------------------------------------------------------------------------
# Janela de controle / espera por sinal
# ---------------------------------------------------------------------------


def _tk_disponivel() -> bool:
    import importlib.util

    return importlib.util.find_spec("tkinter") is not None


def _janela_controle(url: str, ao_encerrar, ao_abrir) -> bool:
    """Janela minima de controle (stdlib). Retorna False se indisponivel."""
    try:
        import tkinter as tk
    except Exception:  # pragma: no cover - ambientes sem Tk
        return False
    try:
        raiz = tk.Tk()
    except Exception:  # pragma: no cover - sem display
        return False

    raiz.title("light-indexer")
    raiz.resizable(False, False)
    raiz.configure(padx=18, pady=16)
    tk.Label(raiz, text="O Light indexer esta ativo.", font=("Segoe UI", 12, "bold")).pack(
        anchor="w"
    )
    tk.Label(raiz, text=url, fg="#0a58ca").pack(anchor="w", pady=(2, 8))
    tk.Label(
        raiz,
        text="Para remover a unidade com seguranca,\nclique em Encerrar.",
        justify="left",
    ).pack(anchor="w")

    barra = tk.Frame(raiz)
    barra.pack(fill="x", pady=(12, 0))
    tk.Button(barra, text="Abrir no navegador", command=ao_abrir).pack(side="left")
    tk.Button(
        barra,
        text="Encerrar",
        command=lambda: (ao_encerrar(), raiz.destroy()),
        bg="#b02a37",
        fg="white",
    ).pack(side="right")
    raiz.protocol("WM_DELETE_WINDOW", lambda: (ao_encerrar(), raiz.destroy()))
    raiz.mainloop()
    return True


# ---------------------------------------------------------------------------
# Orquestracao
# ---------------------------------------------------------------------------


class Lancador:
    """Orquestra inicializacao e encerramento do Light indexer."""

    def __init__(
        self,
        cfg: Config | None = None,
        root: str | Path | None = None,
        db_path: str | Path | None = None,
        docs_dir: str | Path | None = None,
        host: str | None = None,
        web_index: str | Path | None = None,
    ) -> None:
        self.root = Path(root) if root else get_application_root()
        self.cfg = cfg or Config.carregar(caminho_config(self.root))
        self.db_path = Path(db_path) if db_path else caminho_db(self.root)
        self.docs_dir = Path(docs_dir) if docs_dir else diretorio_documentos(self.root)
        self.web_index = Path(web_index) if web_index else self.root / "web" / "index.html"
        self.host = host or self.cfg.host
        self.timeout_readiness = TIMEOUT_READINESS
        self.porta: int | None = None
        self.url: str | None = None
        self._instancia: InstanciaUnica | None = None
        self._servidor = None
        self._thread: threading.Thread | None = None
        self._parar = threading.Event()

    def preparar(self) -> str:
        """Valida o pacote, adquire o mutex e escolhe a porta."""
        validar_estrutura(self.root, self.db_path, self.web_index)
        validar_esquema(self.db_path)

        self._instancia = InstanciaUnica()
        if not self._instancia.adquirir():
            self._instancia = None
            raise ErroLancamento(
                "O Light indexer ja esta aberto. Use a janela que ja esta na tela; "
                "se ela nao aparecer, reinicie o computador."
            )

        try:
            self.porta = escolher_porta(self.host, self.cfg.porta_preferida)
        except OSError as exc:
            self._instancia.liberar()
            self._instancia = None
            raise ErroLancamento(
                "Nenhuma porta local disponivel. " f"Registro: {_caminho_log(self.root)}"
            ) from exc

        self.url = f"http://{self.host}:{self.porta}"
        return self.url

    def iniciar(self) -> str:
        """Sobe o servidor em segundo plano e aguarda o readiness."""
        if self._servidor is not None:
            return self.url or ""

        app = criar_app(
            cfg=self.cfg, root=self.root, db_path=self.db_path, docs_dir=self.docs_dir
        )

        ultimo_erro: OSError | None = None
        for _ in range(20):
            try:
                self._servidor = servir(app, host=self.host, porta=self.porta)
                break
            except OSError as exc:
                ultimo_erro = exc
                self.porta = escolher_porta(self.host, (self.porta or 0) + 1)
        else:
            raise ErroLancamento(
                "Nenhuma porta local disponivel. "
                f"Registro: {_caminho_log(self.root)}"
            ) from ultimo_erro

        app.config["PORTA"] = self.porta
        self.url = f"http://{self.host}:{self.porta}"

        self._thread = threading.Thread(
            target=self._servidor.run, name="light-indexer-http", daemon=True
        )
        self._thread.start()

        if not aguardar_readiness(self.url, timeout=self.timeout_readiness):
            self.encerrar()
            raise ErroLancamento(
                "O servidor local nao respondeu a tempo. "
                f"Registro: {_caminho_log(self.root)}"
            )

        gravar_estado(self.porta, os.getpid(), self.url)
        return self.url

    def encerrar(self) -> None:
        """Para o servidor e libera mutex, estado e a unidade."""
        self._parar.set()

        servidor, self._servidor = self._servidor, None
        if servidor is not None:
            # Para os workers primeiro; so entao fecha o socket/trigger, para
            # nao interromper requisicoes em andamento (evita traceback ruidoso).
            try:
                servidor.task_dispatcher.shutdown()
            except Exception:  # pragma: no cover - defensivo
                pass
            try:
                servidor.close()
            except Exception:  # pragma: no cover - defensivo
                pass

        thread, self._thread = self._thread, None
        if thread is not None and thread.is_alive():
            thread.join(timeout=5)

        remover_estado()
        if self._instancia is not None:
            self._instancia.liberar()
            self._instancia = None

    def _aguardar_sinal(self) -> None:
        import signal

        anteriores: dict[int, object] = {}

        def _parar(_signum, _frame):
            self._parar.set()

        for sig in (getattr(signal, "SIGINT", None), getattr(signal, "SIGTERM", None)):
            if sig is None:
                continue
            try:
                anteriores[sig] = signal.signal(sig, _parar)
            except (ValueError, OSError):  # pragma: no cover - thread nao principal
                pass
        try:
            while not self._parar.wait(timeout=0.5):
                pass
        finally:
            for sig, anterior in anteriores.items():
                try:
                    signal.signal(sig, anterior)
                except (ValueError, OSError):  # pragma: no cover - defensivo
                    pass

    def executar(self, abrir_navegador: bool | None = None, com_janela: bool = True) -> int:
        """Inicia tudo, espera o encerramento e libera a unidade."""
        url = self.preparar()
        self.iniciar()

        if abrir_navegador is None:
            abrir_navegador = bool(self.cfg.abrir_navegador)
        if abrir_navegador:
            abrir_no_navegador(url)

        try:
            if com_janela and _tk_disponivel():
                if not _janela_controle(
                    url, self._parar.set, lambda: abrir_no_navegador(url)
                ):
                    self._aguardar_sinal()
            else:
                self._aguardar_sinal()
        finally:
            self.encerrar()
        return 0


# ---------------------------------------------------------------------------
# Entrada de linha de comando
# ---------------------------------------------------------------------------


def _mostrar_erro(mensagem: str) -> None:
    """Mostra o erro ao usuario: caixa no Windows, senao stderr."""
    if os.name == "nt":  # pragma: no cover - especifico do Windows
        try:
            import ctypes

            ctypes.windll.user32.MessageBoxW(None, mensagem, "light-indexer", 0x10)
            return
        except Exception:
            pass
    print(mensagem, file=sys.stderr)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="Light indexer", description="Lancador do light-indexer (PRD 5.4)."
    )
    parser.add_argument("--root", type=Path, default=None)
    parser.add_argument("--db", type=Path, default=None)
    parser.add_argument("--docs", type=Path, default=None)
    parser.add_argument("--host", default=None)
    parser.add_argument("--porta", type=int, default=None)
    parser.add_argument("--sem-navegador", action="store_true")
    parser.add_argument("--sem-janela", action="store_true")
    parser.add_argument(
        "--smoke-fts5",
        action="store_true",
        help=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--smoke-saida",
        type=Path,
        default=None,
        help=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--version", action="version", version=f"light-indexer {__version__}"
    )
    args = parser.parse_args(argv)

    if args.smoke_fts5:
        from . import smoke

        return smoke.main(
            ["--saida", str(args.smoke_saida)] if args.smoke_saida else []
        )

    root = Path(args.root) if args.root else get_application_root()
    cfg = Config.carregar(caminho_config(root))
    if args.porta is not None:
        cfg.porta_preferida = args.porta
    if args.host is not None:
        cfg.host = args.host

    logger = configurar_logging(cfg)

    lancador = Lancador(
        cfg=cfg, root=root, db_path=args.db, docs_dir=args.docs, host=args.host
    )
    try:
        return lancador.executar(
            abrir_navegador=False if args.sem_navegador else None,
            com_janela=not args.sem_janela,
        )
    except ErroLancamento as exc:
        logger.error("falha ao iniciar: %s", exc)
        _mostrar_erro(str(exc))
        return 2
    except KeyboardInterrupt:  # pragma: no cover - encerramento pelo usuario
        return 0
    except Exception:  # pragma: no cover - defensivo
        logger.exception("erro inesperado no lancador")
        _mostrar_erro(
            "Ocorreu um erro inesperado. " f"Registro: {_caminho_log(root)}"
        )
        return 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
