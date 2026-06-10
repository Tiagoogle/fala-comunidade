/* Smoke test: renderiza todas as telas em Node (sem navegador) e confere
 * que produzem HTML com o conteúdo esperado: node tools/test-views.mjs
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
for (const arquivo of ['app/js/util.js', 'app/js/ia.js', 'app/js/db.js', 'app/js/stats.js', 'app/js/views.js']) {
  (0, eval)(readFileSync(join(raiz, arquivo), 'utf8'));
}
const { FalaDB: DB, FalaViews: V } = globalThis;
DB.init();

let passou = 0;
let falhou = 0;
function ok(cond, nome) {
  if (cond) { passou++; console.log('  ✔', nome); }
  else { falhou++; console.error('  ✘', nome); }
}

const demanda = DB.get('demandas')[0];
const pessoa = DB.get('stakeholders')[0];
const atendimento = DB.get('atendimentos').find((a) => a.id === DB.get('demandas')[2].atendimentoId);
DB.update('atendimentos', atendimento.id, { demandaId: DB.get('demandas')[2].id });

const telas = [
  ['inicio', () => V.inicio(), 'Risco social'],
  ['registrar', () => V.registrar({}), 'form-atendimento'],
  ['registrar?stk', () => V.registrar({ stk: pessoa.id }), pessoa.nome],
  ['confirmacao', () => V.confirmacao({ id: atendimento.id }), atendimento.protocolo],
  ['demandas', () => V.demandas({}), 'Demandas'],
  ['demandas?f=risco', () => V.demandas({ f: 'risco' }), 'chip'],
  ['demandas?q', () => V.demandas({ f: 'todas', q: 'poeira' }), 'Poeira'],
  ['demanda/:id', () => V.demandaDetalhe({ id: demanda.id }), demanda.protocolo],
  ['pessoas', () => V.pessoas({}), 'Stakeholders'],
  ['pessoa/:id', () => V.pessoaDetalhe({ id: pessoa.id }), pessoa.nome],
  ['pessoa/:id?editar', () => V.pessoaDetalhe({ id: pessoa.id, editar: '1' }), 'form-pessoa'],
  ['pessoa/nova', () => V.pessoaDetalhe({ id: 'nova' }), 'Novo stakeholder'],
  ['compromissos', () => V.compromissos(), 'Compromissos'],
  ['compromisso-novo', () => V.compromissoNovo(), 'form-compromisso'],
  ['agenda', () => V.agenda(), 'Agenda'],
  ['agenda-novo', () => V.agendaNovo(), 'form-agenda'],
  ['relatorios 7d', () => V.relatorios({ dias: '7' }), 'RESUMO EXECUTIVO'],
  ['relatorios 30d', () => V.relatorios({}), 'comunicado'],
  ['assistente', () => V.assistente([]), 'FalaIA'],
  ['assistente c/ chat', () => V.assistente([{ de: 'eu', texto: 'oi' }, { de: 'ia', texto: 'olá' }]), 'olá'],
  ['mais', () => V.mais(), 'Ajustes'],
  ['ajustes', () => V.ajustes(), 'LGPD'],
];

console.log('Renderização das telas');
for (const [nome, fn, esperado] of telas) {
  try {
    const html = fn();
    ok(typeof html === 'string' && html.includes(esperado), `${nome} (contém "${esperado}")`);
  } catch (e) {
    ok(false, `${nome} — lançou erro: ${e.message}`);
  }
}

console.log('Sanidade do HTML');
const inicio = V.inicio();
ok(!/undefined|NaN|\[object Object\]/.test(inicio), 'início sem vazamentos de undefined/NaN');
const todas = telas.map(([, fn]) => { try { return fn(); } catch { return ''; } }).join('');
ok(!/\bundefined\b/.test(todas.replace(/data-action/g, '')), 'nenhuma tela vaza "undefined"');

console.log(`\n${passou} passaram, ${falhou} falharam`);
process.exit(falhou ? 1 : 0);
