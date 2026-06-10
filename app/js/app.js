/* Fala Comunidade — controlador principal
 * Roteia as telas, trata eventos (delegação), liga o ditado por voz e a
 * geolocalização, responde o chat da FalaIA (offline e, opcionalmente,
 * via API do Claude) e registra o service worker do PWA.
 */
(function () {
  'use strict';

  const U = self.FalaUtil;
  const DB = self.FalaDB;
  const ST = self.FalaStats;
  const IA = self.FalaIA;
  const V = self.FalaViews;

  const App = {
    chat: [],
    reconhecimento: null,
    iaTravada: false, // usuário ajustou manualmente os campos da IA no registro
  };

  /* ------------------------------ roteador ---------------------------- */

  const ROTAS = [
    { padrao: /^\/?(inicio)?$/, render: () => V.inicio(), nav: 'inicio' },
    { padrao: /^\/registrar$/, render: (p) => V.registrar(p), nav: 'registrar', aoMontar: montarRegistrar },
    { padrao: /^\/confirmacao\/(.+)$/, render: (p, m) => V.confirmacao({ id: m[1] }), nav: 'registrar' },
    { padrao: /^\/demandas$/, render: (p) => V.demandas(p), nav: 'demandas', aoMontar: montarBuscaDemandas },
    { padrao: /^\/demanda\/(.+)$/, render: (p, m) => V.demandaDetalhe({ id: m[1] }), nav: 'demandas' },
    { padrao: /^\/pessoas$/, render: (p) => V.pessoas(p), nav: 'pessoas', aoMontar: montarBuscaPessoas },
    { padrao: /^\/pessoa\/([^/]+)$/, render: (p, m) => V.pessoaDetalhe({ id: m[1], editar: p.editar }), nav: 'pessoas' },
    { padrao: /^\/compromissos$/, render: () => V.compromissos(), nav: 'mais' },
    { padrao: /^\/compromisso-novo$/, render: () => V.compromissoNovo(), nav: 'mais' },
    { padrao: /^\/agenda$/, render: () => V.agenda(), nav: 'mais' },
    { padrao: /^\/agenda-novo$/, render: () => V.agendaNovo(), nav: 'mais' },
    { padrao: /^\/relatorios$/, render: (p) => V.relatorios(p), nav: 'mais' },
    { padrao: /^\/assistente$/, render: () => V.assistente(App.chat), nav: 'mais', aoMontar: rolarChat },
    { padrao: /^\/mais$/, render: () => V.mais(), nav: 'mais' },
    { padrao: /^\/ajustes$/, render: () => V.ajustes(), nav: 'mais', aoMontar: montarAjustes },
  ];

  function parseHash() {
    const bruto = location.hash.replace(/^#/, '') || '/inicio';
    const [caminho, query] = bruto.split('?');
    const params = {};
    if (query) {
      for (const par of query.split('&')) {
        const [k, v] = par.split('=');
        params[decodeURIComponent(k)] = decodeURIComponent(v || '');
      }
    }
    return { caminho, params };
  }

  function render() {
    const { caminho, params } = parseHash();
    const rota = ROTAS.find((r) => r.padrao.test(caminho)) || ROTAS[0];
    const m = caminho.match(rota.padrao) || [];
    const principal = document.getElementById('conteudo');
    principal.innerHTML = rota.render(params, m);
    principal.scrollTop = 0;
    window.scrollTo(0, 0);

    document.querySelectorAll('.nav-item').forEach((el) => {
      el.classList.toggle('ativa', el.dataset.nav === rota.nav);
    });
    App.iaTravada = false;
    if (rota.aoMontar) rota.aoMontar(params, m);
  }

  /* --------------------- montagem específica de telas ------------------ */

  function montarRegistrar() {
    const campo = document.getElementById('campo-descricao');
    if (!campo) return;
    let timer = null;
    campo.addEventListener('input', () => {
      clearTimeout(timer);
      timer = setTimeout(() => analisarDescricao(campo.value), 350);
    });
    ['campo-categoria', 'campo-criticidade', 'campo-tipo'].forEach((id) => {
      const el = document.getElementById(id);
      if (el) el.addEventListener('change', () => { App.iaTravada = true; });
    });
  }

  function analisarDescricao(texto) {
    const painel = document.getElementById('painel-ia');
    if (!painel) return;
    if (!texto || texto.trim().length < 12) {
      painel.classList.add('oculto');
      return;
    }
    const a = IA.analisar(texto);
    painel.classList.remove('oculto');
    painel.innerHTML =
      `<div class="painel-ia-titulo">✨ Leitura da FalaIA</div>` +
      `<div class="painel-ia-chips">` +
      `<span class="chip">${U.escapeHTML(a.categoria.nome)}</span>` +
      `<span class="chip crit-${a.criticidade}">${a.rotuloCriticidade}</span>` +
      `<span class="chip">${a.sentimento.rotulo}</span>` +
      `<span class="chip">resposta em ${a.prazos.resposta}d</span>` +
      `</div>` +
      (a.avisos.length ? `<div class="painel-ia-avisos">${a.avisos.map((x) => `⚠️ ${U.escapeHTML(x)}`).join('<br>')}</div>` : '');

    if (!App.iaTravada) {
      const selCat = document.getElementById('campo-categoria');
      const selCrit = document.getElementById('campo-criticidade');
      const selTipo = document.getElementById('campo-tipo');
      if (selCat) selCat.value = a.categoria.id;
      if (selCrit) selCrit.value = String(a.criticidade);
      if (selTipo) selTipo.value = a.tipo;
    }
  }

  function montarBuscaDemandas() {
    const busca = document.getElementById('busca-demandas');
    if (busca) busca.addEventListener('change', () => {
      const { params } = parseHash();
      location.hash = `#/demandas?f=${params.f || 'abertas'}&q=${encodeURIComponent(busca.value)}`;
    });
  }

  function montarBuscaPessoas() {
    const busca = document.getElementById('busca-pessoas');
    if (busca) busca.addEventListener('change', () => {
      location.hash = `#/pessoas?q=${encodeURIComponent(busca.value)}`;
    });
  }

  function montarAjustes() {
    const arquivo = document.getElementById('arquivo-importar');
    if (arquivo) arquivo.addEventListener('change', async () => {
      const f = arquivo.files[0];
      if (!f) return;
      try {
        DB.importarJSON(await f.text());
        avisar('Backup restaurado com sucesso.');
        render();
      } catch (e) {
        avisar('Arquivo de backup inválido.');
      }
    });
  }

  function rolarChat() {
    const caixa = document.getElementById('chat-mensagens');
    if (caixa) caixa.scrollTop = caixa.scrollHeight;
  }

  /* ------------------------------- toasts ------------------------------ */

  function avisar(texto) {
    const t = document.getElementById('toast');
    t.textContent = texto;
    t.classList.add('visivel');
    clearTimeout(avisar._timer);
    avisar._timer = setTimeout(() => t.classList.remove('visivel'), 2600);
  }

  /* ------------------------------ formulários -------------------------- */

  function aoEnviarFormulario(e) {
    const form = e.target;
    if (!(form instanceof HTMLFormElement)) return;
    e.preventDefault();
    const dados = Object.fromEntries(new FormData(form).entries());

    if (form.id === 'form-atendimento') return salvarAtendimento(dados);
    if (form.id === 'form-tratativa') return salvarTratativa(form.dataset.demanda, dados, form);
    if (form.id === 'form-pessoa') return salvarPessoa(form.dataset.id, dados);
    if (form.id === 'form-compromisso') return salvarCompromisso(dados);
    if (form.id === 'form-agenda') return salvarAgenda(dados);
    if (form.id === 'form-comunicado') return gerarComunicado(dados);
    if (form.id === 'form-chat') return enviarChat(dados.pergunta, form);
    if (form.id === 'form-config') { DB.setConfig({ analista: dados.analista.trim() }); avisar('Salvo!'); return; }
    if (form.id === 'form-ia') {
      DB.setConfig({ ia: { modo: dados.modo, apiKey: dados.apiKey.trim(), modelo: dados.modelo } });
      avisar('Configuração da FalaIA salva.');
      return;
    }
  }

  function salvarAtendimento(dados) {
    const analise = IA.analisar(dados.descricao);
    const criticidade = Number(dados.criticidade) || analise.criticidade;
    const at = DB.add('atendimentos', {
      protocolo: DB.proximoProtocolo(),
      dataISO: U.agoraISO(),
      canal: dados.canal,
      tipo: dados.tipo,
      descricao: dados.descricao.trim(),
      comunidadeId: dados.comunidadeId,
      stakeholderId: dados.stakeholderId || null,
      categoriaId: dados.categoriaId,
      criticidade,
      sentimentoEscore: analise.sentimento.escore,
      sentimentoRotulo: analise.sentimento.rotulo,
      alertaEscalada: analise.avisos.some((a) => a.startsWith('Risco de escalada')),
      geo: dados.geo ? JSON.parse(dados.geo) : null,
    });

    // Reclamações e solicitações viram demanda com SLA automático.
    if (dados.tipo === 'reclamacao' || dados.tipo === 'solicitacao') {
      const prazos = IA.slaPorCriticidade(criticidade);
      const cat = IA.CATEGORIAS.find((c) => c.id === dados.categoriaId);
      const demanda = DB.add('demandas', {
        protocolo: at.protocolo,
        atendimentoId: at.id,
        titulo: tituloAutomatico(dados.descricao, cat),
        descricao: dados.descricao.trim(),
        categoriaId: dados.categoriaId,
        area: cat ? cat.area : 'Relações Comunitárias',
        comunidadeId: dados.comunidadeId,
        stakeholderId: dados.stakeholderId || null,
        criticidade,
        status: 'recebida',
        alertaEscalada: at.alertaEscalada,
        prazoRespostaISO: U.diasAFrente(prazos.resposta),
        prazoSolucaoISO: U.diasAFrente(prazos.solucao),
        historico: [],
      });
      DB.update('atendimentos', at.id, { demandaId: demanda.id });
    }
    location.hash = `#/confirmacao/${at.id}`;
  }

  function tituloAutomatico(descricao, cat) {
    const curto = descricao.trim().replace(/\s+/g, ' ');
    const base = curto.length > 60 ? curto.slice(0, 57) + '…' : curto;
    return cat && cat.id !== 'outros' ? `${cat.nome.split(',')[0].split(' e ')[0]}: ${base}` : base;
  }

  function salvarTratativa(demandaId, dados, form) {
    const d = DB.porId('demandas', demandaId);
    if (!d) return;
    const historico = d.historico || [];
    if (dados.texto && dados.texto.trim()) {
      historico.push({ dataISO: U.agoraISO(), texto: dados.texto.trim() });
    }
    DB.update('demandas', demandaId, {
      status: dados.status,
      respondida: form.querySelector('[name="respondida"]').checked,
      historico,
    });
    avisar('Demanda atualizada.');
    render();
  }

  function salvarPessoa(id, dados) {
    const registro = {
      nome: dados.nome.trim(),
      papel: dados.papel.trim(),
      organizacao: dados.organizacao.trim(),
      telefone: dados.telefone.trim(),
      comunidadeId: dados.comunidadeId,
      influencia: Number(dados.influencia),
      interesse: Number(dados.interesse),
      notas: dados.notas.trim(),
    };
    const salvo = id ? DB.update('stakeholders', id, registro) : DB.add('stakeholders', registro);
    avisar('Stakeholder salvo.');
    location.hash = `#/pessoa/${salvo.id}`;
  }

  function salvarCompromisso(dados) {
    DB.add('compromissos', {
      titulo: dados.titulo.trim(),
      origem: dados.origem,
      comunidadeId: dados.comunidadeId || null,
      responsavel: dados.responsavel.trim(),
      prazoISO: new Date(dados.prazo + 'T12:00:00').toISOString(),
      status: 'pendente',
      descricao: dados.descricao.trim(),
    });
    avisar('Compromisso registrado.');
    location.hash = '#/compromissos';
  }

  function salvarAgenda(dados) {
    DB.add('agenda', {
      titulo: dados.titulo.trim(),
      dataISO: new Date(dados.data + 'T09:00:00').toISOString(),
      tipo: dados.tipo,
      comunidadeId: dados.comunidadeId || null,
      notas: dados.notas.trim(),
      concluido: false,
    });
    avisar('Agendado.');
    location.hash = '#/agenda';
  }

  function gerarComunicado(dados) {
    const comunidade = DB.porId('comunidades', dados.comunidadeId);
    const texto = IA.gerarComunicado(dados.tipo, {
      comunidade: comunidade ? comunidade.nome : '',
      data: new Date(dados.data + 'T12:00:00').toLocaleDateString('pt-BR'),
      hora: dados.hora ? dados.hora.replace(':', 'h') : '',
      detalhe: dados.detalhe,
    });
    const saida = document.getElementById('saida-comunicado');
    saida.innerHTML =
      `<pre class="texto-gerado" id="texto-comunicado">${U.escapeHTML(texto)}</pre>` +
      `<div class="botoes">` +
      `<button class="btn-suave" data-action="copiar" data-alvo="texto-comunicado">📋 Copiar</button>` +
      `<button class="btn-primario" data-action="compartilhar" data-alvo="texto-comunicado">📤 Enviar</button>` +
      `</div>`;
    saida.scrollIntoView({ behavior: 'smooth' });
  }

  /* ------------------------------ chat FalaIA -------------------------- */

  function pushChat(de, texto) {
    App.chat.push({ de, texto });
    const caixa = document.getElementById('chat-mensagens');
    if (caixa) {
      const div = document.createElement('div');
      div.className = 'balao ' + (de === 'eu' ? 'eu' : 'ia');
      div.textContent = texto;
      caixa.appendChild(div);
      caixa.scrollTop = caixa.scrollHeight;
    }
  }

  async function enviarChat(pergunta, form) {
    pergunta = (pergunta || '').trim();
    if (!pergunta) return;
    if (form) form.reset();
    pushChat('eu', pergunta);

    const local = responderLocal(pergunta);
    if (local) {
      pushChat('ia', local);
      return;
    }
    const cfg = DB.getConfig();
    if (cfg.ia.modo === 'online' && cfg.ia.apiKey) {
      pushChat('ia', '⏳ Consultando o Claude…');
      try {
        const resposta = await consultarClaude(pergunta);
        App.chat.pop();
        const caixa = document.getElementById('chat-mensagens');
        if (caixa && caixa.lastElementChild) caixa.lastElementChild.remove();
        pushChat('ia', resposta);
      } catch (e) {
        App.chat.pop();
        const caixa = document.getElementById('chat-mensagens');
        if (caixa && caixa.lastElementChild) caixa.lastElementChild.remove();
        pushChat('ia', `Não consegui falar com a API (${e.message}). Verifique a chave e a conexão em Ajustes.`);
      }
    } else {
      pushChat('ia', 'No modo offline eu respondo sobre: demandas em risco, resumo de comunidades, relatórios, comunicados e modelos de resposta. Para perguntas livres, ative o modo online em Ajustes ✨.');
    }
  }

  /** Intents respondidas localmente, sem internet. */
  function responderLocal(perguntaBruta) {
    const p = U.normalizar(perguntaBruta);

    if (/(demanda|sla|prazo).*(risco|atras|vencen|estoura)|em risco/.test(p)) {
      const lista = ST.demandasEmRisco();
      if (!lista.length) return 'Nenhuma demanda com prazo em risco. ✅';
      return `Tenho ${lista.length} demanda(s) exigindo ação:\n\n` + lista.map((x) =>
        `• ${x.demanda.protocolo} — ${x.demanda.titulo}\n  ${x.sla.rotulo} · ${ST.nomeCategoria(x.demanda.categoriaId)}`
      ).join('\n') + '\n\nAbra a aba Demandas → "Em risco" para tratar.';
    }

    if (/quantas? demandas|demandas abertas/.test(p)) {
      const abertas = ST.demandasAbertas();
      return `Há ${abertas.length} demandas abertas: ` +
        Object.entries(abertas.reduce((m, d) => { m[d.status] = (m[d.status] || 0) + 1; return m; }, {}))
          .map(([s, n]) => `${n} ${ST.ROTULO_STATUS[s].toLowerCase()}`).join(', ') + '.';
    }

    const comunidade = DB.get('comunidades').find((c) => p.includes(U.normalizar(c.nome).replace(/^(comunidade|distrito de|vila do|assentamento) /, '')));
    if (comunidade && /resumo|como esta|situacao|risco/.test(p)) {
      const r = ST.riscoPorComunidade().find((x) => x.comunidade.id === comunidade.id);
      const abertas = ST.demandasAbertas().filter((d) => d.comunidadeId === comunidade.id);
      return `📍 ${comunidade.nome} (${comunidade.territorio})\n` +
        `Risco social: ${r.risco.nivel} (${r.risco.score}/100)\n` +
        `Fatores: ${r.risco.fatores.join('; ')}\n` +
        `Demandas abertas: ${abertas.length}` +
        (abertas.length ? '\n' + abertas.map((d) => `• ${d.protocolo} — ${d.titulo}`).join('\n') : '') +
        `\nAtendimentos (30d): ${r.atendimentos30d}`;
    }

    if (/relatorio|resumo (da |do )?(semana|mes|periodo)/.test(p)) {
      const dias = /semana/.test(p) ? 7 : /trimestre/.test(p) ? 90 : 30;
      return IA.gerarRelatorio(ST.dadosRelatorio(dias)) + '\n\n(Também disponível em Mais → Relatórios, com botões de envio.)';
    }

    if (/como responder|resposta para|modelo de resposta/.test(p)) {
      const cat = IA.classificarCategoria(perguntaBruta);
      return `Modelo de resposta para "${cat.nome}":\n\n` + IA.respostaSugerida({
        nome: null,
        protocolo: 'FC-AAAA-NNNN',
        categoriaId: cat.id,
        analista: DB.getConfig().analista,
      });
    }

    if (/comunicado/.test(p)) {
      const tipo = /detona/.test(p) ? 'detonacao' : /via|estrada|interrup/.test(p) ? 'interrupcao_via' : /reuniao|convite/.test(p) ? 'reuniao' : 'manutencao';
      const com = DB.get('comunidades').find((c) => p.includes(U.normalizar(c.nome).replace(/^(comunidade|distrito de|vila do|assentamento) /, '')));
      const data = /amanha/.test(p) ? new Date(Date.now() + 86400000).toLocaleDateString('pt-BR') : /hoje/.test(p) ? new Date().toLocaleDateString('pt-BR') : '__/__/____';
      const hora = (p.match(/(\d{1,2})\s*h/) || [])[1];
      return IA.gerarComunicado(tipo, {
        comunidade: com ? com.nome : '',
        data,
        hora: hora ? `${hora}h` : '',
      }) + '\n\n(Edite os campos e envie. Gerador completo em Mais → Relatórios.)';
    }

    if (/sem contato|esfriando|abandonad/.test(p)) {
      const lista = ST.stakeholdersSemContato(30);
      if (!lista.length) return 'Todos os stakeholders tiveram contato nos últimos 30 dias. 👏';
      return 'Relacionamentos esfriando:\n' + lista.map((x) => `• ${x.stakeholder.nome} — ${x.diasSemContato} dias sem contato`).join('\n');
    }

    if (/compromisso|condicionante/.test(p)) {
      const venc = ST.compromissosVencendo(14);
      if (!venc.length) return 'Nenhum compromisso vencendo nos próximos 14 dias. ✅';
      return 'Compromissos a vencer (14 dias):\n' + venc.map((x) => `• ${x.compromisso.titulo} — ${U.rotuloPrazo(x.compromisso.prazoISO)}`).join('\n');
    }

    if (/ajuda|o que voce faz|o que você faz|help/.test(p)) {
      return 'Posso ajudar com:\n• "Demandas em risco"\n• "Resumo da [comunidade]"\n• "Relatório da semana/mês"\n• "Como responder [tema]?"\n• "Comunicado de detonação para [comunidade] amanhã às 14h"\n• "Quem está sem contato?"\n• "Compromissos a vencer"';
    }

    return null;
  }

  /** Contexto compacto dos dados locais para o modo online. */
  function contextoParaClaude() {
    const d = ST.dadosRelatorio(30);
    const riscos = d.territorios.map((t) => `${t.nome}: ${t.nivel} (${t.score})`).join('; ');
    const emRisco = ST.demandasEmRisco().map((x) => `${x.demanda.protocolo} ${x.demanda.titulo} [${x.sla.rotulo}]`).join('; ');
    return `Dados atuais do analista (30 dias): ${d.totalAtendimentos} atendimentos; ${d.demandasAbertas} demandas abertas; ` +
      `SLA no prazo ${Math.round(d.percSlaNoPrazo * 100)}%; tema top: ${d.temaTop ? d.temaTop.nome : 'n/d'}; ` +
      `risco por comunidade: ${riscos}; demandas em risco: ${emRisco || 'nenhuma'}.`;
  }

  async function consultarClaude(pergunta) {
    const cfg = DB.getConfig().ia;
    const sistema =
      'Você é a FalaIA, copiloto de analistas de relacionamento com comunidades em mineração (Brasil). ' +
      'Responda em português, com objetividade e empatia, em texto puro (sem markdown). ' +
      'Use os dados fornecidos; não invente números. Sugira ações práticas de campo quando fizer sentido.\n\n' +
      contextoParaClaude();

    const resp = await fetch('https://api.anthropic.com/v1/messages', {
      method: 'POST',
      headers: {
        'content-type': 'application/json',
        'x-api-key': cfg.apiKey,
        'anthropic-version': '2023-06-01',
        'anthropic-dangerous-direct-browser-access': 'true',
      },
      body: JSON.stringify({
        model: cfg.modelo || 'claude-opus-4-8',
        max_tokens: 4096, // chat móvel: respostas deliberadamente curtas
        system: sistema,
        messages: App.chat
          .filter((m) => !m.texto.startsWith('⏳'))
          .slice(-10)
          .map((m) => ({ role: m.de === 'eu' ? 'user' : 'assistant', content: m.texto })),
      }),
    });
    if (!resp.ok) {
      const corpo = await resp.json().catch(() => null);
      throw new Error(corpo && corpo.error ? corpo.error.type : `HTTP ${resp.status}`);
    }
    const dados = await resp.json();
    if (dados.stop_reason === 'refusal') {
      return 'A consulta foi recusada pelos filtros de segurança do modelo. Reformule a pergunta.';
    }
    return dados.content.filter((b) => b.type === 'text').map((b) => b.text).join('\n') || 'Sem resposta.';
  }

  /* --------------------------- ações (delegação) ----------------------- */

  const ACOES = {
    async copiar(el) {
      const alvo = document.getElementById(el.dataset.alvo);
      if (alvo && await U.copiar(alvo.textContent)) avisar('Copiado! 📋');
    },
    async compartilhar(el) {
      const alvo = document.getElementById(el.dataset.alvo);
      if (!alvo) return;
      const ok = await U.compartilhar('Fala Comunidade', alvo.textContent);
      if (ok && !navigator.share) avisar('Copiado para colar no WhatsApp 📋');
    },
    ditar() {
      const Reconhecedor = self.SpeechRecognition || self.webkitSpeechRecognition;
      const campo = document.getElementById('campo-descricao');
      const btn = document.getElementById('btn-mic');
      if (!Reconhecedor) { avisar('Ditado por voz não disponível neste navegador.'); return; }
      if (App.reconhecimento) {
        App.reconhecimento.stop();
        return;
      }
      const rec = new Reconhecedor();
      rec.lang = 'pt-BR';
      rec.continuous = true;
      rec.interimResults = false;
      rec.onresult = (e) => {
        for (let i = e.resultIndex; i < e.results.length; i++) {
          if (e.results[i].isFinal) {
            campo.value = (campo.value ? campo.value.trim() + ' ' : '') + e.results[i][0].transcript.trim();
          }
        }
        campo.dispatchEvent(new Event('input'));
      };
      rec.onend = () => { App.reconhecimento = null; btn.classList.remove('gravando'); };
      rec.onerror = () => { avisar('Não consegui ouvir. Tente de novo.'); };
      App.reconhecimento = rec;
      btn.classList.add('gravando');
      rec.start();
      avisar('🎤 Ouvindo… toque de novo para parar.');
    },
    'capturar-geo'() {
      const status = document.getElementById('geo-status');
      if (!navigator.geolocation) { status.textContent = 'GPS indisponível.'; return; }
      status.textContent = 'Obtendo localização…';
      navigator.geolocation.getCurrentPosition(
        (pos) => {
          document.getElementById('campo-geo').value = JSON.stringify({
            lat: Number(pos.coords.latitude.toFixed(5)),
            lng: Number(pos.coords.longitude.toFixed(5)),
          });
          status.textContent = `✅ ${pos.coords.latitude.toFixed(4)}, ${pos.coords.longitude.toFixed(4)}`;
        },
        () => { status.textContent = 'Sem permissão de localização.'; },
        { timeout: 8000 }
      );
    },
    'concluir-compromisso'(el) {
      DB.update('compromissos', el.dataset.id, { status: 'concluido' });
      avisar('Compromisso concluído. 🎉');
      render();
    },
    'concluir-agenda'(el) {
      DB.update('agenda', el.dataset.id, { concluido: true });
      render();
    },
    'sugestao-chat'(el) {
      enviarChat(el.textContent);
    },
    'baixar-relatorio'(el) {
      const dias = Number(el.dataset.dias) || 30;
      const texto = IA.gerarRelatorio(ST.dadosRelatorio(dias));
      U.baixarArquivo(`relatorio-fala-comunidade-${dias}d.txt`, texto);
    },
    'exportar-csv'(el) {
      const col = el.dataset.colecao;
      const csv = DB.exportarCSV(col);
      if (!csv) { avisar('Nada para exportar.'); return; }
      U.baixarArquivo(`fala-comunidade-${col}.csv`, csv, 'text/csv;charset=utf-8');
    },
    'exportar-json'() {
      U.baixarArquivo('fala-comunidade-backup.json', DB.exportarJSON(), 'application/json');
    },
    'recarregar-demo'() {
      if (confirm('Substituir os dados atuais pelos dados de demonstração?')) {
        DB.limparTudo();
        DB.seedDemo();
        avisar('Dados de demonstração recarregados.');
        render();
      }
    },
    'limpar-tudo'() {
      if (confirm('Apagar TODOS os dados deste dispositivo? Faça um backup antes.')) {
        DB.limparTudo();
        avisar('Dados apagados.');
        location.hash = '#/inicio';
        render();
      }
    },
  };

  function aoClicar(e) {
    const el = e.target.closest('[data-action]');
    if (!el) return;
    const acao = ACOES[el.dataset.action];
    if (acao) {
      e.preventDefault();
      acao(el);
    }
  }

  /* ------------------------------ bootstrap ---------------------------- */

  function iniciar() {
    DB.init();
    document.addEventListener('click', aoClicar);
    document.addEventListener('submit', aoEnviarFormulario);
    window.addEventListener('hashchange', render);
    render();

    if ('serviceWorker' in navigator) {
      navigator.serviceWorker.register('./sw.js').catch((e) => console.warn('SW não registrado', e));
    }
    window.addEventListener('online', () => avisar('Conexão restabelecida.'));
    window.addEventListener('offline', () => avisar('Sem internet — o app segue funcionando offline. 📴'));
  }

  document.addEventListener('DOMContentLoaded', iniciar);
})();
