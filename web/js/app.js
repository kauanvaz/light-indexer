/* Interface do Light indexer — logica de UI (PRD 7.2, UC2, UC4, UC9).
   JavaScript puro, sem CDN, sem dependencias. Conversa apenas com a API local:
   GET /api/search, GET /api/status e GET /documentos/<id> (via link). */

(function () {
  "use strict";

  var form = document.getElementById("form-busca");
  var campo = document.getElementById("campo");
  var resumo = document.getElementById("resumo");
  var lista = document.getElementById("lista");
  var estado = document.getElementById("estado");
  var paginacao = document.getElementById("paginacao");
  var acervoInfo = document.getElementById("acervo-info");
  var rodapeMeta = document.getElementById("rodape-meta");

  var controlador = null;
  var sequencia = 0;

  function plural(n, singular, pluralForma) {
    return n === 1 ? singular : pluralForma;
  }

  function nomeArquivo(arquivo) {
    var partes = String(arquivo || "").split("/");
    return partes[partes.length - 1] || String(arquivo || "");
  }

  function limpar(node) {
    while (node.firstChild) {
      node.removeChild(node.firstChild);
    }
  }

  function limparListas() {
    limpar(lista);
    limpar(paginacao);
    paginacao.hidden = true;
  }

  function lerParametros() {
    var params = new URLSearchParams(window.location.search);
    var page = parseInt(params.get("page"), 10);
    return {
      q: (params.get("q") || "").trim(),
      page: page > 0 ? page : 1
    };
  }

  function urlBusca(q, page) {
    var params = new URLSearchParams();
    params.set("q", q);
    if (page > 1) {
      params.set("page", String(page));
    }
    return window.location.pathname + "?" + params.toString();
  }

  function atualizarUrl(q, page, empilhar) {
    var url = q ? urlBusca(q, page) : window.location.pathname;
    var estadoHistorico = { q: q, page: page };
    if (empilhar) {
      window.history.pushState(estadoHistorico, "", url);
    } else {
      window.history.replaceState(estadoHistorico, "", url);
    }
  }

  /* ---------- Estados ---------- */

  function mostrarEstado(tipo, mensagem, complemento) {
    limpar(estado);
    estado.className = "estado estado--" + tipo;
    estado.hidden = false;

    if (tipo === "carregando") {
      var spinner = document.createElement("span");
      spinner.className = "spinner";
      spinner.setAttribute("aria-hidden", "true");
      estado.appendChild(spinner);
    }

    var texto = document.createElement("p");
    texto.className = "estado__texto";
    texto.textContent = mensagem;
    estado.appendChild(texto);

    if (complemento) {
      var extra = document.createElement("p");
      extra.className = "estado__extra";
      extra.textContent = complemento;
      estado.appendChild(extra);
    }
  }

  function esconderEstado() {
    estado.hidden = true;
    limpar(estado);
  }

  function mostrarCarregando() {
    resumo.textContent = "";
    limparListas();
    mostrarEstado("carregando", "Pesquisando no acervo…");
    form.setAttribute("aria-busy", "true");
  }

  function mostrarInicial() {
    resumo.textContent = "";
    limparListas();
    mostrarEstado(
      "inicial",
      "Pesquise no acervo",
      "Digite uma palavra-chave e pressione Enter para encontrar documentos."
    );
  }

  function mostrarVazio(q) {
    limparListas();
    mostrarEstado(
      "vazio",
      "Nenhum resultado para “" + q + "”.",
      "Verifique a grafia ou tente um termo mais curto."
    );
  }

  function mostrarErro(mensagem) {
    limparListas();
    mostrarEstado(
      "erro",
      mensagem || "Não foi possível concluir a busca.",
      "Tente novamente. Se persistir, consulte os logs na pasta logs/."
    );
  }

  /* ---------- Montagem dos resultados ---------- */

  function montarItem(r) {
    var li = document.createElement("li");
    li.className = "resultado";

    var titulo = document.createElement("h2");
    titulo.className = "resultado__titulo";
    var link = document.createElement("a");
    /* Abre o PDF inline no visualizador do navegador, ja na pagina do
       resultado; a nova aba preserva o termo e a pagina pesquisados (UC3). */
    link.href = "/documentos/" + encodeURIComponent(r.doc_id) + "#page=" + encodeURIComponent(r.pagina || 1);
    link.target = "_blank";
    link.rel = "noopener";
    link.textContent = (r.titulo && r.titulo.trim()) ? r.titulo : nomeArquivo(r.arquivo);
    titulo.appendChild(link);

    var meta = document.createElement("p");
    meta.className = "resultado__meta";
    var arquivo = document.createElement("span");
    arquivo.className = "resultado__arquivo";
    arquivo.textContent = r.arquivo || "";
    arquivo.title = r.arquivo || "";
    var pagina = document.createElement("span");
    pagina.className = "resultado__pagina";
    pagina.textContent = "página " + (r.pagina || 1);
    meta.appendChild(arquivo);
    meta.appendChild(pagina);

    var trecho = document.createElement("p");
    trecho.className = "resultado__trecho";
    /* Seguro por contrato: o servidor escapa o texto original e insere apenas
       as marcas <mark> (PRD 5.11 e 7.2). Titulo e arquivo vao por textContent. */
    trecho.innerHTML = r.trecho || "";

    li.appendChild(titulo);
    li.appendChild(meta);
    li.appendChild(trecho);
    return li;
  }

  function intervaloPaginas(atual, total) {
    var paginas = [];
    for (var i = 1; i <= total; i++) {
      if (i === 1 || i === total || Math.abs(i - atual) <= 1) {
        paginas.push(i);
      } else if (paginas[paginas.length - 1] !== "…") {
        paginas.push("…");
      }
    }
    return paginas;
  }

  function montarBotaoPagina(texto, destino, q, opcoes) {
    opcoes = opcoes || {};
    if (opcoes.desabilitado) {
      var inerte = document.createElement("span");
      inerte.className = "paginacao__item paginacao__item--desabilitado";
      inerte.setAttribute("aria-disabled", "true");
      inerte.textContent = texto;
      return inerte;
    }
    var link = document.createElement("a");
    link.className = "paginacao__item" + (opcoes.atual ? " paginacao__item--atual" : "");
    link.href = urlBusca(q, destino);
    link.textContent = texto;
    if (opcoes.rotulo) {
      link.setAttribute("aria-label", opcoes.rotulo);
    }
    if (opcoes.atual) {
      link.setAttribute("aria-current", "page");
    }
    link.addEventListener("click", function (evento) {
      if (evento.metaKey || evento.ctrlKey || evento.shiftKey || evento.button !== 0) {
        return;
      }
      evento.preventDefault();
      buscar(q, destino, { empilhar: true });
    });
    return link;
  }

  function montarPaginacao(q, totalPaginas, pagina) {
    if (totalPaginas <= 1) {
      paginacao.hidden = true;
      return;
    }
    var frag = document.createDocumentFragment();
    frag.appendChild(montarBotaoPagina("‹ Anterior", pagina - 1, q, {
      desabilitado: pagina <= 1,
      rotulo: "Página anterior"
    }));

    intervaloPaginas(pagina, totalPaginas).forEach(function (p) {
      if (p === "…") {
        var reticencias = document.createElement("span");
        reticencias.className = "paginacao__reticencias";
        reticencias.setAttribute("aria-hidden", "true");
        reticencias.textContent = "…";
        frag.appendChild(reticencias);
        return;
      }
      frag.appendChild(montarBotaoPagina(String(p), p, q, {
        atual: p === pagina,
        rotulo: "Página " + p
      }));
    });

    frag.appendChild(montarBotaoPagina("Próxima ›", pagina + 1, q, {
      desabilitado: pagina >= totalPaginas,
      rotulo: "Próxima página"
    }));

    limpar(paginacao);
    paginacao.appendChild(frag);
    paginacao.hidden = false;
  }

  function renderizar(q, dados) {
    limparListas();
    esconderEstado();

    var total = dados.total || 0;
    var size = dados.size || 20;
    var pagina = dados.page || 1;
    var resultados = dados.results || [];
    var totalPaginas = total > 0 ? Math.ceil(total / size) : 0;

    if (total === 0) {
      mostrarVazio(q);
      return;
    }

    if (pagina > totalPaginas) {
      mostrarEstado(
        "vazio",
        "Esta página não possui resultados.",
        "O acervo tem " + total + " " + plural(total, "documento", "documentos") + " para “" + q + "”."
      );
      montarPaginacao(q, totalPaginas, pagina);
      return;
    }

    var de = (pagina - 1) * size + 1;
    var ate = de + resultados.length - 1;
    resumo.textContent =
      total + " " + plural(total, "resultado", "resultados") +
      " para “" + q + "” · exibindo " + de + "–" + ate;

    var frag = document.createDocumentFragment();
    resultados.forEach(function (r) {
      frag.appendChild(montarItem(r));
    });
    lista.appendChild(frag);

    montarPaginacao(q, totalPaginas, pagina);
  }

  /* ---------- Busca ---------- */

  function buscar(q, pagina, opcoes) {
    opcoes = opcoes || {};
    q = (q || "").trim();
    pagina = Math.max(1, parseInt(pagina, 10) || 1);

    if (controlador) {
      controlador.abort();
      controlador = null;
    }
    form.removeAttribute("aria-busy");

    if (!q) {
      atualizarUrl("", 1, opcoes.empilhar === true);
      mostrarInicial();
      return;
    }

    atualizarUrl(q, pagina, opcoes.empilhar === true);
    mostrarCarregando();

    var token = ++sequencia;
    if (typeof AbortController !== "undefined") {
      controlador = new AbortController();
    }

    var params = new URLSearchParams();
    params.set("q", q);
    params.set("page", String(pagina));

    fetch("/api/search?" + params.toString(), {
      headers: { "Accept": "application/json" },
      signal: controlador ? controlador.signal : undefined
    })
      .then(function (resposta) {
        return resposta.json()
          .catch(function () { return {}; })
          .then(function (dados) {
            return { ok: resposta.ok, dados: dados };
          });
      })
      .then(function (r) {
        if (token !== sequencia) {
          return;
        }
        form.removeAttribute("aria-busy");
        if (!r.ok) {
          mostrarErro(r.dados && r.dados.erro);
          return;
        }
        renderizar(q, r.dados);
      })
      .catch(function (erro) {
        if (erro && erro.name === "AbortError") {
          return;
        }
        if (token !== sequencia) {
          return;
        }
        form.removeAttribute("aria-busy");
        mostrarErro();
      });
  }

  /* ---------- Diagnostico (opcional) ---------- */

  function carregarStatus() {
    fetch("/api/status", { headers: { "Accept": "application/json" } })
      .then(function (resposta) {
        return resposta.ok ? resposta.json() : null;
      })
      .then(function (dados) {
        if (!dados) {
          return;
        }
        if (typeof dados.documentos === "number") {
          acervoInfo.textContent =
            dados.documentos.toLocaleString("pt-BR") + " " +
            plural(dados.documentos, "documento", "documentos") + " no acervo";
        }
        var partes = [];
        if (dados.versao_app) {
          partes.push("versão " + dados.versao_app);
        }
        if (dados.versao_indice) {
          partes.push("índice " + dados.versao_indice);
        }
        rodapeMeta.textContent = partes.join(" · ");
      })
      .catch(function () {
        /* Diagnostico e opcional: a busca funciona mesmo sem /api/status. */
      });
  }

  /* ---------- Inicializacao ---------- */

  form.addEventListener("submit", function (evento) {
    evento.preventDefault();
    buscar(campo.value, 1, { empilhar: true });
  });

  window.addEventListener("popstate", function () {
    var params = lerParametros();
    campo.value = params.q;
    buscar(params.q, params.page, { empilhar: false });
  });

  var inicial = lerParametros();
  campo.value = inicial.q;
  carregarStatus();
  buscar(inicial.q, inicial.page, { empilhar: false });
})();
