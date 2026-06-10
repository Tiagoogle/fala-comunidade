/* Testes do motor FalaIA (roda em Node: node tools/test-ia.mjs) */
import { readFileSync } from 'node:fs';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

const raiz = join(dirname(fileURLToPath(import.meta.url)), '..');
for (const arquivo of ['app/js/util.js', 'app/js/ia.js']) {
  (0, eval)(readFileSync(join(raiz, arquivo), 'utf8'));
}
const IA = globalThis.FalaIA;

let passou = 0;
let falhou = 0;
function ok(cond, nome) {
  if (cond) { passou++; console.log('  ✔', nome); }
  else { falhou++; console.error('  ✘', nome); }
}

console.log('Classificação de categoria');
ok(IA.classificarCategoria('Muita poeira na estrada, roupas sujas no varal').id === 'poeira', 'poeira');
ok(IA.classificarCategoria('A detonação de ontem tremeu as janelas').id === 'ruido_vibracao', 'detonação → ruído/vibração');
ok(IA.classificarCategoria('Apareceram trincas e rachaduras na parede da cozinha').id === 'patrimonio', 'trincas → patrimônio');
ok(IA.classificarCategoria('A água do córrego está turva perto da captação').id === 'agua', 'água');
ok(IA.classificarCategoria('Quando toca a sirene da barragem temos que ir ao ponto de encontro?').id === 'barragens', 'sirene/ZAS → barragens');
ok(IA.classificarCategoria('Gostaria de me candidatar a uma vaga de emprego').id === 'emprego', 'emprego');
ok(IA.classificarCategoria('Pedimos patrocínio para a festa junina da comunidade').id === 'invest_social', 'patrocínio → investimento social');
ok(IA.classificarCategoria('Obrigado pelo apoio, parabéns à equipe!').id === 'elogio', 'elogio');
ok(IA.classificarCategoria('xyz abc 123').id === 'outros', 'sem pista → outros');

console.log('Sentimento');
ok(IA.sentimento('Estamos revoltados, é um absurdo, ninguém resolve!').escore < -0.4, 'muito negativo');
ok(IA.sentimento('Muito obrigado, excelente trabalho, parabéns!').escore > 0.4, 'positivo');
ok(IA.sentimento('A reunião será na quinta-feira.').rotulo === 'neutro', 'neutro');

console.log('Criticidade e escalada');
const tenso = IA.analisar('Se a poeira não for resolvida vamos fazer bloqueio da estrada e chamar a imprensa!');
ok(tenso.criticidade >= 4, 'bloqueio/imprensa eleva criticidade (>=4)');
ok(tenso.avisos.some((a) => a.includes('escalada')), 'gera aviso de escalada');
ok(IA.analisar('Obrigado pela visita de ontem!').criticidade === 1, 'elogio = criticidade 1');
const urgente = IA.analisar('Urgente: crianças da escola estão tossindo com a poeira, situação de risco');
ok(urgente.criticidade >= 4, 'urgência + escola eleva criticidade');

console.log('Tipo sugerido e demanda');
ok(IA.analisar('Solicito apoio com doação de tinta para a quadra').tipo === 'solicitacao', 'solicitação');
ok(IA.analisar('Reclamação: barulho insuportável de madrugada').tipo === 'reclamacao', 'reclamação');
ok(IA.analisar('Qual a data da próxima reunião? Tenho uma dúvida.').tipo === 'informacao', 'informação');
ok(IA.analisar('Reclamação: poeira demais').geraDemanda === true, 'reclamação gera demanda');
ok(IA.analisar('Obrigado pela ajuda!').geraDemanda === false, 'elogio não gera demanda');

console.log('SLA');
ok(IA.slaPorCriticidade(5).resposta === 1 && IA.slaPorCriticidade(5).solucao === 5, 'crítica: 1d/5d');
ok(IA.slaPorCriticidade(2).resposta === 10, 'baixa: 10d');
ok(IA.slaPorCriticidade(99).resposta === 1, 'criticidade fora da faixa é grampeada');

console.log('Risco social');
const alto = IA.indiceRisco({ criticidadeMedia: 4.5, percSlaEstourado: 0.5, tendencia: 0.8, sentimentoMedio: -0.6, alertasEscalada: 2 });
ok(alto.nivel === 'Alto' && alto.score >= 65, 'cenário crítico → Alto');
const calmo = IA.indiceRisco({ criticidadeMedia: 1.5, percSlaEstourado: 0, tendencia: 0, sentimentoMedio: 0.2, alertasEscalada: 0 });
ok(calmo.nivel === 'Controlado', 'cenário calmo → Controlado');
ok(alto.fatores.length > 0 && calmo.fatores.length > 0, 'sempre explica os fatores');

console.log('Geração de textos');
const resp = IA.respostaSugerida({ nome: 'Zélia', protocolo: 'FC-2026-0001', categoriaId: 'poeira', analista: 'Tiago' });
ok(resp.includes('FC-2026-0001') && resp.includes('Zélia') && resp.toLowerCase().includes('umectação'), 'resposta cita protocolo, nome e ação');
const com = IA.gerarComunicado('detonacao', { comunidade: 'Boa Vista', data: '12/06/2026', hora: '14h' });
ok(com.includes('DETONAÇÃO') && com.toUpperCase().includes('BOA VISTA') && com.includes('12/06/2026'), 'comunicado de detonação completo');

const rel = IA.gerarRelatorio({
  periodo: 'últimos 30 dias', totalAtendimentos: 14, variacaoAtendimentos: 0.3,
  novasDemandas: 6, demandasEncerradas: 1, demandasAbertas: 7, percSlaNoPrazo: 0.71,
  sentimentoRotulo: 'negativo', elogios: 1,
  temaTop: { id: 'poeira', nome: 'Poeira e Qualidade do Ar', qtd: 4 },
  temas: [{ id: 'poeira', nome: 'Poeira e Qualidade do Ar', qtd: 4 }],
  territorios: [{ nome: 'Boa Vista', score: 78, nivel: 'Alto', fatores: ['x'] }],
  territorioMaisCritico: { nome: 'Boa Vista', score: 78, nivel: 'Alto' },
  compromissosVencendo: [{ titulo: 'Umectação reforçada', prazo: 'vence amanhã' }],
  alertasEscalada: 1,
  stakeholdersSemContato: [],
});
ok(rel.includes('RESUMO EXECUTIVO') && rel.includes('RECOMENDAÇÕES'), 'relatório tem resumo e recomendações');
ok(rel.includes('71%') && rel.includes('Boa Vista'), 'relatório usa os números reais');
ok(rel.toLowerCase().includes('umectação'), 'recomendação coerente com tema top (poeira)');
ok(rel.toLowerCase().includes('crise') || rel.toLowerCase().includes('escalada') || rel.toLowerCase().includes('bloqueio'), 'alerta de escalada vira recomendação');

console.log(`\n${passou} passaram, ${falhou} falharam`);
process.exit(falhou ? 1 : 0);
