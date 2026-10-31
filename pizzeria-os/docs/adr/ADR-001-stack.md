# ADR-001 — Stack tecnológica do Módulo Conciliação e Cobrança

- **Status:** aceito (Fase 0)
- **Data:** 2026-10-31
- **Decisores:** Tiago Tadeu Abjaud (arquitetura) · agente de código (proposta)

## Contexto

O Prompt Mestre §3.1 exige que a stack satisfaça cinco requisitos não negociáveis:
(a) isolamento multi-tenant por RLS + camada de aplicação;
(b) dinheiro em inteiros de 64 bits, sem float em nenhuma camada;
(c) hash criptográfico nativo para o `recovery_ledger`;
(d) fila assíncrona para o SubsetSumSolver;
(e) versionamento temporal de regras tarifárias no banco.

O prompt sugere, sem exclusividade, Next.js 16 + TypeScript + Prisma + PostgreSQL, com o solver em Python e a fila em BullMQ/Redis.

## Decisão

**Python 3.11+ (FastAPI) + PostgreSQL 15+ + RQ/Redis**, com o motor, o ledger e o solver no mesmo processo de domínio.

| Requisito | Como é atendido | Verificação |
| --- | --- | --- |
| (a) RLS + app | `ENABLE` + `FORCE ROW LEVEL SECURITY` com policy `tenant_id = current_setting('app.tenant_id')` em 14 tabelas. Na aplicação, `Store.tenant()` é a única porta de leitura e recusa tenant vazio | `tests/invariantes/test_db_guards.py::test_inv2_rls_isolates_tenants`, `test_invariantes.py::test_inv2_*` |
| (b) int64 sem float | Colunas `BIGINT *_cents`. Os modelos validam `type(v) is int` em runtime. A API usa `StrictInt`. O gateway serializa o valor como literal decimal montado a partir de inteiros, sem float. Um lint AST proíbe literais float e `float()` no pacote | `test_inv1_*` |
| (c) hash | `hashlib.sha256` (stdlib) na aplicação. Um trigger no banco valida o encadeamento e as transições no `INSERT` | `tests/ledger`, `test_ledger_chain_and_transition_enforced_by_db` |
| (d) fila | Interface `JobQueue`. A `InMemoryJobQueue` serve a testes e desenvolvimento. Em produção, RQ sobre Redis com worker separado | `tests/motor/test_subset_sum.py::test_degraded_path_end_to_end`, `tests/test_api.py::test_degraded_flow_via_queue` |
| (e) versionamento | `valid_from`/`valid_to` com `EXCLUDE USING gist` contra sobreposição. A expectativa usa a versão vigente **na data do evento** | `test_inv5_*`, `test_fee_rule_overlap_rejected` |

## Por que não a stack sugerida

1. **Uma linguagem só para o domínio crítico.** Na stack sugerida, a heurística do subset-sum (Python) e a regra de matching (TypeScript) ficariam em linguagens diferentes, e as duas precisam concordar sobre tolerância, canonicalização de referência e centavos. Dois runtimes implicam duas implementações de `normalize_ref` e `tolerance_for`, e a divergência entre elas viraria exceção falsa. Aqui, motor, solver e ledger compartilham o mesmo código.
2. **Prisma e RLS.** O Prisma não define `app.tenant_id` por transação de forma nativa. Isso se resolve com extensões ou `$executeRaw` em cada transação, e é justamente o tipo de detalhe que vaza em produção. Com psycopg, `SET LOCAL` fica explícito no repositório.
3. **Ferramental de dados.** A base do produto é parsear relatórios heterogêneos (CSV, OFX, layout do iFood). O ecossistema Python para isso é mais maduro.

**Custo aceito:** a UI do lojista fica mais simples (HTML estático + `fetch` em `/dashboard`). Se o produto precisar de uma UI rica, ela entra como frontend separado (Next.js) consumindo esta API, sem tocar o domínio.

## Consequências e decisões derivadas

1. **Feature flags por tenant** (`tenant_feature_flags`, com auditoria por trigger) implementam os dois ramos de cada incógnita, como o §8 exige.
2. **Default `settlement_itemized=false` com roteamento por linha.** Pelo §8.4, todo tenant começa com a flag em `false`. Se a flag decidisse o caminho inteiro, todo tenant novo cairia no caminho degradado, contrariando a INV-7. A flag decide **só o destino das linhas sem referência**. Linhas com referência sempre seguem o caminho primário.
3. **Cadeia de hash por tenant, não por exceção.** O §7.2 descreve `verifyChain(exception_id)`. Uma cadeia por exceção não detecta a exclusão de uma recuperação inteira, porque a cadeia some junto com ela. Por isso, a cadeia é única por tenant, e `verify_chain(exception_id)` valida a cadeia inteira mais a trajetória da exceção.
4. **O §9.3 virou trigger.** O PostgreSQL rejeita `CHECK` com subquery (`ERROR: cannot use subquery in check constraint`, reproduzido no PG 16). A guarda equivalente é o trigger `billing_charge_guard`, que também exige a linha de flags (§8) e `variable_capture_enabled` para cobrança `variavel` (INV-8).
5. **Faixas marginais.** "Faixas decrescentes" foram implementadas como alíquota marginal. Em degrau, recuperar R$ 2.001 custaria R$ 160, contra R$ 300 para recuperar R$ 2.000. O teste de monotonicidade garante que recuperar mais nunca reduz o líquido do lojista.

## Risco registrado — viabilidade da Fase 3 (subset-sum)

Simulação em `scripts/subset_sum_ambiguity.py`: n pedidos sem par, com líquido entre R$ 20 e R$ 120, e um depósito igual à soma de n/2 deles. Fração de depósitos com atribuição **única**:

| pedidos sem par | 8 | 10 | 12 | 16 | 20 | 30+ |
| --- | --- | --- | --- | --- | --- | --- |
| atribuição única | 99% | 97% | 88% | 21% | 0% | 0% |

Isso é o princípio da casa dos pombos. Com n pedidos existem 2ⁿ subconjuntos, mas as somas possíveis cabem num intervalo de cerca de n × R$ 100. A partir de ~16 pedidos, muitos subconjuntos produzem exatamente a mesma soma. Uma pizzaria no iFood tem dezenas a centenas de pedidos por ciclo, então **o critério de saída da Fase 3 (auto-match ≥ 65%) é inalcançável com subset-sum puro sobre o ciclo inteiro**.

Além disso, o solver casa contra o líquido **esperado**. Se a plataforma divergiu em qualquer pedido, nenhum subconjunto fecha, e isso acontece justamente quando há valor a recuperar.

**Mitigações a avaliar na Fase 0, antes de investir na Fase 3:**
- Particionar por dia de repasse ou lote, reduzindo n abaixo de ~10 por depósito.
- Usar sinais secundários, como data, canal e forma de pagamento.
- Negociar exportação itemizada com a plataforma.
- Aceitar o degradado só como detector de "o lote não fecha".
