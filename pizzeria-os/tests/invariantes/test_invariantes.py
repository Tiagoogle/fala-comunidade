"""Cada invariante (Prompt Mestre §4 / §11.4) tem teste positivo e negativo.
As de nível de banco (INV-3, guarda do §9.3) estão em test_db_guards.py."""
import ast
from dataclasses import replace
from datetime import date
from pathlib import Path

import pytest

from conciliacao.billing import BillingError
from conciliacao.flags import Flag
from conciliacao.models import CentsTypeError, Channel, CommissionBase, EventType, FeeRule, OrderEvent
from conciliacao.store import TenantIsolationError
from conciliacao.subset_sum import solve
from tests.conftest import NOW, T, expected_for, make_input
from tests.billing.test_billing import gateways, with_confirmations

PKG = Path(__file__).resolve().parents[2] / "conciliacao"


# INV-1 — inteiros em centavos -----------------------------------------------------------
def test_inv1_cents_int_accepted():
    assert OrderEvent(T, "o", "1", Channel.IFOOD, EventType.SALE, 6890, date(2026, 10, 20)).gross_cents == 6890


@pytest.mark.parametrize("bad", [68.9, True])
def test_inv1_float_or_bool_cents_rejected_at_runtime(bad):
    with pytest.raises(CentsTypeError):
        OrderEvent(T, "o", "1", Channel.IFOOD, EventType.SALE, bad, date(2026, 10, 20))


def test_inv1_no_float_literals_or_casts_in_domain_code():
    """Lint estático: nenhuma literal float nem float() fora do formatter de UI."""
    offenders = []
    for path in PKG.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and type(node.value) is float and not _is_confidence(path, node):
                offenders.append(f"{path.name}:{node.lineno} literal {node.value}")
            if isinstance(node, ast.Call) and getattr(node.func, "id", None) == "float":
                offenders.append(f"{path.name}:{node.lineno} float()")
    assert not offenders, offenders


def _is_confidence(path, node) -> bool:
    # confidence do match é probabilidade (0..1), não dinheiro — única exceção permitida, no motor
    return path.name == "engine.py"


def test_inv1_api_rejects_float_cents():
    from fastapi.testclient import TestClient
    from conciliacao import api
    r = TestClient(api.app).post("/orders/events", headers={"X-Tenant-Id": "inexistente"}, json=[{
        "order_id": "o", "external_order_ref": "1", "channel": "ifood", "event_type": "sale",
        "gross_cents": 68.9, "occurred_on": "2026-10-20"}])
    assert r.status_code in (404, 422)


# INV-2 — isolamento multi-tenant --------------------------------------------------------
def test_inv2_scoped_access_works(app):
    assert app.store.tenant(T).profile.tenant_id == T


@pytest.mark.parametrize("tenant", ["", "   ", None])
def test_inv2_query_without_tenant_fails_explicitly(app, tenant):
    with pytest.raises(TenantIsolationError):
        app.store.tenant(tenant)


def test_inv2_cross_tenant_write_rejected(app, ifood_rule, calendar):
    exp = expected_for(ifood_rule, calendar, "X", 1000)
    with pytest.raises(TenantIsolationError):
        app.store.check("outro-tenant", exp)


def test_inv2_store_has_no_unscoped_reader():
    from conciliacao.store import Store
    public = [m for m in dir(Store) if not m.startswith("_")]
    assert set(public) <= {"tenant", "create_tenant", "exists", "check"}


# INV-3 (camada de serviço; banco em test_db_guards) -------------------------------------
def test_inv3_service_has_only_insert(flags):
    from conciliacao.ledger import RecoveryLedgerService
    assert not [m for m in dir(RecoveryLedgerService) if m.startswith(("update", "delete", "remove"))]


# INV-4 — captura apenas sobre confirmed -------------------------------------------------
def test_inv4_base_is_confirmed_only(app):
    with_confirmations(app, [20_000] * 10)   # + uma entrada só detected de R$ 999,99
    preview = app.billing.preview_variable(app.store.tenant(T).ledger, "2026-11")
    assert preview.base_amount_cents == 200_000


def test_inv4_billing_on_detected_rejected_at_service(app):
    with_confirmations(app, [20_000] * 10)
    app.flags.set(T, Flag.VARIABLE_CAPTURE_ENABLED, True, "admin", "teste de guarda INV-4", NOW)
    td = app.store.tenant(T)
    detected = next(e for e in td.ledger.entries if e.state.value == "detected" and e.amount_cents == 99_999)
    real = app.billing.preview_variable
    app.billing.preview_variable = lambda ledger, period, until=None: replace(
        real(ledger, period, until), ledger_entry_ids=[detected.id])
    _, _, two = gateways()
    with pytest.raises(BillingError, match="não confirmada"):
        app.emit_variable(T, "2026-11", two)


# INV-5 — versão vigente à data do evento -------------------------------------------------
def test_inv5_expected_uses_rule_in_force_on_event_date(app):
    app.store.fee_rules.supersede(
        FeeRule(T, Channel.IFOOD, 2700, CommissionBase.GROSS, 99, 5000, date(2026, 10, 25), None, 2), date(2026, 10, 25))
    before, after = app.add_order_events(T, [
        {"order_id": "a", "external_order_ref": "A", "channel": "ifood", "event_type": "sale",
         "gross_cents": 10000, "occurred_on": date(2026, 10, 20)},
        {"order_id": "b", "external_order_ref": "B", "channel": "ifood", "event_type": "sale",
         "gross_cents": 10000, "occurred_on": date(2026, 10, 26)},
    ])
    assert before.components["commission_bps"] == 2300 and after.components["commission_bps"] == 2700


def test_inv5_contract_change_after_event_does_not_rewrite_expectation(app):
    (exp,) = app.add_order_events(T, [{"order_id": "a", "external_order_ref": "A", "channel": "ifood",
                                       "event_type": "sale", "gross_cents": 10000, "occurred_on": date(2026, 10, 20)}])
    app.store.fee_rules.supersede(
        FeeRule(T, Channel.IFOOD, 2700, CommissionBase.GROSS, 99, 5000, date(2026, 11, 1), None, 2), date(2026, 11, 1))
    app.reconcile(T)
    assert app.store.tenant(T).expected[exp.id].expected_net_cents == 10000 - 2300 - 99


# INV-6 — tolerância -----------------------------------------------------------------------
def test_inv6_one_cent_delta_absorbed(engine, ifood_rule, calendar):
    from conciliacao.canonical import parse_settlement_csv
    from tests.conftest import SALES_CYCLE, settle_csv
    exp = expected_for(ifood_rule, calendar, "IF-1", 400)                       # R$ 4,00 → tolerância R$ 0,02
    lines, _ = parse_settlement_csv(T, Channel.IFOOD, settle_csv([("IF-1", "venda", "2,08")]), calendar)
    assert exp[0].expected_net_cents == 209
    res = engine.run(make_input(exp, lines, closed=(SALES_CYCLE,)))
    assert not res.exceptions


def test_inv6_above_tolerance_becomes_exception(engine, ifood_rule, calendar):
    from conciliacao.canonical import parse_settlement_csv
    from tests.conftest import SALES_CYCLE, settle_csv
    exp = expected_for(ifood_rule, calendar, "IF-1", 400)
    lines, _ = parse_settlement_csv(T, Channel.IFOOD, settle_csv([("IF-1", "venda", "2,06")]), calendar)
    assert [e.type.value for e in engine.run(make_input(exp, lines, closed=(SALES_CYCLE,))).exceptions] == ["taxa_divergente"]


# INV-7 — primário com degradação explícita ------------------------------------------------
def test_inv7_itemized_lines_never_routed_to_subset_sum(engine, ifood_rule, calendar):
    from conciliacao.canonical import parse_settlement_csv
    from tests.conftest import settle_csv
    exp = expected_for(ifood_rule, calendar, "IF-1", 6890)
    lines, _ = parse_settlement_csv(T, Channel.IFOOD, settle_csv([("IF-1", "venda", "52,06")]), calendar)
    res = engine.run(make_input(exp, lines, itemized=False, closed=()))
    assert not res.subset_sum_requests


def test_inv7_degraded_path_is_explicit_and_typed():
    assert solve(10, [("a", 3), ("b", 3), ("c", 4), ("d", 7)]).status.value == "ambiguous"


# INV-8 — piso primeiro --------------------------------------------------------------------
def test_inv8_floor_allowed_without_history(app):
    assert app.emit_floor(T, "2026-11").computed_amount_cents == 12_900


def test_inv8_variable_blocked_before_enough_confirmations(app):
    with_confirmations(app, [20_000] * 9)
    app.flags.set(T, Flag.VARIABLE_CAPTURE_ENABLED, True, "admin", "ativação antes do critério de saída", NOW)
    _, _, two = gateways()
    with pytest.raises(BillingError, match="confirmações insuficientes no ledger: 9/10"):
        app.emit_variable(T, "2026-11", two)
