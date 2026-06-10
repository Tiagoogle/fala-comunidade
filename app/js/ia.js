/* Fala Comunidade — FalaIA
 * Motor de inteligência embarcado (funciona 100% offline, no dispositivo).
 * Classifica manifestações, mede sentimento e criticidade, calcula SLA,
 * estima risco social por território e gera textos prontos (respostas,
 * comunicados e relatórios) para o analista de relacionamento com comunidades.
 */
(function (raiz) {
  'use strict';

  const norm = (t) => String(t || '')
    .toLowerCase()
    .normalize('NFD')
    .replace(/[̀-ͯ]/g, '');

  /* ------------------------------------------------------------------ *
   * Taxonomia de relacionamento com comunidades na mineração
   * ------------------------------------------------------------------ */

  const CATEGORIAS = [
    {
      id: 'barragens',
      nome: 'Barragens e Emergência (ZAS)',
      area: 'Geotecnia e Emergência',
      sensivel: true,
      chaves: ['barragem', 'sirene', 'zas', 'autossalvamento', 'simulado', 'evacuacao', 'rompimento', 'rota de fuga', 'ponto de encontro', 'alerta de emergencia'],
    },
    {
      id: 'patrimonio',
      nome: 'Danos a Imóveis e Patrimônio',
      area: 'Engenharia e Patrimônio',
      chaves: ['trinca', 'trincas', 'rachadura', 'rachaduras', 'rachado', 'parede rachada', 'muro caiu', 'telhado', 'dano na casa', 'casa danificada', 'vistoria no imovel'],
    },
    {
      id: 'ruido_vibracao',
      nome: 'Ruído, Vibração e Detonação',
      area: 'Operação de Mina',
      chaves: ['barulho', 'ruido', 'vibracao', 'detonacao', 'explosao', 'tremor', 'tremeu', 'tremendo', 'casa balanca', 'estrondo'],
    },
    {
      id: 'poeira',
      nome: 'Poeira e Qualidade do Ar',
      area: 'Meio Ambiente',
      chaves: ['poeira', 'particulado', 'poluicao do ar', 'umectacao', 'po na', 'po da', 'po de minerio', 'nuvem de po'],
    },
    {
      id: 'agua',
      nome: 'Água e Recursos Hídricos',
      area: 'Meio Ambiente',
      chaves: ['agua', 'poco', 'corrego', 'rio', 'nascente', 'abastecimento', 'turva', 'barrenta', 'cisterna', 'caixa d', 'sem agua', 'esgoto'],
    },
    {
      id: 'trafego',
      nome: 'Tráfego, Vias e Ferrovia',
      area: 'Logística e Infraestrutura',
      chaves: ['estrada', 'caminhao', 'caminhoes', 'transito', 'ferrovia', 'trem', 'locomotiva', 'mata-burro', 'ponte', 'buraco na via', 'velocidade', 'sinalizacao', 'passagem de nivel'],
    },
    {
      id: 'emprego',
      nome: 'Emprego e Capacitação',
      area: 'Recursos Humanos',
      chaves: ['emprego', 'vaga', 'vagas', 'trabalho', 'contratacao', 'curriculo', 'capacitacao', 'curso', 'estagio', 'jovem aprendiz', 'mao de obra local'],
    },
    {
      id: 'fornecedores',
      nome: 'Compras e Fornecedores Locais',
      area: 'Suprimentos',
      chaves: ['fornecedor', 'fornecimento', 'compra local', 'prestador de servico', 'cadastro de fornecedor', 'cotacao', 'contrato de servico'],
    },
    {
      id: 'invest_social',
      nome: 'Investimento Social, Doações e Patrocínios',
      area: 'Relações Comunitárias',
      chaves: ['doacao', 'patrocinio', 'apoio para', 'apoio a', 'projeto social', 'edital', 'convenio', 'festa', 'evento da comunidade', 'horta comunitaria', 'quadra', 'reforma da escola'],
    },
    {
      id: 'fundiario',
      nome: 'Terras, Cercas e Reassentamento',
      area: 'Fundiário',
      chaves: ['terra', 'terreno', 'cerca', 'divisa', 'reassentamento', 'desapropriacao', 'indenizacao', 'posse', 'propriedade', 'lote', 'porteira'],
    },
    {
      id: 'meio_ambiente',
      nome: 'Fauna, Flora e Meio Ambiente',
      area: 'Meio Ambiente',
      chaves: ['fauna', 'animal', 'animais', 'flora', 'arvore', 'arvores', 'desmatamento', 'queimada', 'peixe', 'peixes', 'mata', 'nascente seca', 'licenca ambiental'],
    },
    {
      id: 'saude_seguranca',
      nome: 'Saúde e Segurança Comunitária',
      area: 'Saúde e Segurança',
      chaves: ['saude', 'posto de saude', 'acidente', 'atropelamento', 'atropelou', 'doenca', 'respiratorio', 'falta de seguranca', 'iluminacao'],
    },
    {
      id: 'elogio',
      nome: 'Elogios e Agradecimentos',
      area: 'Relações Comunitárias',
      chaves: ['obrigado', 'obrigada', 'agradeco', 'agradecimento', 'agradecer', 'parabens', 'elogio', 'elogiar', 'excelente trabalho', 'muito bom o'],
    },
    {
      id: 'comunicacao',
      nome: 'Informações e Esclarecimentos',
      area: 'Relações Comunitárias',
      chaves: ['informacao', 'informacoes', 'esclarecimento', 'duvida', 'duvidas', 'comunicado', 'reuniao', 'convite', 'saber sobre', 'quando vai', 'como funciona'],
    },
    {
      id: 'outros',
      nome: 'Outros Assuntos',
      area: 'Relações Comunitárias',
      chaves: [],
    },
  ];

  /* Termos que indicam risco de escalada do conflito (peso forte). */
  const ESCALADA_FORTE = [
    'bloqueio', 'bloquear', 'fechar a estrada', 'trancar a estrada', 'fechar a ferrovia',
    'manifestacao', 'protesto', 'paralisacao', 'paralisar', 'abaixo-assinado',
    'ministerio publico', 'justica', 'processo', 'processar', 'advogado', 'defensoria',
    'imprensa', 'jornal', 'televisao', 'reportagem', 'denuncia', 'denunciar',
  ];

  /* Termos que indicam atenção institucional/política (peso moderado). */
  const ESCALADA_MODERADA = ['vereador', 'camara', 'prefeitura', 'prefeito', 'ibama', 'ouvidoria', 'sindicato'];

  /* Termos de urgência humanitária/operacional. */
  const URGENCIA = [
    'urgente', 'emergencia', 'risco de vida', 'perigo', 'crianca', 'escola',
    'hospital', 'idoso', 'sem agua', 'rompeu', 'caiu', 'desabou', 'acidente', 'ferido',
  ];

  /* Léxico simples de sentimento em PT-BR (peso por termo). */
  const LEXICO_NEG = {
    'revoltado': 2, 'revoltada': 2, 'indignado': 2, 'indignada': 2, 'absurdo': 2, 'inadmissivel': 2,
    'descaso': 2, 'abandono': 2, 'abandonados': 2, 'insuportavel': 2, 'humilhacao': 2, 'medo': 2,
    'pessimo': 2, 'pessima': 2, 'horrivel': 2, 'sofrendo': 2, 'prejuizo': 2, 'prejudicando': 2,
    'ruim': 1, 'problema': 1, 'problemas': 1, 'reclamacao': 1, 'reclamar': 1, 'cansado': 1, 'cansada': 1,
    'demora': 1, 'atraso': 1, 'sem resposta': 2, 'ninguem resolve': 2, 'nao aguentamos': 2, 'nao aguento': 2,
    'preocupado': 1, 'preocupada': 1, 'preocupacao': 1, 'sujeira': 1, 'incomodo': 1, 'incomodando': 1, 'piorou': 2,
  };
  const LEXICO_POS = {
    'obrigado': 2, 'obrigada': 2, 'agradeco': 2, 'agradecemos': 2, 'parabens': 2, 'excelente': 2,
    'otimo': 2, 'otima': 2, 'maravilhoso': 2, 'feliz': 2, 'satisfeito': 2, 'satisfeita': 2,
    'bom': 1, 'boa': 1, 'melhorou': 2, 'resolvido': 2, 'resolveu': 2, 'atencioso': 1, 'ajudou': 1, 'apoio recebido': 2,
  };

  /* SLA padrão por criticidade (dias corridos). */
  const SLA = {
    1: { resposta: 15, solucao: 30 },
    2: { resposta: 10, solucao: 30 },
    3: { resposta: 5, solucao: 20 },
    4: { resposta: 2, solucao: 10 },
    5: { resposta: 1, solucao: 5 },
  };

  const ROTULO_CRITICIDADE = { 1: 'Informativa', 2: 'Baixa', 3: 'Média', 4: 'Alta', 5: 'Crítica' };

  /* ------------------------------------------------------------------ *
   * Análise de texto
   * ------------------------------------------------------------------ */

  function contarOcorrencias(texto, termos) {
    const achados = [];
    for (const termo of termos) {
      if (texto.includes(termo)) achados.push(termo);
    }
    return achados;
  }

  function classificarCategoria(textoBruto) {
    const texto = ' ' + norm(textoBruto) + ' ';
    let melhor = null;
    let melhorPontos = 0;
    for (const cat of CATEGORIAS) {
      let pontos = 0;
      for (const chave of cat.chaves) {
        if (texto.includes(chave)) pontos += chave.includes(' ') ? 2 : 1;
      }
      if (pontos > melhorPontos) {
        melhorPontos = pontos;
        melhor = cat;
      }
    }
    if (!melhor) melhor = CATEGORIAS.find((c) => c.id === 'outros');
    return {
      id: melhor.id,
      nome: melhor.nome,
      area: melhor.area,
      confianca: melhorPontos >= 3 ? 'alta' : melhorPontos >= 1 ? 'média' : 'baixa',
    };
  }

  function sentimento(textoBruto) {
    const texto = ' ' + norm(textoBruto) + ' ';
    let pontos = 0;
    let termos = 0;
    for (const [termo, peso] of Object.entries(LEXICO_NEG)) {
      if (texto.includes(termo)) { pontos -= peso; termos++; }
    }
    for (const [termo, peso] of Object.entries(LEXICO_POS)) {
      if (texto.includes(termo)) { pontos += peso; termos++; }
    }
    const escore = termos === 0 ? 0 : Math.max(-1, Math.min(1, pontos / (termos * 2)));
    let rotulo = 'neutro';
    if (escore <= -0.6) rotulo = 'muito negativo';
    else if (escore <= -0.15) rotulo = 'negativo';
    else if (escore >= 0.15) rotulo = 'positivo';
    return { escore: Number(escore.toFixed(2)), rotulo };
  }

  function tipoSugerido(textoBruto, categoriaId, sent) {
    const texto = ' ' + norm(textoBruto) + ' ';
    if (categoriaId === 'elogio') return 'elogio';
    if (/\b(solicito|solicitamos|pedimos|peco|precisamos|gostariamos|gostaria de pedir|apoio para|doacao|patrocinio)\b/.test(texto)) {
      return 'solicitacao';
    }
    if (categoriaId === 'comunicacao' || /\b(duvida|saber|informacao|esclarecimento|quando vai|como funciona)\b/.test(texto)) {
      return 'informacao';
    }
    if (sent.escore < 0 || /\b(reclamacao|reclamar|problema|incomod|prejuizo|dano)\b/.test(texto)) {
      return 'reclamacao';
    }
    return 'informacao';
  }

  function criticidade(textoBruto, categoriaId, sent, alertas) {
    if (categoriaId === 'elogio') return 1;
    let nota = 2;
    if (sent.escore <= -0.6) nota += 1.5;
    else if (sent.escore <= -0.15) nota += 0.5;
    if (alertas.fortes.length) nota += 2;
    else if (alertas.moderados.length) nota += 1;
    if (alertas.urgencias.length >= 2) nota += 2;
    else if (alertas.urgencias.length) nota += 1;
    if (categoriaId === 'barragens' || categoriaId === 'saude_seguranca') nota += 1;
    if (categoriaId === 'comunicacao' && !alertas.fortes.length && !alertas.urgencias.length) nota = Math.min(nota, 2);
    return Math.max(1, Math.min(5, Math.round(nota)));
  }

  function detectarAlertas(textoBruto) {
    const texto = ' ' + norm(textoBruto) + ' ';
    return {
      fortes: contarOcorrencias(texto, ESCALADA_FORTE),
      moderados: contarOcorrencias(texto, ESCALADA_MODERADA),
      urgencias: contarOcorrencias(texto, URGENCIA),
    };
  }

  /**
   * Análise completa de um relato — o coração do registro assistido.
   * Devolve categoria, sentimento, criticidade, tipo, área e prazos sugeridos.
   */
  function analisar(textoBruto) {
    const categoria = classificarCategoria(textoBruto);
    const sent = sentimento(textoBruto);
    const alertas = detectarAlertas(textoBruto);
    const crit = criticidade(textoBruto, categoria.id, sent, alertas);
    const tipo = tipoSugerido(textoBruto, categoria.id, sent);
    const avisos = [];
    if (alertas.fortes.length) avisos.push(`Risco de escalada: menção a "${alertas.fortes[0]}"`);
    if (alertas.urgencias.length) avisos.push(`Sinal de urgência: "${alertas.urgencias[0]}"`);
    if (alertas.moderados.length) avisos.push(`Ator institucional citado: "${alertas.moderados[0]}"`);
    return {
      categoria,
      sentimento: sent,
      criticidade: crit,
      rotuloCriticidade: ROTULO_CRITICIDADE[crit],
      tipo,
      prazos: SLA[crit],
      avisos,
      geraDemanda: tipo === 'reclamacao' || tipo === 'solicitacao',
    };
  }

  /* ------------------------------------------------------------------ *
   * Risco social por território
   * ------------------------------------------------------------------ */

  /**
   * Índice de risco social (0–100) a partir de indicadores agregados:
   * criticidade (média e pico) das demandas abertas, % de SLA estourado,
   * tendência de manifestações (30d vs 30d anteriores), sentimento e alertas.
   * Uma única demanda crítica ou menção a bloqueio pesa muito — na prática,
   * é o que antecede paralisações e crises de licença social.
   */
  function indiceRisco(ind) {
    const critMedia = ind.criticidadeMedia || 0;
    const critMax = ind.criticidadeMax || critMedia;
    const slaEstourado = Math.max(0, Math.min(1, ind.percSlaEstourado || 0));
    const tendencia = Math.max(0, Math.min(1, ind.tendencia || 0));
    const sentNeg = Math.max(0, -(ind.sentimentoMedio || 0));
    const alertas = ind.alertasEscalada || 0;

    const score = Math.round(
      ((critMedia * 0.6 + critMax * 0.4) / 5) * 40 +
      slaEstourado * 20 +
      tendencia * 15 +
      sentNeg * 15 +
      (alertas >= 2 ? 20 : alertas === 1 ? 12 : 0)
    );
    const nivel = score >= 65 ? 'Alto' : score >= 35 ? 'Atenção' : 'Controlado';

    const fatores = [];
    if (alertas > 0) fatores.push('menções a bloqueio, protesto ou judicialização');
    if (critMax >= 5) fatores.push('demanda crítica em aberto');
    else if (critMedia >= 3.5) fatores.push('demandas abertas de alta criticidade');
    if (slaEstourado >= 0.25) fatores.push(`${Math.round(slaEstourado * 100)}% das demandas com prazo estourado`);
    if (tendencia >= 0.4) fatores.push('volume de manifestações em crescimento');
    if (sentNeg >= 0.3) fatores.push('sentimento predominantemente negativo');
    if (!fatores.length) fatores.push('indicadores dentro da normalidade');

    return { score: Math.max(0, Math.min(100, score)), nivel, fatores };
  }

  /* ------------------------------------------------------------------ *
   * Geração de textos prontos
   * ------------------------------------------------------------------ */

  const CORPO_RESPOSTA = {
    poeira: 'A equipe de Meio Ambiente foi acionada para verificar as condições de emissão de particulados e reforçar as rotinas de umectação das vias na sua região.',
    ruido_vibracao: 'A equipe de Operação de Mina foi acionada para verificar os registros de sismografia e os horários das detonações próximas à sua comunidade.',
    agua: 'A equipe de Meio Ambiente foi acionada para avaliar a situação relatada e, se necessário, realizar coleta e análise da qualidade da água.',
    patrimonio: 'Será agendada uma vistoria técnica no imóvel para avaliação dos danos relatados. Nossa equipe entrará em contato para combinar a melhor data.',
    trafego: 'A equipe de Logística e Infraestrutura foi acionada para verificar as condições da via e as medidas de segurança no trecho indicado.',
    emprego: 'Encaminhamos sua manifestação à equipe de Recursos Humanos. As vagas e os programas de capacitação são divulgados nos canais oficiais e nas lideranças locais.',
    fornecedores: 'Encaminhamos seu interesse à equipe de Suprimentos, responsável pelo cadastro e desenvolvimento de fornecedores locais.',
    invest_social: 'Sua solicitação foi registrada e será avaliada conforme os critérios do programa de investimento social e o calendário de apoios da empresa.',
    fundiario: 'A equipe Fundiária foi acionada para analisar a situação relatada e dar o encaminhamento adequado.',
    barragens: 'A equipe de Geotecnia e Emergência foi imediatamente informada. Reforçamos que os canais de emergência e os pontos de encontro estão à disposição da comunidade.',
    meio_ambiente: 'A equipe de Meio Ambiente foi acionada para verificar a ocorrência relatada.',
    saude_seguranca: 'A equipe de Saúde e Segurança foi acionada com prioridade para avaliar a situação relatada.',
    comunicacao: 'Seguem em anexo as informações solicitadas. Permanecemos à disposição para esclarecimentos adicionais.',
    elogio: 'Agradecemos imensamente o reconhecimento, que será repassado a toda a equipe envolvida.',
    outros: 'Sua manifestação foi encaminhada à área responsável para análise e retorno.',
  };

  /**
   * Rascunho de resposta à comunidade, pronto para enviar por WhatsApp.
   * dados: { nome, protocolo, categoriaId, prazoRespostaISO }
   */
  function respostaSugerida(dados) {
    const nome = dados.nome ? `Olá, ${dados.nome}!` : 'Olá!';
    const corpo = CORPO_RESPOSTA[dados.categoriaId] || CORPO_RESPOSTA.outros;
    const prazo = dados.prazoSolucaoISO
      ? `\n\nPrevisão de retorno conclusivo: até ${new Date(dados.prazoSolucaoISO).toLocaleDateString('pt-BR')}.`
      : '';
    return (
      `${nome} Aqui é ${dados.analista || 'a equipe'} de Relacionamento com Comunidades.\n\n` +
      `Recebemos a sua manifestação e ela foi registrada sob o protocolo ${dados.protocolo}. ${corpo}${prazo}\n\n` +
      `Você pode acompanhar este protocolo comigo ou pelos nossos canais oficiais. Obrigado pelo contato!`
    );
  }

  const COMUNICADOS = {
    detonacao: (d) => (
      `📢 COMUNICADO À COMUNIDADE ${d.comunidade ? d.comunidade.toUpperCase() : ''}\n\n` +
      `Informamos que no dia ${d.data}, por volta das ${d.hora || '12h'}, será realizada DETONAÇÃO programada na mina.\n\n` +
      `• O que esperar: ruído e leve vibração por alguns segundos.\n` +
      `• Não é necessário sair de casa nem tomar qualquer providência.\n` +
      `• Equipes de monitoramento estarão acompanhando toda a operação.\n\n` +
      `Em caso de dúvidas, fale com a equipe de Relacionamento ou ligue 0800-031-2303.`
    ),
    interrupcao_via: (d) => (
      `📢 COMUNICADO — INTERRUPÇÃO TEMPORÁRIA DE VIA\n\n` +
      `No dia ${d.data}, ${d.detalhe || 'haverá interrupção temporária de tráfego'} ${d.comunidade ? `na região de ${d.comunidade}` : ''}.\n\n` +
      `• Horário previsto: ${d.hora || 'a confirmar'}.\n` +
      `• Rotas alternativas estarão sinalizadas.\n\n` +
      `Pedimos desculpas pelo transtorno e agradecemos a compreensão. Dúvidas: 0800-031-2303.`
    ),
    manutencao: (d) => (
      `📢 COMUNICADO — ATIVIDADE DE MANUTENÇÃO\n\n` +
      `Informamos que no dia ${d.data} será realizada ${d.detalhe || 'atividade de manutenção programada'} ${d.comunidade ? `próxima à comunidade ${d.comunidade}` : ''}.\n\n` +
      `A atividade pode gerar movimentação de equipes e equipamentos na região. Contamos com a compreensão de todos.\n\n` +
      `Dúvidas: equipe de Relacionamento com Comunidades — 0800-031-2303.`
    ),
    reuniao: (d) => (
      `📢 CONVITE — REUNIÃO COM A COMUNIDADE ${d.comunidade ? d.comunidade.toUpperCase() : ''}\n\n` +
      `Convidamos todas e todos para nossa reunião no dia ${d.data}, às ${d.hora || '19h'}, ${d.detalhe || 'no local de costume'}.\n\n` +
      `Pauta: atualizações das ações na região, próximos passos e espaço aberto para perguntas.\n\n` +
      `Sua participação é muito importante!`
    ),
  };

  function gerarComunicado(tipo, dados) {
    const gerador = COMUNICADOS[tipo] || COMUNICADOS.manutencao;
    return gerador(dados || {});
  }

  /* ------------------------------------------------------------------ *
   * Relatório gerencial automático
   * ------------------------------------------------------------------ */

  /**
   * Gera o relatório do período em texto pronto para envio.
   * dados: agregado produzido por FalaStats.dadosRelatorio().
   */
  function gerarRelatorio(dados) {
    const d = dados;
    const linhas = [];
    const titulo = d.titulo || 'RELATÓRIO DE RELACIONAMENTO COM COMUNIDADES';
    linhas.push(titulo.toUpperCase());
    linhas.push(`Período: ${d.periodo} · Gerado em ${new Date().toLocaleDateString('pt-BR')} pelo Fala Comunidade`);
    linhas.push('');

    // Resumo executivo em prosa
    const variacao = d.variacaoAtendimentos;
    const tendTexto = variacao > 0.15 ? `alta de ${Math.round(variacao * 100)}% sobre o período anterior`
      : variacao < -0.15 ? `queda de ${Math.round(-variacao * 100)}% sobre o período anterior`
      : 'volume estável em relação ao período anterior';
    linhas.push('1. RESUMO EXECUTIVO');
    linhas.push(
      `Foram registrados ${d.totalAtendimentos} atendimentos no período (${tendTexto}), ` +
      `com ${d.demandasAbertas} demandas em aberto ao final. ` +
      `O cumprimento de prazos de resposta ficou em ${Math.round(d.percSlaNoPrazo * 100)}%. ` +
      `O tema mais recorrente foi "${d.temaTop ? d.temaTop.nome : '—'}"` +
      (d.territorioMaisCritico ? `, e o território que exige mais atenção é ${d.territorioMaisCritico.nome} (risco ${d.territorioMaisCritico.nivel.toLowerCase()}, índice ${d.territorioMaisCritico.score}/100).` : '.')
    );
    linhas.push('');

    linhas.push('2. NÚMEROS DO PERÍODO');
    linhas.push(`• Atendimentos registrados: ${d.totalAtendimentos}`);
    linhas.push(`• Novas demandas: ${d.novasDemandas} | Encerradas: ${d.demandasEncerradas} | Em aberto: ${d.demandasAbertas}`);
    linhas.push(`• Respostas dentro do prazo (SLA): ${Math.round(d.percSlaNoPrazo * 100)}%`);
    linhas.push(`• Sentimento médio das manifestações: ${d.sentimentoRotulo}`);
    if (d.elogios > 0) linhas.push(`• Elogios recebidos: ${d.elogios}`);
    linhas.push('');

    if (d.temas && d.temas.length) {
      linhas.push('3. TEMAS MAIS RECORRENTES');
      d.temas.slice(0, 5).forEach((t, i) => {
        linhas.push(`${i + 1}. ${t.nome} — ${t.qtd} registro(s)`);
      });
      linhas.push('');
    }

    if (d.territorios && d.territorios.length) {
      linhas.push('4. RISCO SOCIAL POR TERRITÓRIO');
      d.territorios.forEach((t) => {
        linhas.push(`• ${t.nome}: ${t.nivel} (${t.score}/100) — ${t.fatores[0]}`);
      });
      linhas.push('');
    }

    if (d.compromissosVencendo && d.compromissosVencendo.length) {
      linhas.push('5. COMPROMISSOS E CONDICIONANTES A VENCER');
      d.compromissosVencendo.forEach((c) => {
        linhas.push(`• ${c.titulo} — prazo ${c.prazo}`);
      });
      linhas.push('');
    }

    linhas.push(`${d.compromissosVencendo && d.compromissosVencendo.length ? 6 : 5}. RECOMENDAÇÕES DA FALAIA`);
    recomendar(d).forEach((r) => linhas.push(`• ${r}`));

    return linhas.join('\n');
  }

  function recomendar(d) {
    const recs = [];
    const topId = d.temaTop && d.temaTop.id;
    if (topId === 'poeira') recs.push('Reforçar a umectação de vias e comunicar o cronograma às comunidades afetadas — poeira é o tema dominante do período.');
    if (topId === 'ruido_vibracao') recs.push('Divulgar antecipadamente o calendário de detonações e compartilhar laudos de sismografia com as lideranças.');
    if (topId === 'agua') recs.push('Antecipar coletas de qualidade da água e divulgar os resultados em linguagem acessível.');
    if (topId === 'emprego') recs.push('Organizar ação de divulgação de vagas e capacitação com as lideranças locais.');
    if (topId === 'patrimonio') recs.push('Priorizar o mutirão de vistorias de imóveis nas comunidades com mais relatos.');
    if (d.percSlaNoPrazo < 0.8) recs.push('Realizar mutirão de tratativas: o cumprimento de SLA está abaixo da meta de 80%.');
    if (d.territorioMaisCritico && d.territorioMaisCritico.nivel === 'Alto') {
      recs.push(`Intensificar presença de campo em ${d.territorioMaisCritico.nomeCompleto || d.territorioMaisCritico.nome} e preparar plano de resposta a possível escalada.`);
    }
    if (d.alertasEscalada > 0) recs.push('Há manifestações com menção a bloqueio/judicialização: acionar protocolo preventivo de gestão de crise.');
    if (d.stakeholdersSemContato && d.stakeholdersSemContato.length) {
      recs.push(`Retomar contato com lideranças sem interação há mais de 30 dias (${d.stakeholdersSemContato.slice(0, 3).map((s) => s.nome).join(', ')}${d.stakeholdersSemContato.length > 3 ? '…' : ''}).`);
    }
    if (d.elogios > 0) recs.push('Compartilhar os elogios recebidos com as equipes operacionais — reconhecimento fortalece o engajamento interno.');
    if (!recs.length) recs.push('Manter a rotina de visitas e monitoramento — indicadores dentro da normalidade.');
    return recs;
  }

  /* ------------------------------------------------------------------ *
   * API pública
   * ------------------------------------------------------------------ */

  raiz.FalaIA = {
    CATEGORIAS,
    ROTULO_CRITICIDADE,
    SLA,
    analisar,
    classificarCategoria,
    sentimento,
    criticidade,
    detectarAlertas,
    indiceRisco,
    respostaSugerida,
    gerarComunicado,
    gerarRelatorio,
    slaPorCriticidade: (c) => SLA[Math.max(1, Math.min(5, c))],
  };
})(typeof self !== 'undefined' ? self : globalThis);
