/* Teste de integração: seed de demonstração + indicadores + relatório.
 * Roda em Node com um stub de localStorage: node tools/test-stats.mjs
 */
import { readFileSync } from 'node:fs';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

const memoria = new Map();
globalThis.localStorage = {
  getItem: (k) => (memoria.has(k) ? memoria.get(k) : null),
  setItem: (k, v) => memoria.set(k, String(v)),
  removeItem: (k) => memoria.delete(k),
};

const raiz = join(dirname(fileURLToPath(import.meta.url)), '..');
for (const arquivo of ['app/js/util.js', 'app/js/ia.js', 'app/js/db.js', 'app/js/stats.js']) {
  (0, eval)(readFileSync(join(raiz, arquivo), 'utf8'));
}
const { FalaDB: DB, FalaStats: ST, FalaIA: IA } = globalThis;

let passou = 0;
let falhou = 0;
function ok(cond, nome) {
  if (cond) { passou++; console.log('  ✔', nome); }
  else { falhou++; console.error('  ✘', nome); }
}

DB.init();

console.log('Seed de demonstração');
ok(DB.get('comunidades').length === 4, '4 comunidades');
ok(DB.get('stakeholders').length === 8, '8 stakeholders');
ok(DB.get('atendimentos').length === 14, '14 atendimentos');
ok(DB.get('demandas').length === 8, '8 demandas');
ok(DB.getConfig().demoCarregada === true, 'flag de demo ativa');

console.log('Protocolos');
const p1 = DB.proximoProtocolo();
const p2 = DB.proximoProtocolo();
ok(/^FC-\d{4}-\d{4}$/.test(p1), 'formato FC-AAAA-NNNN');
ok(p1 !== p2, 'sequencial único');

console.log('SLA e demandas em risco');
const emRisco = ST.demandasEmRisco();
ok(emRisco.length >= 2, 'demo traz demandas com prazo em risco');
ok(emRisco.every((x) => x.sla.estourado || x.sla.urgente), 'filtro coerente');
const encerrada = DB.get('demandas').find((d) => d.status === 'encerrada');
ok(ST.situacaoSLA(encerrada).fase === 'concluida', 'encerrada não conta SLA');

console.log('Risco por comunidade');
const riscos = ST.riscoPorComunidade();
ok(riscos.length === 4, 'avalia as 4 comunidades');
const topDois = riscos.slice(0, 2).map((r) => r.comunidade.id).sort();
ok(topDois.join(',') === 'com-boavista,com-santaef', 'Boa Vista e Santa Efigênia lideram o risco no demo');
ok(riscos[0].risco.nivel === 'Alto' && riscos[1].risco.nivel === 'Alto', 'ambas em nível Alto');
const boaVista = riscos.find((r) => r.comunidade.id === 'com-boavista');
ok(boaVista.risco.fatores.some((f) => f.includes('bloqueio')), 'ameaça de bloqueio aparece como fator');
ok(riscos[3].risco.nivel === 'Controlado', 'há comunidade sob controle (contraste)');

console.log('Temas e stakeholders');
const temas = ST.temasEmAlta(30);
ok(temas[0].id === 'poeira', 'poeira é o tema nº 1 dos 30 dias');
ok(ST.stakeholdersSemContato(30).length >= 1, 'detecta relacionamento esfriando');
ok(ST.quadranteStakeholder({ influencia: 5, interesse: 5 }) === 'Gerenciar de perto', 'matriz influência × interesse');

console.log('Relatório integrado');
const rel = IA.gerarRelatorio(ST.dadosRelatorio(30));
ok(rel.includes('RESUMO EXECUTIVO') && rel.includes('Boa Vista'), 'relatório nasce dos dados reais');
ok(/\d+ atendimentos/.test(rel) || /Atendimentos registrados: \d+/.test(rel), 'números presentes');

console.log('Exportações');
ok(DB.exportarCSV('demandas').split('\n').length === DB.get('demandas').length + 1, 'CSV com cabeçalho + linhas');
ok(JSON.parse(DB.exportarJSON()).atendimentos.length === 14, 'backup JSON íntegro');

console.log(`\n${passou} passaram, ${falhou} falharam`);
process.exit(falhou ? 1 : 0);
