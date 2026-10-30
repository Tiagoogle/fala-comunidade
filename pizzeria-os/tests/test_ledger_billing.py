from dataclasses import replace
from datetime import date, datetime, timedelta, timezone

import pytest

from conciliacao.billing import BillingError, BillingService, PricingPlan, compute_variable
from conciliacao.canonical import source_hash
from conciliacao.gates import Branch, DecisionGateBlocked, Gate
from conciliacao.ledger import ConfirmationMethod, LedgerError, LedgerState, RecoveryLedger
from conciliacao.models import (
    AttributionContract, Channel, EventType, ExceptionType, ReconciliationException, SettlementLine,
)
from tests.conftest import T

t0 = datetime(2026, 10, 27, 12, tzinfo=timezone.utc)


def exc(amount=398, ref="IF-1"):
    return ReconciliationException(T, ExceptionType.TAXA_DIVERGENTE, amount, ref, "ifood:2026-10-19", "promo")


def adjustment(ref="IF-1", amount=398, cycle="ifood:2026-10-26"):
    return SettlementLine(T, Channel.IFOOD, ref, cycle, amount, EventType.ADJUSTMENT, date(2026, 11, 2),
                          source_hash(ref, amount, cycle))


def test_chain_and_tamper_detection(gates):
    led = RecoveryLedger(T, gates)
    e = exc()
    led.detect(e, t0)
    led.dispute(e.id, "ops", t0 + timedelta(hours=1), "IFOOD-PROT-123")
    led.confirm_manual(e.id, 398, "lojista@pizzaria", t0 + timedelta(days=8), "extrato 02/11")
    assert led.verify() == (True, None)
    led._entries[1] = replace(led._entries[1], amount_cents=1)  # adulteração
    ok, err = led.verify()
    assert not ok and "adulterada" in err


def test_cannot_confirm_without_dispute(gates):
    led = RecoveryLedger(T, gates)
    e = exc()
    led.detect(e, t0)
    with pytest.raises(LedgerError, match="transição inválida"):
        led.confirm_manual(e.id, 398, "x", t0, "y")


def test_confirmed_cannot_exceed_detected(gates):
    led = RecoveryLedger(T, gates)
    e = exc()
    led.detect(e, t0)
    led.dispute(e.id, "ops", t0, "P")
    with pytest.raises(LedgerError, match="crescer"):
        led.confirm_manual(e.id, 999, "x", t0, "y")


def test_auto_confirm_blocked_until_gate1_resolved(gates):
    led = RecoveryLedger(T, gates)
    e = exc()
    led.detect(e, t0)
    led.dispute(e.id, "ops", t0, "P")
    with pytest.raises(DecisionGateBlocked):
        led.confirm_auto(e.id, adjustment(), e.cycle_id, t0)
    gates.resolve(Gate.IFOOD_TRACEABLE_ADJUSTMENT, Branch.SIMPLIFIES, "relatório financeiro iFood out/2026, linha AJUSTE com id_pedido", date(2026, 11, 1))
    with pytest.raises(LedgerError, match="ciclo posterior"):
        led.confirm_auto(e.id, adjustment(cycle="ifood:2026-10-19"), e.cycle_id, t0)
    entry = led.confirm_auto(e.id, adjustment(amount=300), e.cycle_id, t0)
    assert entry.confirmation_method is ConfirmationMethod.AUTO and entry.amount_cents == 300


def test_auto_confirm_refused_in_expensive_branch(gates):
    gates.resolve(Gate.IFOOD_TRACEABLE_ADJUSTMENT, Branch.EXPENSIVE, "relatório só traz ajuste agregado por ciclo", date(2026, 11, 1))
    led = RecoveryLedger(T, gates)
    e = exc()
    led.detect(e, t0)
    led.dispute(e.id, "ops", t0, "P")
    with pytest.raises(DecisionGateBlocked):
        led.confirm_auto(e.id, adjustment(), e.cycle_id, t0)


def test_gate_resolution_requires_evidence(gates):
    with pytest.raises(ValueError):
        gates.resolve(Gate.SETTLEMENT_ITEMIZED, Branch.SIMPLIFIES, "sim", date(2026, 11, 1))


@pytest.mark.parametrize("base,expected,capped", [
    (0, 0, False),
    (40_000, 10_000, False),                       # 25% de R$ 400
    (50_000, 12_500, False),                       # topo da 1ª faixa
    (100_000, 12_500 + 7_500, False),              # + 15% de R$ 500
    (300_000, 12_500 + 22_500 + 8_000, False),     # + 8% de R$ 1.000 = R$ 430
    (1_000_000, 45_000, True),                     # teto R$ 450
])
def test_marginal_tiers_and_cap(base, expected, capped):
    amount, cap, _ = compute_variable(base, PricingPlan())
    assert (amount, cap) == (expected, capped)


def test_marginal_tiers_are_monotonic():
    plan = PricingPlan()
    prev_net = -1
    for base in range(0, 400_000, 1_000):
        net = base - compute_variable(base, plan)[0]
        assert net >= prev_net  # recuperar mais nunca deixa o lojista com menos
        prev_net = net


class FakeGateway:
    def __init__(self):
        self.calls = []

    def charge_subscription(self, tenant_id, amount_cents, period_id):
        self.calls.append(("sub", amount_cents))
        return "sub-1"

    def charge_variable(self, tenant_id, amount_cents, period_id):
        self.calls.append(("var", amount_cents))
        return "var-1"


def _confirmed_ledger(gates, amounts):
    led = RecoveryLedger(T, gates)
    for a in amounts:
        e = exc(a)
        led.detect(e, t0)
        led.dispute(e.id, "ops", t0, "P")
        led.confirm_manual(e.id, a, "lojista", t0, "extrato")
    d = exc(10_000)  # só detectado — nunca entra na base
    led.detect(d, t0)
    return led


def test_preview_uses_only_confirmed(gates):
    led = _confirmed_ledger(gates, [20_000, 40_000])
    charge = BillingService(gates).preview_variable(led, "2026-10")
    assert charge.base_amount_cents == 60_000
    assert charge.computed_amount_cents == 12_500 + 1_500


def test_floor_is_unblocked(gates):
    gw = FakeGateway()
    c = BillingService(gates).floor_charge(T, "2026-10", gw)
    assert c.computed_amount_cents == 12_900 and gw.calls == [("sub", 12_900)]


def test_variable_emission_gated(gates):
    led = _confirmed_ledger(gates, [20_000])
    contract = AttributionContract(T, t0, "v1", "valor creditado após disputa aberta pelo módulo", "dono")
    svc = BillingService(gates, PricingPlan(variable_arm_enabled=True))
    with pytest.raises(DecisionGateBlocked):
        svc.emit_variable(led, "2026-10", contract, 6, FakeGateway(), t0)
    gates.resolve(Gate.GATEWAY_VARIABLE_AMOUNT, Branch.EXPENSIVE, "sandbox MP: preapproval rejeita valor variável (teste #42)", date(2026, 11, 3))
    with pytest.raises(BillingError, match="attribution_contract"):
        svc.emit_variable(led, "2026-10", None, 6, FakeGateway(), t0)
    with pytest.raises(BillingError, match="histórico insuficiente"):
        svc.emit_variable(led, "2026-10", contract, 1, FakeGateway(), t0)
    gw = FakeGateway()
    charge = svc.emit_variable(led, "2026-10", contract, 6, gw, t0)
    assert gw.calls == [("var", 5_000)]
    assert all(led.current(e.exception_id).state is LedgerState.BILLED
               for e in led.entries if e.state is LedgerState.CONFIRMED)
    assert led.verify()[0]
    # idempotência: nada confirmado-não-faturado sobra
    assert svc.preview_variable(led, "2026-10").base_amount_cents == 0
    assert charge.status.value == "submitted"
