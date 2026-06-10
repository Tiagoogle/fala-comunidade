/* Fala Comunidade — FalaViews
 * Funções de renderização (HTML por rota). Leitura via FalaDB/FalaStats;
 * os eventos são tratados por delegação em app.js (atributos data-action).
 */
(function (raiz) {
  'use strict';

  const U = raiz.FalaUtil;
  const esc = U.escapeHTML;
  const DB = () => raiz.FalaDB;
  const ST = () => raiz.FalaStats;
  const IA = () => raiz.FalaIA;

  /* ----------------------------- helpers ----------------------------- */

  function nomeComunidade(id) {
    const c = DB().porId('comunidades', id);
    return c ? c.nome : 'Sem comunidade';
  }

  function nomeStakeholder(id) {
    const s = id && DB().porId('stakeholders', id);
    return s ? s.nome : null;
  }

  function chipCriticidade(n) {
    const rot = IA().ROTULO_CRITICIDADE[n] || '—';
    return `<span class="chip crit-${n}">${rot}</span>`;
  }

  function chipStatus(status) {
    return `<span class="chip st-${status}">${ST().ROTULO_STATUS[status] || status}</span>`;
  }

  function chipSLA(sla) {
    if (sla.fase === 'concluida') return '';
    const cls = sla.estourado ? 'sla-ruim' : sla.urgente ? 'sla-alerta' : 'sla-ok';
    return `<span class="chip ${cls}">⏱ ${esc(sla.rotulo)}</span>`;
  }

  function chipRisco(risco) {
    const cls = risco.nivel === 'Alto' ? 'risco-alto' : risco.nivel === 'Atenção' ? 'risco-medio' : 'risco-baixo';
    return `<span class="chip ${cls}">${risco.nivel} · ${risco.score}</span>`;
  }

  function opcoesComunidades(selecionada) {
    return DB().get('comunidades')
      .map((c) => `<option value="${c.id}" ${c.id === selecionada ? 'selected' : ''}>${esc(c.nome)}</option>`)
      .join('');
  }

  function opcoesCategorias(selecionada) {
    return IA().CATEGORIAS
      .map((c) => `<option value="${c.id}" ${c.id === selecionada ? 'selected' : ''}>${esc(c.nome)}</option>`)
      .join('');
  }

  function vazioMsg(texto) {
    return `<div class="vazio">${esc(texto)}</div>`;
  }

  /* ----------------------------- Início ------------------------------ */

  function inicio() {
    const cfg = DB().getConfig();
    const hoje = new Date();
    const saudacao = hoje.getHours() < 12 ? 'Bom dia' : hoje.getHours() < 18 ? 'Boa tarde' : 'Boa noite';
    const emRisco = ST().demandasEmRisco();
    const riscos = ST().riscoPorComunidade();
    const riscoAlto = riscos.filter((r) => r.risco.nivel === 'Alto');
    const ats30 = ST().atendimentosNoPeriodo(30);
    const abertas = ST().demandasAbertas();
    const compVenc = ST().compromissosVencendo(7);
    const temas = ST().temasEmAlta(30).slice(0, 4);
    const agendaHoje = DB().get('agenda')
      .filter((a) => !a.concluido && U.diasAte(a.dataISO) <= 1)
      .sort((a, b) => new Date(a.dataISO) - new Date(b.dataISO));
    const semContato = ST().stakeholdersSemContato(30);

    const alertas = [];
    riscoAlto.forEach((r) => alertas.push({
      icone: '🔴', texto: `Risco social ALTO em ${r.comunidade.nome}: ${r.risco.fatores[0]}.`, link: '#/relatorios',
    }));
    emRisco.slice(0, 3).forEach((x) => alertas.push({
      icone: x.sla.estourado ? '⏰' : '⚠️',
      texto: `${x.demanda.protocolo} · ${x.demanda.titulo} — ${x.sla.rotulo}.`,
      link: `#/demanda/${x.demanda.id}`,
    }));
    compVenc.slice(0, 2).forEach((x) => alertas.push({
      icone: '🤝', texto: `Compromisso "${x.compromisso.titulo}" ${U.rotuloPrazo(x.compromisso.prazoISO)}.`, link: '#/compromissos',
    }));

    return `
    <section class="saudacao">
      <h2>${saudacao}${cfg.analista ? ', ' + esc(cfg.analista.split(' ')[0]) : ''}!</h2>
      <p class="sub">${esc(U.fmtDataExtensa(U.agoraISO()))}</p>
    </section>

    ${alertas.length ? `
    <section class="card alertas">
      <h3>⚡ Prioridades de hoje</h3>
      ${alertas.map((a) => `<a class="alerta" href="${a.link}"><span>${a.icone}</span><span>${esc(a.texto)}</span></a>`).join('')}
    </section>` : ''}

    <section class="kpis">
      <a class="kpi" href="#/demandas"><strong>${abertas.length}</strong><span>demandas abertas</span></a>
      <a class="kpi ${emRisco.length ? 'kpi-ruim' : ''}" href="#/demandas?f=risco"><strong>${emRisco.length}</strong><span>SLA em risco</span></a>
      <a class="kpi" href="#/relatorios"><strong>${ats30.length}</strong><span>atendimentos 30d</span></a>
      <a class="kpi" href="#/compromissos"><strong>${compVenc.length}</strong><span>compromissos ≤7d</span></a>
    </section>

    <section class="card">
      <h3>🗺️ Risco social por comunidade</h3>
      ${riscos.map((r) => `
        <div class="linha-risco">
          <div class="linha-risco-info">
            <strong>${esc(r.comunidade.nome)}</strong>
            <small>${esc(r.comunidade.territorio)} · ${U.plural(r.abertas, 'demanda aberta', 'demandas abertas')}</small>
          </div>
          <div class="linha-risco-medida">
            <div class="barra"><div class="barra-fill nivel-${r.risco.nivel === 'Alto' ? 'alto' : r.risco.nivel === 'Atenção' ? 'medio' : 'baixo'}" style="width:${r.risco.score}%"></div></div>
            ${chipRisco(r.risco)}
          </div>
        </div>`).join('')}
    </section>

    <section class="card">
      <h3>📈 Temas em alta (30 dias)</h3>
      ${temas.length ? temas.map((t) => `
        <div class="linha-tema">
          <span>${esc(t.nome)}</span>
          <span class="tema-qtd">${t.qtd} ${t.delta > 0 ? `<em class="delta-sobe">▲ ${t.delta}</em>` : t.delta < 0 ? `<em class="delta-desce">▼ ${-t.delta}</em>` : ''}</span>
        </div>`).join('') : vazioMsg('Sem registros no período.')}
    </section>

    <section class="card">
      <h3>📅 Hoje e amanhã</h3>
      ${agendaHoje.length ? agendaHoje.map((a) => `
        <div class="linha-agenda">
          <span class="agenda-icone">${a.tipo === 'visita' ? '🚙' : '👥'}</span>
          <div><strong>${esc(a.titulo)}</strong><small>${esc(U.fmtDataExtensa(a.dataISO))}${a.comunidadeId ? ' · ' + esc(nomeComunidade(a.comunidadeId)) : ''}</small></div>
        </div>`).join('') : vazioMsg('Nada agendado. Bom momento para visitas preventivas.')}
      <a class="link-mais" href="#/agenda">Ver agenda completa →</a>
    </section>

    ${semContato.length ? `
    <section class="card">
      <h3>🤝 Relacionamento esfriando</h3>
      ${semContato.slice(0, 3).map((x) => `
        <a class="linha-agenda" href="#/pessoa/${x.stakeholder.id}">
          <span class="agenda-icone">👤</span>
          <div><strong>${esc(x.stakeholder.nome)}</strong><small>sem contato há ${x.diasSemContato} dias · ${esc(nomeComunidade(x.stakeholder.comunidadeId))}</small></div>
        </a>`).join('')}
    </section>` : ''}`;
  }

  /* ---------------------------- Registrar ---------------------------- */

  function registrar(params) {
    const stk = params.stk ? DB().porId('stakeholders', params.stk) : null;
    return `
    <section class="card">
      <h2>➕ Registrar atendimento</h2>
      <p class="sub">Descreva ou dite o relato. A FalaIA classifica, mede a criticidade e calcula o prazo automaticamente.</p>
      <form id="form-atendimento" autocomplete="off">
        <div class="campo-texto-ia">
          <textarea id="campo-descricao" name="descricao" rows="5" required
            placeholder="Ex.: Dona Maria, da Boa Vista, reclamou da poeira na estrada e disse que as crianças estão tossindo…"></textarea>
          <button type="button" class="btn-mic" id="btn-mic" data-action="ditar" title="Ditar por voz">🎤</button>
        </div>

        <div id="painel-ia" class="painel-ia oculto" aria-live="polite"></div>

        <label>Comunidade
          <select name="comunidadeId">${opcoesComunidades(stk ? stk.comunidadeId : null)}</select>
        </label>

        <label>Pessoa atendida (stakeholder)
          <select name="stakeholderId">
            <option value="">— não identificado / novo —</option>
            ${DB().get('stakeholders').map((s) => `<option value="${s.id}" ${stk && stk.id === s.id ? 'selected' : ''}>${esc(s.nome)} · ${esc(s.papel)}</option>`).join('')}
          </select>
        </label>

        <div class="grade-2">
          <label>Canal
            <select name="canal">
              <option value="presencial">Presencial / campo</option>
              <option value="whatsapp">WhatsApp</option>
              <option value="telefone">Telefone</option>
              <option value="0800">0800 / Ouvidoria</option>
              <option value="reuniao">Reunião</option>
            </select>
          </label>
          <label>Tipo
            <select name="tipo" id="campo-tipo">
              <option value="informacao">Informação</option>
              <option value="solicitacao">Solicitação</option>
              <option value="reclamacao">Reclamação</option>
              <option value="elogio">Elogio</option>
            </select>
          </label>
        </div>

        <div class="grade-2">
          <label>Categoria (IA)
            <select name="categoriaId" id="campo-categoria">${opcoesCategorias('outros')}</select>
          </label>
          <label>Criticidade (IA)
            <select name="criticidade" id="campo-criticidade">
              ${[1, 2, 3, 4, 5].map((n) => `<option value="${n}" ${n === 2 ? 'selected' : ''}>${n} — ${IA().ROTULO_CRITICIDADE[n]}</option>`).join('')}
            </select>
          </label>
        </div>

        <div class="linha-geo">
          <button type="button" class="btn-suave" data-action="capturar-geo">📍 Marcar localização</button>
          <span id="geo-status" class="sub"></span>
          <input type="hidden" name="geo" id="campo-geo">
        </div>

        <button type="submit" class="btn-primario">Salvar atendimento</button>
      </form>
    </section>`;
  }

  function confirmacao(params) {
    const at = DB().porId('atendimentos', params.id);
    if (!at) return vazioMsg('Atendimento não encontrado.');
    const demanda = at.demandaId ? DB().porId('demandas', at.demandaId) : null;
    const resposta = demanda ? IA().respostaSugerida({
      nome: nomeStakeholder(at.stakeholderId),
      protocolo: demanda.protocolo,
      categoriaId: demanda.categoriaId,
      prazoSolucaoISO: demanda.prazoSolucaoISO,
      analista: DB().getConfig().analista,
    }) : null;

    return `
    <section class="card confirmacao">
      <div class="confirma-icone">✅</div>
      <h2>Registrado em segundos!</h2>
      <p class="protocolo">Protocolo <strong>${esc(at.protocolo)}</strong></p>
      <p>${esc(ST().nomeCategoria(at.categoriaId))} · ${chipCriticidade(at.criticidade)}</p>
      ${demanda ? `
        <div class="aviso-demanda">
          📌 Demanda criada automaticamente para <strong>${esc(demanda.area)}</strong><br>
          Prazo de resposta: <strong>${U.fmtData(demanda.prazoRespostaISO)}</strong> · Solução: <strong>${U.fmtData(demanda.prazoSolucaoISO)}</strong>
        </div>` : '<p class="sub">Registro informativo — não gera demanda.</p>'}
    </section>

    ${resposta ? `
    <section class="card">
      <h3>💬 Resposta sugerida pela FalaIA</h3>
      <pre class="texto-gerado" id="texto-resposta">${esc(resposta)}</pre>
      <div class="botoes">
        <button class="btn-suave" data-action="copiar" data-alvo="texto-resposta">📋 Copiar</button>
        <button class="btn-primario" data-action="compartilhar" data-alvo="texto-resposta">📤 Enviar (WhatsApp…)</button>
      </div>
    </section>` : ''}

    <div class="botoes coluna">
      ${demanda ? `<a class="btn-suave" href="#/demanda/${demanda.id}">Ver demanda</a>` : ''}
      <a class="btn-suave" href="#/registrar">Registrar outro</a>
      <a class="btn-suave" href="#/inicio">Voltar ao início</a>
    </div>`;
  }

  /* ---------------------------- Demandas ----------------------------- */

  function demandas(params) {
    const filtro = params.f || 'abertas';
    let lista = DB().get('demandas').slice();
    if (filtro === 'abertas') lista = lista.filter((d) => ST().STATUS_ABERTOS.includes(d.status));
    if (filtro === 'risco') lista = ST().demandasEmRisco().map((x) => x.demanda);
    if (filtro === 'encerradas') lista = lista.filter((d) => !ST().STATUS_ABERTOS.includes(d.status));
    if (params.q) {
      const q = U.normalizar(params.q);
      lista = lista.filter((d) => U.normalizar(`${d.titulo} ${d.protocolo} ${d.descricao}`).includes(q));
    }
    lista.sort((a, b) => (b.criticidade - a.criticidade) || (new Date(a.prazoRespostaISO) - new Date(b.prazoRespostaISO)));

    const aba = (id, rotulo) => `<a class="aba ${filtro === id ? 'ativa' : ''}" href="#/demandas?f=${id}">${rotulo}</a>`;
    return `
    <section>
      <h2>📋 Demandas</h2>
      <div class="abas">${aba('abertas', 'Abertas')}${aba('risco', '⏱ Em risco')}${aba('encerradas', 'Encerradas')}${aba('todas', 'Todas')}</div>
      <input class="busca" type="search" id="busca-demandas" placeholder="Buscar por título, protocolo…" value="${esc(params.q || '')}">
      ${lista.length ? lista.map((d) => {
        const sla = ST().situacaoSLA(d);
        return `
        <a class="card item-demanda" href="#/demanda/${d.id}">
          <div class="item-demanda-topo">
            <span class="protocolo-mini">${esc(d.protocolo)}</span>
            ${d.alertaEscalada ? '<span class="chip risco-alto">🔥 escalada</span>' : ''}
            ${chipCriticidade(d.criticidade)}
          </div>
          <strong>${esc(d.titulo)}</strong>
          <small>${esc(nomeComunidade(d.comunidadeId))} · ${esc(d.area)}</small>
          <div class="item-demanda-rodape">${chipStatus(d.status)} ${chipSLA(sla)}</div>
        </a>`;
      }).join('') : vazioMsg('Nenhuma demanda neste filtro.')}
    </section>`;
  }

  function demandaDetalhe(params) {
    const d = DB().porId('demandas', params.id);
    if (!d) return vazioMsg('Demanda não encontrada.');
    const sla = ST().situacaoSLA(d);
    const resposta = IA().respostaSugerida({
      nome: nomeStakeholder(d.stakeholderId),
      protocolo: d.protocolo,
      categoriaId: d.categoriaId,
      prazoSolucaoISO: d.prazoSolucaoISO,
      analista: DB().getConfig().analista,
    });
    const historico = (d.historico || []).slice().sort((a, b) => new Date(b.dataISO) - new Date(a.dataISO));

    return `
    <section class="card">
      <div class="item-demanda-topo">
        <span class="protocolo-mini">${esc(d.protocolo)}</span>
        ${d.alertaEscalada ? '<span class="chip risco-alto">🔥 risco de escalada</span>' : ''}
        ${chipCriticidade(d.criticidade)}
      </div>
      <h2>${esc(d.titulo)}</h2>
      <p class="sub">${esc(nomeComunidade(d.comunidadeId))} · ${esc(d.area)} · aberta em ${U.fmtData(d.criadoISO)}</p>
      <p>${esc(d.descricao)}</p>
      <div class="item-demanda-rodape">${chipStatus(d.status)} ${chipSLA(sla)}</div>
      <div class="prazos">
        <span>Resposta até <strong>${U.fmtData(d.prazoRespostaISO)}</strong></span>
        <span>Solução até <strong>${U.fmtData(d.prazoSolucaoISO)}</strong></span>
      </div>
    </section>

    <section class="card">
      <h3>🔄 Atualizar</h3>
      <form id="form-tratativa" data-demanda="${d.id}">
        <label>Status
          <select name="status">
            ${Object.entries(ST().ROTULO_STATUS).map(([v, r]) => `<option value="${v}" ${v === d.status ? 'selected' : ''}>${r}</option>`).join('')}
          </select>
        </label>
        <label>Nova tratativa / andamento
          <textarea name="texto" rows="2" placeholder="Ex.: Vistoria agendada para sexta com a Engenharia…"></textarea>
        </label>
        <label class="check"><input type="checkbox" name="respondida" ${d.respondida ? 'checked' : ''}> Comunidade já recebeu a 1ª resposta</label>
        <button type="submit" class="btn-primario">Salvar atualização</button>
      </form>
    </section>

    <section class="card">
      <h3>💬 Resposta sugerida (FalaIA)</h3>
      <pre class="texto-gerado" id="texto-resposta">${esc(resposta)}</pre>
      <div class="botoes">
        <button class="btn-suave" data-action="copiar" data-alvo="texto-resposta">📋 Copiar</button>
        <button class="btn-primario" data-action="compartilhar" data-alvo="texto-resposta">📤 Enviar</button>
      </div>
    </section>

    <section class="card">
      <h3>🗂 Linha do tempo</h3>
      ${historico.length ? historico.map((h) => `
        <div class="evento"><small>${U.fmtDataHora(h.dataISO)}</small><p>${esc(h.texto)}</p></div>`).join('') : vazioMsg('Sem tratativas registradas ainda.')}
    </section>`;
  }

  /* ----------------------------- Pessoas ----------------------------- */

  function pessoas(params) {
    let lista = DB().get('stakeholders').slice();
    if (params.q) {
      const q = U.normalizar(params.q);
      lista = lista.filter((s) => U.normalizar(`${s.nome} ${s.papel} ${s.organizacao}`).includes(q));
    }
    const semContato = new Map(ST().stakeholdersSemContato(30).map((x) => [x.stakeholder.id, x.diasSemContato]));
    lista.sort((a, b) => (b.influencia + b.interesse) - (a.influencia + a.interesse));

    return `
    <section>
      <div class="titulo-acao">
        <h2>👥 Stakeholders</h2>
        <a class="btn-suave" href="#/pessoa/nova">+ Novo</a>
      </div>
      <input class="busca" type="search" id="busca-pessoas" placeholder="Buscar por nome, papel…" value="${esc(params.q || '')}">
      ${lista.map((s) => `
        <a class="card item-pessoa" href="#/pessoa/${s.id}">
          <div class="avatar">${esc(s.nome.charAt(0))}</div>
          <div class="item-pessoa-info">
            <strong>${esc(s.nome)}</strong>
            <small>${esc(s.papel)}${s.organizacao ? ' · ' + esc(s.organizacao) : ''}</small>
            <small>${esc(nomeComunidade(s.comunidadeId))}</small>
          </div>
          <div class="item-pessoa-chips">
            <span class="chip quad">${ST().quadranteStakeholder(s)}</span>
            ${semContato.has(s.id) ? `<span class="chip sla-alerta">😶 ${semContato.get(s.id)}d sem contato</span>` : ''}
          </div>
        </a>`).join('') || vazioMsg('Nenhum stakeholder cadastrado.')}
    </section>`;
  }

  function pessoaForm(s) {
    const ehNova = !s;
    s = s || { nome: '', papel: '', organizacao: '', telefone: '', influencia: 3, interesse: 3, notas: '', comunidadeId: null };
    return `
    <section class="card">
      <h2>${ehNova ? '👤 Novo stakeholder' : '✏️ Editar stakeholder'}</h2>
      <form id="form-pessoa" ${s.id ? `data-id="${s.id}"` : ''}>
        <label>Nome <input name="nome" required value="${esc(s.nome)}"></label>
        <label>Papel na comunidade <input name="papel" placeholder="Ex.: Presidente da associação" value="${esc(s.papel)}"></label>
        <label>Organização <input name="organizacao" value="${esc(s.organizacao || '')}"></label>
        <div class="grade-2">
          <label>Telefone <input name="telefone" inputmode="tel" value="${esc(s.telefone || '')}"></label>
          <label>Comunidade <select name="comunidadeId">${opcoesComunidades(s.comunidadeId)}</select></label>
        </div>
        <label>Influência: <output id="out-inf">${s.influencia}</output>/5
          <input type="range" name="influencia" min="1" max="5" value="${s.influencia}" oninput="document.getElementById('out-inf').value=this.value">
        </label>
        <label>Interesse: <output id="out-int">${s.interesse}</output>/5
          <input type="range" name="interesse" min="1" max="5" value="${s.interesse}" oninput="document.getElementById('out-int').value=this.value">
        </label>
        <label>Notas de relacionamento <textarea name="notas" rows="3">${esc(s.notas || '')}</textarea></label>
        <button type="submit" class="btn-primario">Salvar</button>
      </form>
    </section>`;
  }

  function pessoaDetalhe(params) {
    if (params.id === 'nova') return pessoaForm(null);
    const s = DB().porId('stakeholders', params.id);
    if (!s) return vazioMsg('Stakeholder não encontrado.');
    if (params.editar) return pessoaForm(s);

    const historico = DB().get('atendimentos')
      .filter((a) => a.stakeholderId === s.id)
      .sort((a, b) => new Date(b.dataISO) - new Date(a.dataISO));
    const ultimo = historico[0];

    return `
    <section class="card">
      <div class="pessoa-cabecalho">
        <div class="avatar grande">${esc(s.nome.charAt(0))}</div>
        <div>
          <h2>${esc(s.nome)}</h2>
          <p class="sub">${esc(s.papel)}${s.organizacao ? ' · ' + esc(s.organizacao) : ''}</p>
          <p class="sub">${esc(nomeComunidade(s.comunidadeId))}${s.telefone ? ' · 📞 ' + esc(s.telefone) : ''}</p>
        </div>
      </div>
      <div class="item-demanda-rodape">
        <span class="chip quad">${ST().quadranteStakeholder(s)}</span>
        <span class="chip">Influência ${s.influencia}/5</span>
        <span class="chip">Interesse ${s.interesse}/5</span>
      </div>
      ${ultimo ? `<p class="sub">Último contato: ${U.fmtData(ultimo.dataISO)} (${esc(ST().nomeCategoria(ultimo.categoriaId))})</p>` : '<p class="sub">Sem atendimentos registrados.</p>'}
      ${s.notas ? `<p class="notas">📝 ${esc(s.notas)}</p>` : ''}
      <div class="botoes">
        <a class="btn-primario" href="#/registrar?stk=${s.id}">➕ Registrar atendimento</a>
        <a class="btn-suave" href="#/pessoa/${s.id}?editar=1">✏️ Editar</a>
      </div>
    </section>

    <section class="card">
      <h3>🗂 Histórico de interações</h3>
      ${historico.length ? historico.map((a) => `
        <div class="evento">
          <small>${U.fmtData(a.dataISO)} · ${esc(a.canal)} · ${esc(ST().nomeCategoria(a.categoriaId))}</small>
          <p>${esc(a.descricao)}</p>
        </div>`).join('') : vazioMsg('Nenhuma interação registrada.')}
    </section>`;
  }

  /* --------------------------- Compromissos -------------------------- */

  function compromissos() {
    const lista = DB().get('compromissos').slice()
      .sort((a, b) => (a.status === 'concluido') - (b.status === 'concluido') || new Date(a.prazoISO) - new Date(b.prazoISO));
    const pend = lista.filter((c) => c.status !== 'concluido');
    const atrasados = pend.filter((c) => U.diasAte(c.prazoISO) < 0).length;
    const ICONE_ORIGEM = { condicionante: '⚖️', acordo: '🤝', reuniao: '👥', plano: '📋' };

    return `
    <section>
      <div class="titulo-acao">
        <h2>🤝 Compromissos</h2>
        <a class="btn-suave" href="#/compromisso-novo">+ Novo</a>
      </div>
      <p class="sub">${pend.length} pendentes${atrasados ? ` · <strong class="texto-ruim">${atrasados} em atraso</strong>` : ''} — condicionantes e promessas feitas à comunidade.</p>
      ${lista.map((c) => {
        const dias = U.diasAte(c.prazoISO);
        const concluido = c.status === 'concluido';
        return `
        <div class="card item-compromisso ${concluido ? 'concluido' : ''}">
          <div class="item-demanda-topo">
            <span>${ICONE_ORIGEM[c.origem] || '📌'} ${esc(c.origem)}</span>
            ${concluido ? '<span class="chip st-encerrada">Concluído</span>'
              : `<span class="chip ${dias < 0 ? 'sla-ruim' : dias <= 7 ? 'sla-alerta' : 'sla-ok'}">${esc(U.rotuloPrazo(c.prazoISO))}</span>`}
          </div>
          <strong>${esc(c.titulo)}</strong>
          <small>${c.comunidadeId ? esc(nomeComunidade(c.comunidadeId)) + ' · ' : ''}resp.: ${esc(c.responsavel)}</small>
          ${c.descricao ? `<p class="sub">${esc(c.descricao)}</p>` : ''}
          ${!concluido ? `<button class="btn-suave" data-action="concluir-compromisso" data-id="${c.id}">✔ Marcar como concluído</button>` : ''}
        </div>`;
      }).join('') || vazioMsg('Nenhum compromisso registrado.')}
    </section>`;
  }

  function compromissoNovo() {
    return `
    <section class="card">
      <h2>🤝 Novo compromisso</h2>
      <form id="form-compromisso">
        <label>Título <input name="titulo" required placeholder="Ex.: Reparar mata-burro da estrada da Boa Vista"></label>
        <div class="grade-2">
          <label>Origem
            <select name="origem">
              <option value="acordo">Acordo com a comunidade</option>
              <option value="condicionante">Condicionante de licença</option>
              <option value="reuniao">Reunião</option>
              <option value="plano">Plano interno</option>
            </select>
          </label>
          <label>Prazo <input type="date" name="prazo" required></label>
        </div>
        <label>Comunidade <select name="comunidadeId"><option value="">— geral —</option>${opcoesComunidades()}</select></label>
        <label>Área responsável <input name="responsavel" required placeholder="Ex.: Meio Ambiente"></label>
        <label>Descrição <textarea name="descricao" rows="2"></textarea></label>
        <button type="submit" class="btn-primario">Salvar compromisso</button>
      </form>
    </section>`;
  }

  /* ------------------------------ Agenda ----------------------------- */

  function agenda() {
    const lista = DB().get('agenda').slice()
      .sort((a, b) => a.concluido - b.concluido || new Date(a.dataISO) - new Date(b.dataISO));
    return `
    <section>
      <div class="titulo-acao">
        <h2>📅 Agenda de campo</h2>
        <a class="btn-suave" href="#/agenda-novo">+ Novo</a>
      </div>
      ${lista.map((a) => `
        <div class="card linha-agenda ${a.concluido ? 'concluido' : ''}">
          <span class="agenda-icone">${a.tipo === 'visita' ? '🚙' : a.tipo === 'evento' ? '🎉' : '👥'}</span>
          <div class="cresce">
            <strong>${esc(a.titulo)}</strong>
            <small>${esc(U.fmtDataExtensa(a.dataISO))}${a.comunidadeId ? ' · ' + esc(nomeComunidade(a.comunidadeId)) : ''}</small>
            ${a.notas ? `<small>📝 ${esc(a.notas)}</small>` : ''}
          </div>
          ${!a.concluido ? `<button class="btn-suave" data-action="concluir-agenda" data-id="${a.id}">✔</button>` : ''}
        </div>`).join('') || vazioMsg('Agenda vazia.')}
    </section>`;
  }

  function agendaNovo() {
    return `
    <section class="card">
      <h2>📅 Novo item de agenda</h2>
      <form id="form-agenda">
        <label>Título <input name="titulo" required placeholder="Ex.: Visita à Vila do Córrego Fundo"></label>
        <div class="grade-2">
          <label>Data <input type="date" name="data" required></label>
          <label>Tipo
            <select name="tipo">
              <option value="visita">Visita de campo</option>
              <option value="reuniao">Reunião</option>
              <option value="evento">Evento</option>
            </select>
          </label>
        </div>
        <label>Comunidade <select name="comunidadeId"><option value="">—</option>${opcoesComunidades()}</select></label>
        <label>Notas <textarea name="notas" rows="2"></textarea></label>
        <button type="submit" class="btn-primario">Salvar</button>
      </form>
    </section>`;
  }

  /* ---------------------- Relatórios e comunicados -------------------- */

  function relatorios(params) {
    const dias = Number(params.dias) || 30;
    const texto = IA().gerarRelatorio(ST().dadosRelatorio(dias));
    const abaP = (n, rotulo) => `<a class="aba ${dias === n ? 'ativa' : ''}" href="#/relatorios?dias=${n}">${rotulo}</a>`;
    return `
    <section>
      <h2>📊 Relatórios em 1 toque</h2>
      <p class="sub">A FalaIA consolida os dados e escreve o relatório pronto para enviar à gerência.</p>
      <div class="abas">${abaP(7, 'Semanal')}${abaP(30, 'Mensal')}${abaP(90, 'Trimestral')}</div>
      <div class="card">
        <pre class="texto-gerado" id="texto-relatorio">${esc(texto)}</pre>
        <div class="botoes">
          <button class="btn-suave" data-action="copiar" data-alvo="texto-relatorio">📋 Copiar</button>
          <button class="btn-suave" data-action="baixar-relatorio" data-dias="${dias}">⬇️ .txt</button>
          <button class="btn-primario" data-action="compartilhar" data-alvo="texto-relatorio">📤 Enviar</button>
        </div>
      </div>
    </section>

    <section class="card">
      <h3>📢 Gerador de comunicados</h3>
      <form id="form-comunicado">
        <div class="grade-2">
          <label>Tipo
            <select name="tipo">
              <option value="detonacao">Detonação programada</option>
              <option value="interrupcao_via">Interrupção de via</option>
              <option value="manutencao">Manutenção</option>
              <option value="reuniao">Convite para reunião</option>
            </select>
          </label>
          <label>Comunidade <select name="comunidadeId">${opcoesComunidades()}</select></label>
        </div>
        <div class="grade-2">
          <label>Data <input type="date" name="data" required></label>
          <label>Hora <input type="time" name="hora"></label>
        </div>
        <label>Detalhe (opcional) <input name="detalhe" placeholder="Ex.: manutenção na linha férrea, km 12"></label>
        <button type="submit" class="btn-primario">Gerar comunicado</button>
      </form>
      <div id="saida-comunicado"></div>
    </section>

    <section class="card">
      <h3>⬇️ Exportar dados (CSV)</h3>
      <div class="botoes">
        <button class="btn-suave" data-action="exportar-csv" data-colecao="atendimentos">Atendimentos</button>
        <button class="btn-suave" data-action="exportar-csv" data-colecao="demandas">Demandas</button>
        <button class="btn-suave" data-action="exportar-csv" data-colecao="stakeholders">Stakeholders</button>
        <button class="btn-suave" data-action="exportar-csv" data-colecao="compromissos">Compromissos</button>
      </div>
    </section>`;
  }

  /* --------------------------- Assistente ---------------------------- */

  function assistente(chat) {
    const cfg = DB().getConfig();
    const online = cfg.ia.modo === 'online' && cfg.ia.apiKey;
    const sugestoes = [
      'Quais demandas estão em risco?',
      'Resumo da Boa Vista',
      'Relatório da semana',
      'Como responder reclamação de poeira?',
      'Comunicado de detonação para Boa Vista amanhã às 14h',
    ];
    return `
    <section class="chat">
      <div class="chat-cabecalho">
        <h2>✨ FalaIA — copiloto do analista</h2>
        <span class="chip ${online ? 'st-em_tratamento' : ''}">${online ? '☁️ online (Claude)' : '📴 offline (no dispositivo)'}</span>
      </div>
      <div class="chat-mensagens" id="chat-mensagens">
        ${chat.length ? chat.map((m) => `
          <div class="balao ${m.de === 'eu' ? 'eu' : 'ia'}">${m.html ? m.texto : esc(m.texto)}</div>`).join('')
        : `<div class="balao ia">Oi! Eu sou a FalaIA 👋
Posso resumir territórios, listar demandas em risco, gerar relatórios, comunicados e sugerir respostas. Pergunte algo ou toque numa sugestão.</div>`}
      </div>
      <div class="chat-sugestoes">
        ${sugestoes.map((s) => `<button class="chip-sugestao" data-action="sugestao-chat">${esc(s)}</button>`).join('')}
      </div>
      <form id="form-chat" class="chat-entrada">
        <input name="pergunta" id="campo-chat" placeholder="Pergunte à FalaIA…" autocomplete="off">
        <button type="submit" class="btn-primario">➤</button>
      </form>
    </section>`;
  }

  /* ------------------------------ Mais/Ajustes ------------------------ */

  function mais() {
    const itens = [
      ['#/relatorios', '📊', 'Relatórios e comunicados', 'Relatório pronto em 1 toque, comunicados e CSV'],
      ['#/compromissos', '🤝', 'Compromissos', 'Condicionantes e promessas com prazo'],
      ['#/agenda', '📅', 'Agenda de campo', 'Visitas, reuniões e eventos'],
      ['#/assistente', '✨', 'FalaIA', 'Copiloto do analista'],
      ['#/ajustes', '⚙️', 'Ajustes e dados', 'Backup, IA online, LGPD'],
    ];
    return `
    <section>
      <h2>Mais</h2>
      ${itens.map(([href, icone, titulo, sub]) => `
        <a class="card item-menu" href="${href}">
          <span class="menu-icone">${icone}</span>
          <div><strong>${titulo}</strong><small>${sub}</small></div>
          <span class="seta">›</span>
        </a>`).join('')}
    </section>`;
  }

  function ajustes() {
    const cfg = DB().getConfig();
    return `
    <section class="card">
      <h3>👤 Analista</h3>
      <form id="form-config">
        <label>Seu nome <input name="analista" value="${esc(cfg.analista)}" placeholder="Como assinar as respostas"></label>
        <button type="submit" class="btn-primario">Salvar</button>
      </form>
    </section>

    <section class="card">
      <h3>✨ FalaIA avançada (opcional)</h3>
      <p class="sub">O app funciona 100% offline. Para respostas livres no chat, conecte a API do Claude. <strong>Piloto:</strong> a chave fica somente neste dispositivo; em produção, use um proxy corporativo.</p>
      <form id="form-ia">
        <label>Modo
          <select name="modo">
            <option value="offline" ${cfg.ia.modo === 'offline' ? 'selected' : ''}>Offline (motor local)</option>
            <option value="online" ${cfg.ia.modo === 'online' ? 'selected' : ''}>Online (Claude API)</option>
          </select>
        </label>
        <label>Chave da API <input name="apiKey" type="password" value="${esc(cfg.ia.apiKey)}" placeholder="sk-ant-…"></label>
        <label>Modelo
          <select name="modelo">
            ${['claude-opus-4-8', 'claude-sonnet-4-6', 'claude-haiku-4-5'].map((m) => `<option value="${m}" ${cfg.ia.modelo === m ? 'selected' : ''}>${m}${m === 'claude-opus-4-8' ? ' (padrão)' : ''}</option>`).join('')}
          </select>
        </label>
        <button type="submit" class="btn-primario">Salvar configuração</button>
      </form>
    </section>

    <section class="card">
      <h3>💾 Backup e dados</h3>
      <div class="botoes coluna">
        <button class="btn-suave" data-action="exportar-json">⬇️ Exportar backup (.json)</button>
        <label class="btn-suave btn-arquivo">⬆️ Restaurar backup<input type="file" id="arquivo-importar" accept=".json" hidden></label>
        <button class="btn-suave" data-action="recarregar-demo">🔄 Recarregar dados de demonstração</button>
        <button class="btn-perigo" data-action="limpar-tudo">🗑 Apagar todos os dados</button>
      </div>
      ${cfg.demoCarregada ? '<p class="sub">⚠️ Este dispositivo está com dados fictícios de demonstração.</p>' : ''}
    </section>

    <section class="card">
      <h3>🔒 Privacidade (LGPD)</h3>
      <p class="sub">Os dados ficam armazenados apenas neste dispositivo. Registre somente dados pessoais necessários ao atendimento, com conhecimento do titular. Exportações e compartilhamentos são de responsabilidade do analista, conforme a política da empresa.</p>
      <p class="sub">Fala Comunidade · Central do Analista · v1.0</p>
    </section>`;
  }

  raiz.FalaViews = {
    inicio,
    registrar,
    confirmacao,
    demandas,
    demandaDetalhe,
    pessoas,
    pessoaDetalhe,
    compromissos,
    compromissoNovo,
    agenda,
    agendaNovo,
    relatorios,
    assistente,
    mais,
    ajustes,
  };
})(typeof self !== 'undefined' ? self : globalThis);
