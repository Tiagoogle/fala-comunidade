from datetime import date

import pytest

from conciliacao.flags import Flag
from conciliacao.models import Channel, CommissionBase, FeeRule
from conciliacao.onboarding import OnboardingError, Step, valid_cnpj
from conciliacao.service import ConciliacaoApp
from tests.conftest import CNPJ, T, Clock, onboard, settle_csv


def fresh():
    return ConciliacaoApp(clock=Clock())


def test_cnpj_validation():
    assert valid_cnpj(CNPJ) and not valid_cnpj("11.222.333/0001-82") and not valid_cnpj("00000000000000")


def test_step1_creates_tenant_with_flags_false():
    a = fresh()
    a.register_tenant(T, "P", CNPJ, "Rua", "Maria", "m@p.test")
    assert not any(a.flags.get(T).values.values())
    assert a.store.tenant(T).onboarding.next_step is Step.FEE_CONTRACT


def test_steps_are_sequential_and_resumable():
    a = fresh()
    a.register_tenant(T, "P", CNPJ, "Rua", "Maria", "m@p.test")
    with pytest.raises(OnboardingError, match="fora de ordem"):
        a.accept_attribution(T, "v1", "x" * 50, "Maria", "1.1.1.1")
    a.configure_fee_contract(T, Channel.IFOOD, 2300, CommissionBase.GROSS, 99, 5000, date(2026, 1, 1))
    # retomada: o estado persiste e aponta a próxima etapa
    assert a.store.tenant(T).onboarding.next_step is Step.ATTRIBUTION_ACCEPTED


def test_step4_forbidden_without_attribution():
    a = fresh()
    a.register_tenant(T, "P", CNPJ, "Rua", "Maria", "m@p.test")
    a.configure_fee_contract(T, Channel.IFOOD, 2300, CommissionBase.GROSS, 99, 5000, date(2026, 1, 1))
    with pytest.raises(OnboardingError, match="PROIBIDO"):
        a.connect_integrations(T, "a", "b")


def test_tokens_encrypted_at_rest():
    a = fresh()
    onboard(a, calibrate=False)
    row = a.tokens.raw_row(T, "ifood")
    assert b"ifood-token" not in row["access_token_enc"] and a.tokens.get_access_token(T, "ifood") == "ifood-token"


def test_step5_calibration_creates_no_ledger_or_billing_and_activates():
    a = fresh()
    onboard(a, calibrate=False)
    a.add_order_events(T, [{"order_id": "o1", "external_order_ref": "IF-1", "channel": "ifood", "event_type": "sale",
                            "gross_cents": 6890, "promo_discount_cents": 796, "occurred_on": date(2026, 10, 20)}])
    a.ingest_settlement(T, Channel.IFOOD, settle_csv([("IF-1", "venda", "44,10")]))
    with pytest.raises(OnboardingError):
        a.reconcile(T)                                   # ainda em onboarding
    summary = a.calibrate(T, approve=False, actor="Maria")
    assert summary["metrics"]["exceptions_by_type"] == {"taxa_divergente": 1}
    td = a.store.tenant(T)
    assert not td.ledger.entries and not td.exceptions and not td.charges
    assert not td.onboarding.active
    a.calibrate(T, approve=True, actor="Maria")
    assert td.onboarding.active
    a.reconcile(T)
    assert [e.state.value for e in td.ledger.entries] == ["detected"]


def test_fee_contract_change_creates_new_version():
    a = fresh()
    onboard(a)
    v2 = a.store.fee_rules.supersede(
        FeeRule(T, Channel.IFOOD, 2500, CommissionBase.GROSS, 99, 5000, date(2026, 11, 1), None, 2), date(2026, 11, 1))
    v1 = a.store.fee_rules.effective(T, Channel.IFOOD, date(2026, 10, 31))
    assert v1.valid_to == date(2026, 11, 1) and v2.version == 2


def test_flag_change_audited_and_requires_evidence():
    a = fresh()
    onboard(a)
    with pytest.raises(ValueError):
        a.flags.set(T, Flag.SETTLEMENT_ITEMIZED, True, "admin", "ok", a.clock())
    a.flags.set(T, Flag.SETTLEMENT_ITEMIZED, True, "admin", "relatório iFood out/26 tem coluna id_pedido", a.clock())
    (audit,) = a.flags.audit(T)
    assert (audit.old_value, audit.new_value, audit.changed_by) == (False, True, "admin")
