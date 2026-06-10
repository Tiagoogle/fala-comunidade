/* Fala Comunidade — FalaDB
 * Camada de dados offline-first sobre localStorage.
 * Tudo fica no dispositivo do analista; exportação/backup sob seu controle (LGPD).
 */
(function (raiz) {
  'use strict';

  const U = raiz.FalaUtil;
  const CHAVE = 'fala-comunidade-v1';
  const COLECOES = ['comunidades', 'stakeholders', 'atendimentos', 'demandas', 'compromissos', 'agenda'];

  let dados = null;

  function vazio() {
    const base = { config: { analista: '', demoCarregada: false, seqProtocolo: 0, ia: { modo: 'offline', apiKey: '', modelo: 'claude-opus-4-8' } } };
    COLECOES.forEach((c) => { base[c] = []; });
    return base;
  }

  function salvar() {
    try {
      localStorage.setItem(CHAVE, JSON.stringify(dados));
    } catch (e) {
      console.error('Falha ao salvar dados locais', e);
      alert('Não foi possível salvar: armazenamento do dispositivo cheio.');
    }
  }

  function init() {
    try {
      const bruto = localStorage.getItem(CHAVE);
      dados = bruto ? JSON.parse(bruto) : null;
    } catch (e) {
      dados = null;
    }
    if (!dados) {
      dados = vazio();
      seedDemo();
      dados.config.demoCarregada = true;
      salvar();
    }
    return dados;
  }

  function get(colecao) {
    return dados[colecao] || [];
  }

  function porId(colecao, id) {
    return get(colecao).find((x) => x.id === id) || null;
  }

  function add(colecao, obj) {
    obj.id = obj.id || U.id();
    obj.criadoISO = obj.criadoISO || U.agoraISO();
    dados[colecao].push(obj);
    salvar();
    return obj;
  }

  function update(colecao, id, patch) {
    const item = porId(colecao, id);
    if (!item) return null;
    Object.assign(item, patch);
    salvar();
    return item;
  }

  function remove(colecao, id) {
    dados[colecao] = get(colecao).filter((x) => x.id !== id);
    salvar();
  }

  function getConfig() {
    return dados.config;
  }

  function setConfig(patch) {
    Object.assign(dados.config, patch);
    salvar();
    return dados.config;
  }

  function proximoProtocolo() {
    dados.config.seqProtocolo = (dados.config.seqProtocolo || 0) + 1;
    salvar();
    const ano = new Date().getFullYear();
    return `FC-${ano}-${String(dados.config.seqProtocolo).padStart(4, '0')}`;
  }

  /* ----------------------- backup / exportação ----------------------- */

  function exportarJSON() {
    return JSON.stringify(dados, null, 2);
  }

  function importarJSON(texto) {
    const novo = JSON.parse(texto);
    if (!novo || !Array.isArray(novo.atendimentos)) throw new Error('Arquivo inválido');
    dados = Object.assign(vazio(), novo);
    salvar();
  }

  function exportarCSV(colecao) {
    const itens = get(colecao);
    if (!itens.length) return '';
    const colunas = [...new Set(itens.flatMap((i) => Object.keys(i)))]
      .filter((c) => c !== 'historico');
    const esc = (v) => {
      if (v == null) return '';
      const s = typeof v === 'object' ? JSON.stringify(v) : String(v);
      return '"' + s.replace(/"/g, '""') + '"';
    };
    const linhas = [colunas.join(';')];
    itens.forEach((i) => linhas.push(colunas.map((c) => esc(i[c])).join(';')));
    return '﻿' + linhas.join('\n');
  }

  function limparTudo() {
    dados = vazio();
    salvar();
  }

  /* ------------------------------------------------------------------ *
   * Dados de demonstração (fictícios) — mostram o app vivo no 1º acesso.
   * Datas relativas a "hoje" para que SLAs, alertas e tendências façam sentido.
   * ------------------------------------------------------------------ */

  function seedDemo() {
    const atras = U.diasAtras;
    const frente = U.diasAFrente;

    const com1 = { id: 'com-boavista', nome: 'Comunidade Boa Vista', territorio: 'Território Norte', municipio: 'Município fictício/MG', populacao: 1200, contexto: 'Vizinha à cava e à estrada de acesso da mina.' };
    const com2 = { id: 'com-santaef', nome: 'Distrito de Santa Efigênia', territorio: 'Território Norte', municipio: 'Município fictício/MG', populacao: 3500, contexto: 'Cortada pela ferrovia; histórico de relatos de vibração.' };
    const com3 = { id: 'com-corrego', nome: 'Vila do Córrego Fundo', territorio: 'Território Sul', municipio: 'Município fictício/MG', populacao: 800, contexto: 'Parcialmente dentro da ZAS; foco em preparação para emergências.' };
    const com4 = { id: 'com-novohor', nome: 'Assentamento Novo Horizonte', territorio: 'Território Sul', municipio: 'Município fictício/MG', populacao: 450, contexto: 'Tema fundiário sensível (divisas e cercas).' };
    dados.comunidades = [com1, com2, com3, com4];

    dados.stakeholders = [
      { id: 'stk-zelia', nome: 'Zélia Martins', papel: 'Presidente da Associação de Moradores', organizacao: 'Associação Boa Vista', comunidadeId: com1.id, telefone: '(31) 99999-0001', influencia: 5, interesse: 5, notas: 'Interlocutora-chave. Prefere contato por WhatsApp pela manhã.' },
      { id: 'stk-joao', nome: 'João Ferreira', papel: 'Líder comunitário', organizacao: '', comunidadeId: com1.id, telefone: '(31) 99999-0002', influencia: 3, interesse: 5, notas: 'Mobiliza os jovens; parceiro no projeto da horta.' },
      { id: 'stk-rita', nome: 'Rita de Cássia', papel: 'Diretora da Escola Municipal', organizacao: 'Escola M. Santa Efigênia', comunidadeId: com2.id, telefone: '(31) 99999-0003', influencia: 4, interesse: 4, notas: 'Sensível ao tema do tráfego de caminhões no horário escolar.' },
      { id: 'stk-carlos', nome: 'Carlos Eduardo', papel: 'Vereador', organizacao: 'Câmara Municipal', comunidadeId: com2.id, telefone: '(31) 99999-0004', influencia: 5, interesse: 3, notas: 'Costuma levar demandas da base à imprensa. Manter informado.' },
      { id: 'stk-antonia', nome: 'Antônia Lopes', papel: 'Agente Comunitária de Saúde', organizacao: 'UBS Córrego Fundo', comunidadeId: com3.id, telefone: '(31) 99999-0005', influencia: 3, interesse: 5, notas: 'Apoia a comunicação dos simulados da ZAS.' },
      { id: 'stk-geraldo', nome: 'Geraldo Souza', papel: 'Produtor rural', organizacao: 'Sindicato Rural', comunidadeId: com4.id, telefone: '(31) 99999-0006', influencia: 4, interesse: 4, notas: 'Caso de divisa de terreno em negociação.' },
      { id: 'stk-padre', nome: 'Padre Miguel', papel: 'Pároco', organizacao: 'Paróquia N. Sra. Aparecida', comunidadeId: com1.id, telefone: '(31) 99999-0007', influencia: 4, interesse: 3, notas: 'Apoio importante na festa junina e em momentos de tensão.' },
      { id: 'stk-marcia', nome: 'Márcia Oliveira', papel: 'Comerciante', organizacao: 'Mercearia da Márcia', comunidadeId: com3.id, telefone: '(31) 99999-0008', influencia: 2, interesse: 4, notas: 'Interessada no cadastro de fornecedores locais.' },
    ];

    // Histórico de atendimentos (últimos ~70 dias) — alguns geram demandas.
    const ats = [
      { dataISO: atras(68), canal: 'presencial', comunidadeId: com1.id, stakeholderId: 'stk-zelia', descricao: 'Reunião mensal com a associação. Pauta: cronograma de umectação da estrada e vagas para jovens.', categoriaId: 'comunicacao', tipo: 'informacao', criticidade: 2, sentimentoRotulo: 'neutro', sentimentoEscore: 0 },
      { dataISO: atras(55), canal: 'telefone', comunidadeId: com2.id, stakeholderId: 'stk-rita', descricao: 'Diretora pediu reforço de sinalização e redução de velocidade dos caminhões no horário de entrada da escola.', categoriaId: 'trafego', tipo: 'solicitacao', criticidade: 3, sentimentoRotulo: 'neutro', sentimentoEscore: -0.1 },
      { dataISO: atras(41), canal: 'whatsapp', comunidadeId: com1.id, stakeholderId: 'stk-joao', descricao: 'Agradecimento pelo apoio ao projeto da horta comunitária. Colheita rendeu e parte foi doada à escola.', categoriaId: 'elogio', tipo: 'elogio', criticidade: 1, sentimentoRotulo: 'positivo', sentimentoEscore: 0.8 },
      { dataISO: atras(34), canal: 'presencial', comunidadeId: com3.id, stakeholderId: 'stk-antonia', descricao: 'Dúvidas dos moradores sobre o próximo simulado de emergência da ZAS e o som da sirene.', categoriaId: 'barragens', tipo: 'informacao', criticidade: 3, sentimentoRotulo: 'neutro', sentimentoEscore: 0 },
      { dataISO: atras(29), canal: '0800', comunidadeId: com2.id, stakeholderId: null, descricao: 'Morador relatou trincas na parede da sala e pediu vistoria. Acha que piorou depois das últimas detonações.', categoriaId: 'patrimonio', tipo: 'reclamacao', criticidade: 4, sentimentoRotulo: 'negativo', sentimentoEscore: -0.4 },
      { dataISO: atras(24), canal: 'whatsapp', comunidadeId: com1.id, stakeholderId: 'stk-zelia', descricao: 'Poeira intensa na estrada de acesso. Moradores com roupas no varal sujas e reclamando de tosse nas crianças.', categoriaId: 'poeira', tipo: 'reclamacao', criticidade: 4, sentimentoRotulo: 'negativo', sentimentoEscore: -0.5 },
      { dataISO: atras(20), canal: 'presencial', comunidadeId: com4.id, stakeholderId: 'stk-geraldo', descricao: 'Tratativa sobre cerca na divisa do assentamento com área da empresa. Pediu posição formal do Fundiário.', categoriaId: 'fundiario', tipo: 'solicitacao', criticidade: 3, sentimentoRotulo: 'neutro', sentimentoEscore: -0.1 },
      { dataISO: atras(15), canal: 'whatsapp', comunidadeId: com1.id, stakeholderId: 'stk-padre', descricao: 'Paróquia solicita patrocínio para a festa junina da comunidade, com praça de alimentação das famílias locais.', categoriaId: 'invest_social', tipo: 'solicitacao', criticidade: 2, sentimentoRotulo: 'positivo', sentimentoEscore: 0.2 },
      { dataISO: atras(12), canal: 'telefone', comunidadeId: com3.id, stakeholderId: 'stk-marcia', descricao: 'Comerciante quer saber como entrar no cadastro de fornecedores locais para fornecer lanches às equipes.', categoriaId: 'fornecedores', tipo: 'informacao', criticidade: 2, sentimentoRotulo: 'neutro', sentimentoEscore: 0.1 },
      { dataISO: atras(9), canal: 'whatsapp', comunidadeId: com1.id, stakeholderId: 'stk-zelia', descricao: 'Poeira voltou forte com o tempo seco. Associação cobra cronograma de umectação; moradores muito insatisfeitos.', categoriaId: 'poeira', tipo: 'reclamacao', criticidade: 4, sentimentoRotulo: 'negativo', sentimentoEscore: -0.6 },
      { dataISO: atras(6), canal: 'presencial', comunidadeId: com2.id, stakeholderId: 'stk-carlos', descricao: 'Vereador cobrou retorno das vistorias de trincas e disse que, sem resposta, levará o caso à imprensa.', categoriaId: 'patrimonio', tipo: 'reclamacao', criticidade: 4, sentimentoRotulo: 'negativo', sentimentoEscore: -0.5 },
      { dataISO: atras(4), canal: 'whatsapp', comunidadeId: com1.id, stakeholderId: 'stk-joao', descricao: 'Jovens perguntando sobre novas turmas do curso de capacitação. Lista de interessados com 22 nomes.', categoriaId: 'emprego', tipo: 'solicitacao', criticidade: 2, sentimentoRotulo: 'positivo', sentimentoEscore: 0.2 },
      { dataISO: atras(2), canal: 'presencial', comunidadeId: com1.id, stakeholderId: 'stk-zelia', descricao: 'Reunião tensa: parte dos moradores fala em bloqueio da estrada de acesso se a poeira não for resolvida esta semana.', categoriaId: 'poeira', tipo: 'reclamacao', criticidade: 5, sentimentoRotulo: 'muito negativo', sentimentoEscore: -0.8, alertaEscalada: true },
      { dataISO: atras(1), canal: '0800', comunidadeId: com3.id, stakeholderId: null, descricao: 'Moradora relatou água turva no córrego perto da captação. Pediu verificação com urgência.', categoriaId: 'agua', tipo: 'reclamacao', criticidade: 4, sentimentoRotulo: 'negativo', sentimentoEscore: -0.3 },
    ];

    let seq = 0;
    const proto = () => `FC-${new Date().getFullYear()}-${String(++seq).padStart(4, '0')}`;
    ats.forEach((a) => {
      a.id = U.id();
      a.protocolo = proto();
      a.criadoISO = a.dataISO;
      dados.atendimentos.push(a);
    });

    const at = (i) => dados.atendimentos[i];

    dados.demandas = [
      {
        id: 'dem-trafego-escola', protocolo: at(1).protocolo, atendimentoId: at(1).id,
        titulo: 'Sinalização e velocidade de caminhões junto à escola',
        descricao: at(1).descricao, categoriaId: 'trafego', area: 'Logística e Infraestrutura',
        comunidadeId: com2.id, stakeholderId: 'stk-rita', criticidade: 3, status: 'encerrada',
        criadoISO: at(1).dataISO, prazoRespostaISO: atras(50), prazoSolucaoISO: atras(35),
        historico: [
          { dataISO: atras(53), texto: 'Encaminhado à Logística com prioridade.' },
          { dataISO: atras(45), texto: 'Instalados redutores e nova sinalização; motoristas orientados.' },
          { dataISO: atras(38), texto: 'Retorno dado à diretora; demanda encerrada com satisfação.' },
        ],
      },
      {
        id: 'dem-trincas', protocolo: at(4).protocolo, atendimentoId: at(4).id,
        titulo: 'Vistoria de trincas em imóveis — Santa Efigênia',
        descricao: at(4).descricao, categoriaId: 'patrimonio', area: 'Engenharia e Patrimônio',
        comunidadeId: com2.id, stakeholderId: null, criticidade: 4, status: 'em_tratamento',
        criadoISO: at(4).dataISO, prazoRespostaISO: atras(27), prazoSolucaoISO: atras(3),
        respondida: true,
        historico: [
          { dataISO: atras(28), texto: 'Primeiro retorno dado ao morador; vistoria solicitada à Engenharia.' },
          { dataISO: atras(14), texto: 'Vistoria realizada em 3 imóveis; laudo em elaboração.' },
        ],
      },
      {
        id: 'dem-poeira', protocolo: at(9).protocolo, atendimentoId: at(9).id,
        titulo: 'Poeira na estrada de acesso — Boa Vista (recorrente)',
        descricao: at(9).descricao, categoriaId: 'poeira', area: 'Meio Ambiente',
        comunidadeId: com1.id, stakeholderId: 'stk-zelia', criticidade: 5, status: 'em_tratamento',
        criadoISO: at(9).dataISO, prazoRespostaISO: atras(8), prazoSolucaoISO: U.agoraISO(),
        respondida: true, alertaEscalada: true,
        historico: [
          { dataISO: atras(8), texto: 'Resposta enviada à associação; umectação extra acionada.' },
          { dataISO: atras(2), texto: 'Reunião com moradores: risco de bloqueio citado. Escalado à gerência.' },
        ],
      },
      {
        id: 'dem-fundiario', protocolo: at(6).protocolo, atendimentoId: at(6).id,
        titulo: 'Posição formal sobre cerca na divisa — Novo Horizonte',
        descricao: at(6).descricao, categoriaId: 'fundiario', area: 'Fundiário',
        comunidadeId: com4.id, stakeholderId: 'stk-geraldo', criticidade: 3, status: 'em_analise',
        criadoISO: at(6).dataISO, prazoRespostaISO: atras(15), prazoSolucaoISO: U.agoraISO(),
        respondida: true,
        historico: [{ dataISO: atras(16), texto: 'Caso encaminhado ao jurídico-fundiário para parecer.' }],
      },
      {
        id: 'dem-festa', protocolo: at(7).protocolo, atendimentoId: at(7).id,
        titulo: 'Patrocínio da festa junina — Boa Vista',
        descricao: at(7).descricao, categoriaId: 'invest_social', area: 'Relações Comunitárias',
        comunidadeId: com1.id, stakeholderId: 'stk-padre', criticidade: 2, status: 'em_tratamento',
        criadoISO: at(7).dataISO, prazoRespostaISO: atras(5), prazoSolucaoISO: frente(8),
        respondida: true,
        historico: [{ dataISO: atras(10), texto: 'Solicitação enquadrada na política de apoios; aguardando aprovação final.' }],
      },
      {
        id: 'dem-emprego', protocolo: at(11).protocolo, atendimentoId: at(11).id,
        titulo: 'Novas turmas de capacitação para jovens — Boa Vista',
        descricao: at(11).descricao, categoriaId: 'emprego', area: 'Recursos Humanos',
        comunidadeId: com1.id, stakeholderId: 'stk-joao', criticidade: 2, status: 'recebida',
        criadoISO: at(11).dataISO, prazoRespostaISO: frente(6), prazoSolucaoISO: frente(26),
        historico: [],
      },
      {
        id: 'dem-imprensa', protocolo: at(10).protocolo, atendimentoId: at(10).id,
        titulo: 'Cobrança do vereador sobre vistorias de trincas',
        descricao: at(10).descricao, categoriaId: 'patrimonio', area: 'Engenharia e Patrimônio',
        comunidadeId: com2.id, stakeholderId: 'stk-carlos', criticidade: 4, status: 'recebida',
        criadoISO: at(10).dataISO, prazoRespostaISO: U.agoraISO(), prazoSolucaoISO: frente(4),
        alertaEscalada: true,
        historico: [],
      },
      {
        id: 'dem-agua', protocolo: at(13).protocolo, atendimentoId: at(13).id,
        titulo: 'Água turva no córrego próximo à captação — Córrego Fundo',
        descricao: at(13).descricao, categoriaId: 'agua', area: 'Meio Ambiente',
        comunidadeId: com3.id, stakeholderId: null, criticidade: 4, status: 'recebida',
        criadoISO: at(13).dataISO, prazoRespostaISO: frente(1), prazoSolucaoISO: frente(9),
        historico: [],
      },
    ];
    dados.config.seqProtocolo = seq;

    dados.compromissos = [
      { id: U.id(), titulo: 'Reparo das trincas vistoriadas (acordo com moradores)', origem: 'acordo', comunidadeId: com2.id, responsavel: 'Engenharia e Patrimônio', prazoISO: frente(3), status: 'em_andamento', descricao: 'Conclusão dos reparos nos 3 imóveis vistoriados, conforme acordo da reunião.', criadoISO: atras(14) },
      { id: U.id(), titulo: 'Condicionante LO 12: monitoramento participativo de poeira', origem: 'condicionante', comunidadeId: com1.id, responsavel: 'Meio Ambiente', prazoISO: frente(12), status: 'em_andamento', descricao: 'Instalar 2 pontos de monitoramento com participação da comunidade e divulgar resultados mensais.', criadoISO: atras(60) },
      { id: U.id(), titulo: 'Umectação reforçada da estrada de acesso (3x ao dia)', origem: 'acordo', comunidadeId: com1.id, responsavel: 'Operação de Mina', prazoISO: frente(1), status: 'em_andamento', descricao: 'Compromisso assumido na reunião com a associação até a pavimentação do trecho crítico.', criadoISO: atras(8) },
      { id: U.id(), titulo: 'Apoio à festa junina (resposta formal à paróquia)', origem: 'acordo', comunidadeId: com1.id, responsavel: 'Relações Comunitárias', prazoISO: frente(5), status: 'pendente', descricao: 'Formalizar a aprovação do patrocínio antes da festa.', criadoISO: atras(10) },
      { id: U.id(), titulo: 'Simulado anual de emergência ZAS', origem: 'condicionante', comunidadeId: com3.id, responsavel: 'Geotecnia e Emergência', prazoISO: frente(20), status: 'pendente', descricao: 'Simulado com a Defesa Civil; comunicação prévia porta a porta.', criadoISO: atras(40) },
      { id: U.id(), titulo: 'Relatório trimestral às lideranças (transparência)', origem: 'plano', comunidadeId: null, responsavel: 'Relações Comunitárias', prazoISO: atras(2), status: 'pendente', descricao: 'Envio do resumo trimestral de ações às lideranças cadastradas.', criadoISO: atras(30) },
    ];

    dados.agenda = [
      { id: U.id(), titulo: 'Visita de campo — Boa Vista (pauta: poeira e bloqueio)', dataISO: frente(0), tipo: 'visita', comunidadeId: com1.id, notas: 'Levar cronograma de umectação impresso. Encontrar Zélia às 9h.', concluido: false },
      { id: U.id(), titulo: 'Reunião com Engenharia — laudo das trincas', dataISO: frente(1), tipo: 'reuniao', comunidadeId: com2.id, notas: 'Alinhar resposta ao vereador antes que o caso vá à imprensa.', concluido: false },
      { id: U.id(), titulo: 'Comitê comunitário — Córrego Fundo', dataISO: frente(3), tipo: 'reuniao', comunidadeId: com3.id, notas: 'Pauta: resultado da análise da água + preparação do simulado.', concluido: false },
      { id: U.id(), titulo: 'Entrega da resposta formal — Novo Horizonte', dataISO: frente(7), tipo: 'visita', comunidadeId: com4.id, notas: 'Posição do Fundiário sobre a cerca da divisa.', concluido: false },
    ];
  }

  raiz.FalaDB = {
    init,
    get,
    porId,
    add,
    update,
    remove,
    getConfig,
    setConfig,
    proximoProtocolo,
    exportarJSON,
    importarJSON,
    exportarCSV,
    limparTudo,
    seedDemo: () => { seedDemo(); dados.config.demoCarregada = true; salvar(); },
  };
})(typeof self !== 'undefined' ? self : globalThis);
