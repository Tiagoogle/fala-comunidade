# PIZZERIA OS — Módulo Conciliação e Cobrança

Implementação do PRD *Módulo Conciliação e Cobrança* (30/10/2026). Python 3.11+, FastAPI, Postgres.

```
pip install -e '.[dev]'
pytest                                   # 47 testes
uvicorn conciliacao.api:app --reload     # docs em http://localhost:8000/docs
```

## O que está implementado

| PRD | Módulo | Estado |
| --- | --- | --- |
| §3 Incógnitas 1–3 | `gates.py` | Gates explícitos. Resolver uma incógnita exige evidência e data (`PUT /gates/{gate}`). Os caminhos que dependem dela devolvem **409 `decision_gate_blocked`** |
| §4 Modelo N1/N2/N3 + cobrança | `models.py`, `db/schema.sql` | As 9 tabelas, com valores em centavos `BIGINT`, RLS por tenant com `FORCE`, ledger com trigger anti-UPDATE/DELETE/TRUNCATE e vigências tarifárias sem sobreposição (`EXCLUDE USING gist`). Validado no Postgres 16 |
| §4 Regras versionadas | `fees.py` | `FeeRuleBook` recusa vigência sobreposta. A expectativa é gerada **por evento** (`sale`, `promo`, `refund`) |
| §5 Passe 0 | `canonical.py` | Lê valores em formato BR/US e OFX/CSV bancário, normaliza referências, mapeia o ciclo e deduplica por hash |
| §5 Passes 1–3 | `engine.py` | Chave determinística com a classificação de `probable_cause`, venda sem repasse (só após o fechamento do ciclo) e repasse sem venda (fila humana) |
| §5 Passe 4 | — | **Não escrito, por determinação do PRD §3.** O motor informa o bloqueio em `blocked[]` |
| §5 Caminho degradado (subset-sum) | — | Bloqueado (Incógnita 3). As linhas sem referência são isoladas e totalizadas, sem chute de atribuição |
| §6 Ledger | `ledger.py` | Append-only com hash encadeado **por tenant**, `verify()` detecta adulteração e a confirmação manual funciona em qualquer ramo. `confirm_auto` só roda no ramo simplificador da Incógnita 1 |
| §6 Cobrança | `billing.py` | O piso está liberado, porque é assinatura fixa nos dois ramos da Incógnita 2. O variável calcula a prévia (`preview`), mas a emissão exige 4 condições (ver abaixo) |

O exemplo do PRD está reproduzido em teste (`test_prd_example_promo_debited_in_full`). Pedido de R$ 68,90, comissão de 23% + R$ 0,99, promoção 50/50 com desconto de R$ 7,96. O esperado é R$ 48,08 e o reportado R$ 44,10. O motor gera `taxa_divergente` de R$ 3,98 com a causa "promoção cofinanciada debitada integralmente do lojista".

## Decisões que tomei além do PRD (e por quê)

1. **Deriva sistemática (`deriva_sistematica`).** A tolerância de max(R$ 0,02; 0,5%) cria um ponto cego. Uma comissão cobrada a 23,4% em vez de 23% gera R$ 0,28 a menos num pedido de R$ 68,90, abaixo do limiar de R$ 0,34. Ela seria absorvida *para sempre*, e é justamente o tipo de erro "recorrente, pequeno por pedido, invisível no agregado" que o PRD diz ser o valor do módulo. Por isso, os deltas absorvidos são agregados por canal e ciclo. Com ≥10 matches, ≥80% com o mesmo sinal e soma ≥R$ 5, o motor gera uma exceção.
2. **Faixas marginais**, como no IR, e não em degrau. Com faixas em degrau, recuperar R$ 2.001 cobraria 8% sobre tudo (R$ 160), contra R$ 300 a 15% com R$ 2.000: o lojista pagaria menos recuperando mais, e o ponto de virada vira alvo de disputa. Há um teste de monotonicidade.
3. **Pagamento a maior não é "recuperável".** Delta positivo vai para a fila humana com o aviso "risco de estorno futuro" e fica fora de `recoverable_cents`. Sem isso, a métrica de valor do produto ficaria inflada.
4. **Promo líquida dentro da venda.** Se a plataforma não traz linha própria de promoção, `sale+promo` é casado contra a linha de venda (`key_order_aggregate`, com confiança 0,97). Assim o mesmo motor serve aos dois layouts plausíveis do relatório.
5. **Estorno esperado e ainda não liquidado** fica em `pending_expected`, não vira `venda_sem_repasse`. É débito futuro, não perda do lojista.
6. **`rejected`** como estado terminal do ledger. Sem ele, uma disputa recusada pela plataforma ficaria `disputed` para sempre.
7. **Valor nunca cresce na cadeia** (confirmado ≤ disputado ≤ detectado). Recuperação parcial é permitida.
8. **Idempotência** por `fingerprint`: rodar o motor de novo atualiza a exceção e registra a revisão no histórico, sem duplicar.

## Condições para emitir cobrança variável

`BillingService.emit_variable` só roda se:
1. A Incógnita 2 estiver resolvida (com evidência de sandbox).
2. O `attribution_contract` estiver aceito.
3. Houver pelo menos `min_reconciled_cycles_for_variable` ciclos conciliados (padrão: 4).
4. `variable_arm_enabled=True`, seguindo a rota de lançamento do PRD: piso primeiro.

A base de cálculo é **apenas `confirmed`** e, após a emissão, cada entrada vira `billed` no ledger.

## O que falta para produção

- O adaptador `BillingGateway` do Mercado Pago depende da Incógnita 2. Hoje existe apenas o Protocol e um fake de teste.
- A persistência atual é em memória (`store.py`). O DDL está pronto, falta o repositório Postgres.
- O tenant vem do header `X-Tenant-Id`, o que só serve para desenvolvimento. Em produção ele precisa vir de um claim do JWT.
- O layout real do relatório iFood é desconhecido (é a própria Incógnita 3). Por isso o parser recebe um `SettlementColumnMap` configurável.
- Os parâmetros de tolerância, de deriva e de preço são **hipóteses** e precisam ser recalibrados com ciclos reais.
