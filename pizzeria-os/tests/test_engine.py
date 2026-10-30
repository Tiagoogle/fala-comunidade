from datetime import date

from conciliacao.canonical import SettlementColumnMap, parse_settlement_csv
from conciliacao.engine import reconcile
from conciliacao.fees import compute_expected
from conciliacao.models import Channel, EventType, ExceptionStatus, ExceptionType, MatchStatus, OrderEvent
from tests.conftest import T

D = date(2026, 10, 20)
CYCLE = "ifood:2026-10-19"


def expected_for(rule, calendar, ref, gross, promo=0, et=EventType.SALE):
    return compute_expected(OrderEvent(T, f"o-{ref}", ref, Channel.IFOOD, et, gross, D, promo), rule, calendar)


def settle(calendar, rows: list[tuple[str, str, str]]):
    text = "pedido;tipo;valor_liquido;data_repasse\n" + "\n".join(f"{r};{t};{v};26/10/2026" for r, t, v in rows)
    lines, rep = parse_settlement_csv(T, Channel.IFOOD, text, calendar)
    assert not rep.errors, rep.errors
    return lines


def test_prd_example_promo_debited_in_full(ifood_rule, calendar, gates):
    exp = expected_for(ifood_rule, calendar, "IF-1", 6890, promo=796)
    lines = settle(calendar, [("IF-1", "venda", "44,10")])
    res = reconcile(T, exp, lines, {CYCLE}, gates)
    (exc,) = res.exceptions
    assert exc.type is ExceptionType.TAXA_DIVERGENTE
    assert exc.amount_cents == 398
    assert exc.probable_cause == "promoção cofinanciada debitada integralmente do lojista"
    assert res.matches[0].delta_cents == -398


def test_exact_match_event_level(ifood_rule, calendar, gates):
    exp = expected_for(ifood_rule, calendar, "IF-2", 6890, promo=796)
    lines = settle(calendar, [("IF-2", "venda", "52,06"), ("IF-2", "promocao", "-3,98")])
    res = reconcile(T, exp, lines, {CYCLE}, gates)
    assert not res.exceptions
    assert {m.status for m in res.matches} == {MatchStatus.MATCHED}
    assert res.metrics["auto_match_rate"] == 1.0


def test_commission_divergence_attributed(ifood_rule, calendar, gates):
    exp = expected_for(ifood_rule, calendar, "IF-3", 10000)          # esperado 100 - 23 - 0,99 = 76,01
    lines = settle(calendar, [("IF-3", "venda", "73,01")])           # cobraram 26%
    res = reconcile(T, exp, lines, {CYCLE}, gates)
    (exc,) = res.exceptions
    assert exc.amount_cents == 300
    assert "26.00%" in exc.probable_cause


def test_tolerance_absorbs_rounding(ifood_rule, calendar, gates):
    exp = expected_for(ifood_rule, calendar, "IF-4", 6890)
    lines = settle(calendar, [("IF-4", "venda", "52,05")])
    res = reconcile(T, exp, lines, {CYCLE}, gates)
    assert not res.exceptions and res.matches[0].status is MatchStatus.WITHIN_TOLERANCE


def test_systematic_drift_below_tolerance_is_flagged(ifood_rule, calendar, gates):
    exp, rows = [], []
    for i in range(12):
        exp += expected_for(ifood_rule, calendar, f"IF-D{i}", 10000)    # esperado 76,01; tolerância 0,50
        rows.append((f"IF-D{i}", "venda", "75,56"))                       # 45 centavos a menos, todo pedido
    res = reconcile(T, exp, settle(calendar, rows), {CYCLE}, gates)
    (drift,) = res.exceptions
    assert drift.type is ExceptionType.DERIVA_SISTEMATICA
    assert drift.amount_cents == 12 * 45


def test_pass2_only_after_cycle_closed(ifood_rule, calendar, gates):
    exp = expected_for(ifood_rule, calendar, "IF-5", 5000)
    assert not reconcile(T, exp, [], set(), gates).exceptions
    res = reconcile(T, exp, [], {CYCLE}, gates)
    (exc,) = res.exceptions
    assert exc.type is ExceptionType.VENDA_SEM_REPASSE and exc.amount_cents == exp[0].expected_net_cents


def test_pending_refund_not_flagged_as_missing(ifood_rule, calendar, gates):
    exp = expected_for(ifood_rule, calendar, "IF-6", 5000) + expected_for(ifood_rule, calendar, "IF-6", 5000, et=EventType.REFUND)
    lines = settle(calendar, [("IF-6", "venda", f"{(5000 - 1150 - 99) / 100:.2f}".replace('.', ','))])
    res = reconcile(T, exp, lines, {CYCLE}, gates)
    assert not res.exceptions
    assert [e.event_type for e in res.pending_expected] == [EventType.REFUND]


def test_pass3_goes_to_human_queue(ifood_rule, calendar, gates):
    res = reconcile(T, [], settle(calendar, [("IF-X", "venda", "10,00")]), set(), gates)
    (exc,) = res.exceptions
    assert exc.type is ExceptionType.REPASSE_SEM_VENDA and exc.status is ExceptionStatus.HUMAN_QUEUE


def test_overpayment_not_recoverable(ifood_rule, calendar, gates):
    exp = expected_for(ifood_rule, calendar, "IF-7", 10000)
    res = reconcile(T, exp, settle(calendar, [("IF-7", "venda", "80,00")]), {CYCLE}, gates)
    (exc,) = res.exceptions
    assert exc.amount_cents < 0 and exc.status is ExceptionStatus.HUMAN_QUEUE
    assert res.metrics["recoverable_cents"] == 0


def test_aggregate_report_and_pass4_are_blocked(ifood_rule, calendar, gates):
    text = "valor_liquido;data_repasse\n1500,00;26/10/2026\n"
    lines, _ = parse_settlement_csv(T, Channel.IFOOD, text, calendar, SettlementColumnMap(order_ref=None, line_type=None))
    res = reconcile(T, [], lines, set(), gates)
    assert not res.exceptions
    assert any("subset-sum" in b for b in res.blocked)
    assert any("Passe 4" in b for b in res.blocked)


def test_adjustments_are_separated_for_confirmation_loop(calendar, gates):
    lines = settle(calendar, [("IF-1", "ajuste", "3,98")])
    res = reconcile(T, [], lines, set(), gates)
    assert not res.exceptions and len(res.adjustment_lines) == 1


def test_tenant_isolation(ifood_rule, calendar, gates):
    import pytest
    exp = expected_for(ifood_rule, calendar, "IF-8", 1000)
    with pytest.raises(PermissionError):
        reconcile("outro-tenant", exp, [], set(), gates)


def test_settlement_dedup(calendar):
    text = "pedido;tipo;valor_liquido;data_repasse\nIF-1;venda;10,00;26/10/2026\n"
    seen = set()
    a, _ = parse_settlement_csv(T, Channel.IFOOD, text, calendar, seen_hashes=seen)
    b, rep = parse_settlement_csv(T, Channel.IFOOD, text, calendar, seen_hashes=seen)
    assert len(a) == 1 and not b and rep.duplicates == 1
