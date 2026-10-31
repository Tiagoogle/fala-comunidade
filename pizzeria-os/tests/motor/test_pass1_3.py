from conciliacao.canonical import parse_settlement_csv
from conciliacao.models import Channel, EventType, ExceptionStatus, ExceptionType, MatchMethod, MatchStatus
from tests.conftest import SALES_CYCLE, T, expected_for, make_input, settle_csv


def lines(calendar, rows):
    out, rep = parse_settlement_csv(T, Channel.IFOOD, settle_csv(rows), calendar)
    assert not rep.errors
    return out


def test_ct_1_1_exact_match_confidence_one(engine, ifood_rule, calendar):
    exp = expected_for(ifood_rule, calendar, "IF-2", 6890, promo=796)
    res = engine.run(make_input(exp, lines(calendar, [("IF-2", "venda", "52,06"), ("IF-2", "promocao", "-3,98")])))
    order = [m for m in res.matches if m.match_method is not MatchMethod.BANK]
    assert {(m.status, m.confidence, m.delta_cents) for m in order} == {(MatchStatus.MATCHED, 1.0, 0)}
    assert not [e for e in res.exceptions if e.type is not ExceptionType.DIFERENCA_CAIXA]


def test_ct_1_2_within_tolerance_absorbed(engine, ifood_rule, calendar):
    exp = expected_for(ifood_rule, calendar, "IF-4", 6890)                 # esperado 52,06; tolerância 0,34
    res = engine.run(make_input(exp, lines(calendar, [("IF-4", "venda", "51,80")])))
    assert not [e for e in res.exceptions if e.type is ExceptionType.TAXA_DIVERGENTE]
    assert res.matches[0].status is MatchStatus.WITHIN_TOLERANCE


def test_ct_1_3_above_tolerance_typed_with_cause(engine, ifood_rule, calendar):
    exp = expected_for(ifood_rule, calendar, "IF-3", 10000)                # esperado 76,01
    res = engine.run(make_input(exp, lines(calendar, [("IF-3", "venda", "73,01")])))
    (exc,) = [e for e in res.exceptions if e.type is ExceptionType.TAXA_DIVERGENTE]
    assert exc.amount_cents == 300 and "26.00%" in exc.probable_cause


def test_ct_1_4_prd_example_promo_debited_in_full(engine, ifood_rule, calendar):
    # R$ 68,90; 23% + R$ 0,99; desconto R$ 7,96 cofinanciado 50/50 → esperado R$ 48,08, reportado R$ 44,10
    exp = expected_for(ifood_rule, calendar, "IF-1", 6890, promo=796)
    assert sum(e.expected_net_cents for e in exp) == 4808
    res = engine.run(make_input(exp, lines(calendar, [("IF-1", "venda", "44,10")])))
    (exc,) = [e for e in res.exceptions if e.type is ExceptionType.TAXA_DIVERGENTE]
    assert exc.probable_cause == "promoção cofinanciada debitada integralmente"
    assert exc.amount_cents == 398


def test_refund_without_commission_reversal(engine, ifood_rule, calendar):
    exp = expected_for(ifood_rule, calendar, "IF-R", 2000, et=EventType.REFUND)   # esperado -15,40
    res = engine.run(make_input(exp, lines(calendar, [("IF-R", "estorno", "-20,00")])))
    (exc,) = [e for e in res.exceptions if e.type is ExceptionType.TAXA_DIVERGENTE]
    assert exc.probable_cause == "estorno sem reversão da comissão prevista em contrato" and exc.amount_cents == 460


def test_systematic_drift_below_tolerance_is_flagged(engine, ifood_rule, calendar):
    exp, rows = [], []
    for i in range(12):
        exp += expected_for(ifood_rule, calendar, f"D{i}", 10000)
        rows.append((f"D{i}", "venda", "75,56"))                           # 45 centavos a menos, todo pedido
    res = engine.run(make_input(exp, lines(calendar, rows)))
    (drift,) = [e for e in res.exceptions if e.type is ExceptionType.DERIVA_SISTEMATICA]
    assert drift.amount_cents == 12 * 45


def test_overpayment_not_recoverable(engine, ifood_rule, calendar):
    exp = expected_for(ifood_rule, calendar, "IF-7", 10000)
    res = engine.run(make_input(exp, lines(calendar, [("IF-7", "venda", "80,00")]), closed=(SALES_CYCLE,)))
    (exc,) = [e for e in res.exceptions if e.type is ExceptionType.TAXA_DIVERGENTE]
    assert exc.amount_cents < 0 and exc.status is ExceptionStatus.HUMAN_QUEUE
    assert res.metrics["recoverable_cents"] == 0


def test_ct_2_1_missing_settlement_after_close(engine, ifood_rule, calendar):
    exp = expected_for(ifood_rule, calendar, "IF-5", 5000)
    res = engine.run(make_input(exp, []))
    (exc,) = [e for e in res.exceptions if e.type is ExceptionType.VENDA_SEM_REPASSE]
    assert exc.amount_cents == exp[0].expected_net_cents


def test_ct_2_2_open_cycle_no_exception(engine, ifood_rule, calendar):
    exp = expected_for(ifood_rule, calendar, "IF-5", 5000)
    res = engine.run(make_input(exp, [], closed=()))
    assert not res.exceptions and len(res.pending_expected) == 1


def test_pending_refund_is_future_debit_not_missing(engine, ifood_rule, calendar):
    exp = expected_for(ifood_rule, calendar, "IF-6", 5000) + expected_for(ifood_rule, calendar, "IF-6", 5000, et=EventType.REFUND)
    res = engine.run(make_input(exp, lines(calendar, [("IF-6", "venda", "37,51")])))
    assert not [e for e in res.exceptions if e.type is ExceptionType.VENDA_SEM_REPASSE]
    assert [e.event_type for e in res.pending_expected] == [EventType.REFUND]


def test_ct_3_1_unknown_settlement_to_human_queue(engine, calendar):
    res = engine.run(make_input([], lines(calendar, [("XYZ-ABC", "venda", "10,00")])))
    (exc,) = [e for e in res.exceptions if e.type is ExceptionType.REPASSE_SEM_VENDA]
    assert exc.status is ExceptionStatus.HUMAN_QUEUE


def test_ct_3_2_recanonicalize_before_human_queue(engine, ifood_rule, calendar):
    exp = expected_for(ifood_rule, calendar, "PED123", 5000)               # PDV usa prefixo próprio
    res = engine.run(make_input(exp, lines(calendar, [("000123", "venda", "37,51")])))
    assert not [e for e in res.exceptions if e.type in (ExceptionType.REPASSE_SEM_VENDA, ExceptionType.VENDA_SEM_REPASSE)]
    (m,) = [m for m in res.matches if m.match_method is MatchMethod.KEY_LOOSE]
    assert m.status is MatchStatus.MATCHED and m.confidence < 1.0


def test_ct_3_2_loose_ambiguity_is_not_guessed(engine, ifood_rule, calendar):
    exp = expected_for(ifood_rule, calendar, "A123", 5000) + expected_for(ifood_rule, calendar, "B123", 5000)
    res = engine.run(make_input(exp, lines(calendar, [("123", "venda", "37,51")]), closed=()))
    assert [e.type for e in res.exceptions] == [ExceptionType.REPASSE_SEM_VENDA]


def test_cycle_filter_and_idempotent_fingerprints(engine, ifood_rule, calendar):
    exp = expected_for(ifood_rule, calendar, "IF-1", 6890, promo=796)
    inp = make_input(exp, lines(calendar, [("IF-1", "venda", "44,10")]))
    a, b = engine.run(inp), engine.run(inp)
    assert [e.fingerprint for e in a.exceptions] == [e.fingerprint for e in b.exceptions]
    assert all(e.cycle_id == SALES_CYCLE for e in engine.run(inp, cycle_id=SALES_CYCLE).exceptions)


def test_tenant_isolation_in_engine(engine, ifood_rule, calendar):
    import pytest
    from conciliacao.engine import EngineInput
    exp = expected_for(ifood_rule, calendar, "IF-8", 1000)
    with pytest.raises(PermissionError):
        engine.run(EngineInput("outro", exp, [], [], set(), True))
