# PIZZERIA OS — Módulo Conciliação e Cobrança

Implementação do **Prompt Mestre v1.0** (30/10/2026), que substitui o PRD original. A stack e a justificativa estão em [`docs/adr/ADR-001-stack.md`](docs/adr/ADR-001-stack.md).

```bash
pip install -e '.[dev]'
pytest                                          # 105 testes (as guardas de banco pedem DATABASE_URL)
DATABASE_URL=postgresql://... pytest            # inclui triggers/RLS contra as migrations reais
uvicorn conciliacao.api:app --reload            # API em /docs · dashboard em /dashboard
python scripts/subset_sum_ambiguity.py          # simulação de viabilidade do caminho degradado
```

## Entregáveis × Prompt Mestre

| § | Entregável | Onde |
| --- | --- | --- |
| 3.1 | ADR-001 com a decisão de stack | `docs/adr/ADR-001-stack.md` |
| 5 | Schema com as 9 tabelas, índices por tenant e migrations versionadas | `db/migrations/0001_core.sql` |
| 6 | `ReconciliationEngine.run_pass0`…`run_pass4` + `run(cycle_id)` | `conciliacao/engine.py` |
| 6.6 | SubsetSumSolver (DP com bitset e **prova de unicidade**) e fila assíncrona | `conciliacao/subset_sum.py`, `conciliacao/jobs.py` |
| 7 | `RecoveryLedgerService.append_entry / verify_chain / transition`, mais triggers append-only e de encadeamento | `conciliacao/ledger.py`, `db/migrations/0003_guards_rls.sql` |
| 8 | `tenant_feature_flags` (3 incógnitas + ativação da Fase 2), default `false`, com auditoria por trigger | `conciliacao/flags.py`, `0002_flags_onboarding.sql` |
| 8.2 | Os dois ramos de cobrança: `SingleMandateGateway` (mandato único) e `TwoInstrumentGateway` (assinatura + avulsa) | `conciliacao/gateways/mercadopago.py` |
| 9 | Onboarding em 5 etapas retomáveis, CNPJ validado, tokens cifrados e calibração sem ledger nem cobrança | `conciliacao/onboarding.py`, `conciliacao/service.py` |
| 9.3 | Guarda do `attribution_contract` no banco (trigger) | `0003_guards_rls.sql` |
| 3.2 | Dashboard de exceções e trilha de recuperação | `conciliacao/static/dashboard.html` |
| 10 | Pasta de retrospectivas com modelo | `docs/retrospectives/` |
| 11 | `tests/{motor,ledger,billing,onboarding,invariantes}` com casos CT-0.1…CT-B.5 e INV-1…8 (positivo e negativo), e CI com cobertura mínima | `tests/`, `.github/workflows/pizzeria-os.yml` |

## Onde desviei do Prompt Mestre, e por quê

1. **CHECK com subquery (§9.3) não existe no PostgreSQL**: o banco devolve `cannot use subquery in check constraint`. Substituí por um trigger com o mesmo efeito, que também exige a linha de flags e, para cobrança variável, a flag da Fase 2.
2. **A cadeia de hash é por tenant, não por exceção (§7.2).** Com cadeia por exceção, apagar uma recuperação inteira passa despercebido. Com cadeia por tenant, isso é detectado (há teste). `verify_chain(exception_id)` continua disponível.
3. **`settlement_itemized=false` por padrão não rebaixa o tenant.** A flag decide apenas o destino das linhas *sem* referência; linhas com referência seguem sempre o caminho primário (INV-7). Se a flag decidisse o motor inteiro, o default da §8.4 colocaria todo tenant novo no caminho caro.
4. **O delta do Passe 1 tem sinal**, embora a §6.3 use `abs()`. Sem o sinal, um pagamento a maior (risco de estorno futuro) apareceria como "valor recuperável" e inflaria a métrica de produto.
5. **Faixas marginais**, como no IR: em degrau, recuperar mais pode custar menos ao lojista.
6. **Ampliações:** `deriva_sistematica`, que pega erros sistemáticos abaixo da tolerância, e o estado `rejected` no ledger, para disputas negadas.

## Riscos que o código não resolve

- **A Fase 3 é inviável como especificada.** A atribuição única por subset-sum cai a 0% acima de ~20 pedidos por depósito (ver ADR-001). Isso precisa ser decidido na Fase 0, antes de investir 3 semanas.
- **O Mercado Pago não foi verificado em sandbox.** Os endpoints seguem a API pública conhecida até jan/2026 e o adaptador está marcado como tal.
- **O layout do relatório do iFood é hipótese.** O cliente OAuth do iFood é só uma interface (Protocol): nenhum endpoint foi inventado.
- **A persistência ainda é em memória.** As migrations e as guardas de banco estão prontas e testadas, mas falta o repositório psycopg com `SET LOCAL app.tenant_id` por transação.
- **A autenticação é de desenvolvimento** (headers `X-Tenant-Id` e `X-Admin-Token`). Em produção, o tenant precisa vir de um claim do JWT.
