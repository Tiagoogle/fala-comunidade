import json
from datetime import timedelta

import pytest

from conciliacao.billing import BillingError, PricingPlan, Tier, compute_variable
from conciliacao.flags import Flag
from conciliacao.gateways.mercadopago import (
    MercadoPagoClient, SingleMandateGateway, TenantBillingAccount, TwoInstrumentGateway, cents_to_amount_literal,
    encode_json,
)
from conciliacao.models import ChargeType, ExceptionType, ReconciliationException
from conciliacao.service import ConciliacaoApp
from tests.conftest import NOW, T, Clock, onboard


class FakeTransport:
    def __init__(self):
        self.calls = []

    def request(self, method, url, headers, body):
        self.calls.append((method, url, body))
        return {"id": f"mp-{len(self.calls)}"}


def gateways():
    tr = FakeTransport()
    client = MercadoPagoClient("tok", tr)
    acc = {T: TenantBillingAccount("dono@pizzaria.test", customer_id="cus-1", card_token="card-1")}
    return tr, SingleMandateGateway(client, acc), TwoInstrumentGateway(client, {T: TenantBillingAccount(**vars(acc[T]))})


def with_confirmations(app: ConciliacaoApp, amounts, cycles=3):
    td = app.store.tenant(T)
    for i, a in enumerate(amounts):
        e = ReconciliationException(T, ExceptionType.TAXA_DIVERGENTE, a, f"R{i}", "ifood:2026-10-19", "x")
        td.exceptions[e.id] = e
        td.ledger.detect(e, NOW)
        td.ledger.dispute(e.id, "ops", NOW, "P")
        td.ledger.confirm_manual(e.id, a, "dono", NOW, "extrato")
    d = ReconciliationException(T, ExceptionType.TAXA_DIVERGENTE, 99_999, "DET", "ifood:2026-10-19", "só detectado")
    td.exceptions[d.id] = d
    td.ledger.detect(d, NOW)
    td.reconciled_cycles |= {f"ifood:c{i}" for i in range(cycles)}


def test_ct_b_1_floor_monthly_for_active_tenant(app):
    tr, single, two = gateways()
    c = app.emit_floor(T, "2026-11", app.billing.gateway_for(T, single, two))
    assert c.charge_type is ChargeType.PISO and c.computed_amount_cents == 12_900 and c.instrument == "subscription"
    assert '"transaction_amount": 129.00' in tr.calls[0][2]
    with pytest.raises(ValueError):
        app.emit_floor(T, "2026-11")


def test_ct_b_2_variable_only_with_confirmed_entries(app):
    app.flags.set(T, Flag.VARIABLE_CAPTURE_ENABLED, True, "admin", "fase 1 concluída, 5 tenants ativos", NOW)
    app.plan = PricingPlan(min_confirmed_entries=0)
    app.billing.plan = app.plan
    app.store.tenant(T).reconciled_cycles |= {"a", "b", "c"}
    _, single, two = gateways()
    assert app.emit_variable(T, "2026-11", two) is None


def test_ct_b_3_cap_applied():
    amount, capped, _ = compute_variable(1_000_000, PricingPlan())
    assert capped and amount == 45_000


@pytest.mark.parametrize("base,expected", [
    (0, 0), (40_000, 10_000), (50_000, 12_500), (100_000, 20_000), (200_000, 35_000), (300_000, 43_000),
])
def test_ct_b_4_marginal_decreasing_tiers(base, expected):
    assert compute_variable(base, PricingPlan())[0] == expected


def test_tiers_monotonic_net_for_merchant():
    plan, prev = PricingPlan(), -1
    for base in range(0, 400_000, 500):
        net = base - compute_variable(base, plan)[0]
        assert net >= prev
        prev = net


def test_plan_rejects_increasing_rates():
    with pytest.raises(BillingError):
        PricingPlan(tiers=(Tier(50_000, 800), Tier(None, 2500)))


def test_variable_two_instruments_branch(app):
    with_confirmations(app, [20_000] * 10)
    app.flags.set(T, Flag.VARIABLE_CAPTURE_ENABLED, True, "admin", "fase 1 concluída, critérios de saída ok", NOW)
    tr, single, two = gateways()
    c = app.emit_variable(T, "2026-11", app.billing.gateway_for(T, single, two))
    assert c.base_amount_cents == 200_000 and c.computed_amount_cents == 35_000 and c.instrument == "one_off"
    method, url, body = tr.calls[-1]
    assert url.endswith("/v1/payments") and '"transaction_amount": 350.00' in body
    assert app.store.tenant(T).ledger.verify_chain()
    assert app.billing.preview_variable(app.store.tenant(T).ledger, "2026-12").base_amount_cents == 0


def test_variable_single_mandate_branch(app):
    with_confirmations(app, [20_000] * 10)
    for f in (Flag.VARIABLE_CAPTURE_ENABLED, Flag.BILLING_SINGLE_MANDATE):
        app.flags.set(T, f, True, "admin", "sandbox MP: PUT /preapproval altera valor (teste #42)", NOW)
    tr, single, two = gateways()
    gw = app.billing.gateway_for(T, single, two)
    app.emit_floor(T, "2026-11", gw)
    c = app.emit_variable(T, "2026-11", gw)
    assert c.instrument == "single_mandate" and tr.calls[-1][0] == "PUT"
    assert '"transaction_amount": 479.00' in tr.calls[-1][2]                  # piso 129 + captura 350


def test_variable_blockers(app):
    with_confirmations(app, [20_000] * 3, cycles=1)
    _, single, two = gateways()
    with pytest.raises(BillingError, match="variable_capture_enabled"):
        app.emit_variable(T, "2026-11", two)
    app.flags.set(T, Flag.VARIABLE_CAPTURE_ENABLED, True, "admin", "ativação prematura de teste", NOW)
    with pytest.raises(BillingError, match="histórico insuficiente.*confirmações insuficientes"):
        app.emit_variable(T, "2026-11", two)


def test_money_never_float_at_gateway():
    assert cents_to_amount_literal(12_905) == "129.05"
    with pytest.raises(TypeError):
        cents_to_amount_literal(129.05)
    with pytest.raises(TypeError):
        encode_json({"x": 1.5})
    assert json.loads(encode_json({"a": {"b": [1]}})) == {"a": {"b": [1]}}


def test_floor_requires_active_tenant():
    a = ConciliacaoApp(clock=Clock())
    onboard(a, calibrate=False)
    with pytest.raises(BillingError, match="modo ativo"):
        a.emit_floor(T, "2026-11")
