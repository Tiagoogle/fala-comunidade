/* Fala Comunidade — FalaStats
 * Indicadores derivados dos dados locais: SLA, risco por território,
 * temas em alta e agregados para o relatório automático.
 */
(function (raiz) {
  'use strict';

  const U = raiz.FalaUtil;
  const DB = () => raiz.FalaDB;
  const IA = () => raiz.FalaIA;

  const STATUS_ABERTOS = ['recebida', 'em_analise', 'em_tratamento'];
  const ROTULO_STATUS = {
    recebida: 'Recebida',
    em_analise: 'Em análise',
    em_tratamento: 'Em tratamento',
    respondida: 'Respondida',
    encerrada: 'Encerrada',
  };

  function nomeCategoria(id) {
    const cat = IA().CATEGORIAS.find((c) => c.id === id);
    return cat ? cat.nome : 'Outros Assuntos';
  }

  function demandasAbertas() {
    return DB().get('demandas').filter((d) => STATUS_ABERTOS.includes(d.status));
  }

  /** Situação de prazo de uma demanda: qual prazo vale agora e quantos dias faltam. */
  function situacaoSLA(demanda) {
    if (!STATUS_ABERTOS.includes(demanda.status)) {
      return { fase: 'concluida', dias: 0, estourado: false, rotulo: ROTULO_STATUS[demanda.status] };
    }
    const aguardandoResposta = !demanda.respondida;
    const prazoISO = aguardandoResposta ? demanda.prazoRespostaISO : demanda.prazoSolucaoISO;
    const dias = U.diasAte(prazoISO);
    return {
      fase: aguardandoResposta ? 'resposta' : 'solucao',
      prazoISO,
      dias,
      estourado: dias < 0,
      urgente: dias >= 0 && dias <= 1,
      rotulo: (aguardandoResposta ? 'Resposta ' : 'Solução ') + U.rotuloPrazo(prazoISO),
    };
  }

  function demandasEmRisco() {
    return demandasAbertas()
      .map((d) => ({ demanda: d, sla: situacaoSLA(d) }))
      .filter((x) => x.sla.estourado || x.sla.urgente)
      .sort((a, b) => a.sla.dias - b.sla.dias);
  }

  function atendimentosNoPeriodo(dias, deslocamento) {
    const desl = deslocamento || 0;
    return DB().get('atendimentos').filter((a) => {
      const idade = (Date.now() - new Date(a.dataISO).getTime()) / 86400000;
      return idade >= desl && idade < desl + dias;
    });
  }

  function temasEmAlta(dias) {
    const atuais = atendimentosNoPeriodo(dias || 30);
    const anteriores = atendimentosNoPeriodo(dias || 30, dias || 30);
    const conta = (lista) => {
      const m = {};
      lista.forEach((a) => { m[a.categoriaId] = (m[a.categoriaId] || 0) + 1; });
      return m;
    };
    const agora = conta(atuais);
    const antes = conta(anteriores);
    return Object.entries(agora)
      .map(([id, qtd]) => ({ id, nome: nomeCategoria(id), qtd, delta: qtd - (antes[id] || 0) }))
      .sort((a, b) => b.qtd - a.qtd);
  }

  /** Indicadores e índice de risco para cada comunidade. */
  function riscoPorComunidade() {
    const comunidades = DB().get('comunidades');
    return comunidades.map((com) => {
      const abertas = demandasAbertas().filter((d) => d.comunidadeId === com.id);
      const ats30 = atendimentosNoPeriodo(30).filter((a) => a.comunidadeId === com.id);
      const ats30ant = atendimentosNoPeriodo(30, 30).filter((a) => a.comunidadeId === com.id);
      const critMedia = abertas.length
        ? abertas.reduce((s, d) => s + (d.criticidade || 2), 0) / abertas.length : 0;
      const critMax = abertas.reduce((m, d) => Math.max(m, d.criticidade || 2), 0);
      const estouradas = abertas.filter((d) => situacaoSLA(d).estourado).length;
      const sentimentos = ats30.map((a) => a.sentimentoEscore || 0);
      const sentMedio = sentimentos.length ? sentimentos.reduce((s, x) => s + x, 0) / sentimentos.length : 0;
      const alertas = abertas.filter((d) => d.alertaEscalada).length +
        ats30.filter((a) => a.alertaEscalada).length;
      const tendencia = ats30ant.length === 0
        ? (ats30.length > 2 ? 0.5 : 0)
        : Math.max(0, (ats30.length - ats30ant.length) / ats30ant.length);

      const risco = IA().indiceRisco({
        criticidadeMedia: critMedia,
        criticidadeMax: critMax,
        percSlaEstourado: abertas.length ? estouradas / abertas.length : 0,
        tendencia,
        sentimentoMedio: sentMedio,
        alertasEscalada: alertas,
      });
      return { comunidade: com, abertas: abertas.length, atendimentos30d: ats30.length, risco };
    }).sort((a, b) => b.risco.score - a.risco.score);
  }

  function stakeholdersSemContato(diasLimite) {
    const limite = diasLimite || 30;
    const ats = DB().get('atendimentos');
    return DB().get('stakeholders')
      .map((s) => {
        const ultimos = ats.filter((a) => a.stakeholderId === s.id)
          .sort((a, b) => new Date(b.dataISO) - new Date(a.dataISO));
        const ultimo = ultimos[0] ? ultimos[0].dataISO : s.criadoISO || U.diasAtras(90);
        return { stakeholder: s, ultimoContatoISO: ultimo, diasSemContato: -U.diasAte(ultimo) };
      })
      .filter((x) => x.diasSemContato > limite)
      .sort((a, b) => b.diasSemContato - a.diasSemContato);
  }

  function compromissosVencendo(dias) {
    return DB().get('compromissos')
      .filter((c) => c.status !== 'concluido')
      .map((c) => ({ compromisso: c, dias: U.diasAte(c.prazoISO) }))
      .filter((x) => x.dias <= (dias == null ? 7 : dias))
      .sort((a, b) => a.dias - b.dias);
  }

  function quadranteStakeholder(s) {
    const inf = s.influencia >= 4;
    const int = s.interesse >= 4;
    if (inf && int) return 'Gerenciar de perto';
    if (inf && !int) return 'Manter satisfeito';
    if (!inf && int) return 'Manter informado';
    return 'Monitorar';
  }

  /** Agregado completo para o relatório automático da FalaIA. */
  function dadosRelatorio(dias) {
    const periodoDias = dias || 30;
    const ats = atendimentosNoPeriodo(periodoDias);
    const atsAnt = atendimentosNoPeriodo(periodoDias, periodoDias);
    const demandas = DB().get('demandas');
    const novas = demandas.filter((d) => U.dentroDeDias(d.criadoISO, periodoDias));
    const abertas = demandasAbertas();
    const respondidasNoPrazo = demandas.filter((d) => {
      if (!U.dentroDeDias(d.criadoISO, periodoDias)) return false;
      const sla = situacaoSLA(d);
      return !(sla.fase === 'resposta' && sla.estourado);
    });
    const sentimentos = ats.map((a) => a.sentimentoEscore || 0);
    const sentMedio = sentimentos.length ? sentimentos.reduce((s, x) => s + x, 0) / sentimentos.length : 0;
    const temas = temasEmAlta(periodoDias);
    const riscos = riscoPorComunidade();
    const top = riscos[0];

    return {
      titulo: `Relatório de Relacionamento com Comunidades — últimos ${periodoDias} dias`,
      periodo: `últimos ${periodoDias} dias`,
      totalAtendimentos: ats.length,
      variacaoAtendimentos: atsAnt.length ? (ats.length - atsAnt.length) / atsAnt.length : 0,
      novasDemandas: novas.length,
      demandasEncerradas: demandas.filter((d) => d.status === 'encerrada' && U.dentroDeDias(d.criadoISO, periodoDias * 2)).length,
      demandasAbertas: abertas.length,
      percSlaNoPrazo: novas.length ? respondidasNoPrazo.length / novas.length : 1,
      sentimentoRotulo: sentMedio <= -0.3 ? 'negativo' : sentMedio >= 0.15 ? 'positivo' : 'neutro',
      elogios: ats.filter((a) => a.categoriaId === 'elogio').length,
      temaTop: temas[0] || null,
      temas,
      territorios: riscos.map((r) => ({ nome: r.comunidade.nome, score: r.risco.score, nivel: r.risco.nivel, fatores: r.risco.fatores })),
      territorioMaisCritico: top ? { nome: top.comunidade.nome, nomeCompleto: `${top.comunidade.nome} (${top.comunidade.territorio})`, score: top.risco.score, nivel: top.risco.nivel } : null,
      compromissosVencendo: compromissosVencendo(7).map((x) => ({ titulo: x.compromisso.titulo, prazo: U.rotuloPrazo(x.compromisso.prazoISO) })),
      alertasEscalada: abertas.filter((d) => d.alertaEscalada).length,
      stakeholdersSemContato: stakeholdersSemContato(30).map((x) => ({ nome: x.stakeholder.nome, dias: x.diasSemContato })),
    };
  }

  raiz.FalaStats = {
    STATUS_ABERTOS,
    ROTULO_STATUS,
    nomeCategoria,
    demandasAbertas,
    situacaoSLA,
    demandasEmRisco,
    atendimentosNoPeriodo,
    temasEmAlta,
    riscoPorComunidade,
    stakeholdersSemContato,
    compromissosVencendo,
    quadranteStakeholder,
    dadosRelatorio,
  };
})(typeof self !== 'undefined' ? self : globalThis);
