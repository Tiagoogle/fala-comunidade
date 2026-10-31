from dataclasses import replace
from datetime import date, timedelta

import pytest

from conciliacao.canonical import source_hash
from conciliacao.flags import Flag
from conciliacao.ledger import ConfirmationMethod, ConfirmationModeError, LedgerError, LedgerState, RecoveryLedgerService
from conciliacao.models import Channel, EventType, ExceptionType, ReconciliationException, SettlementLine
from tests.conftest import NOW, T


def exc(amount=398, ref="1"):
    return ReconciliationException(T, ExceptionType.TAXA_DIVERGENTE, amount, ref, "ifood:2026-10-19", "promo")


def adjustment(ref="1", amount=398, cycle="ifood:2026-10-26"):
    return SettlementLine(T, Channel.IFOOD, ref, cycle, amount, EventType.ADJUSTMENT, date(2026, 11, 2),
                          source_hash(ref, amount, cycle))


def test_ct_l_1_append_entry_chains_prev_hash(flags):
    led = RecoveryLedgerService(T, flags)
    a, b = exc(), exc(500, "2")
    e0 = led.detect(a, NOW)
    e1 = led.detect(b, NOW)
    e2 = led.dispute(a.id, "ops", NOW, "P-1")
    assert e0.prev_entry_hash is None and e0.seq == 0
    assert e1.prev_entry_hash == e0.entry_hash and e2.prev_entry_hash == e1.entry_hash


def test_ct_l_2_verify_chain_true_then_false_after_tamper(flags):
    led = RecoveryLedgerService(T, flags)
    e = exc()
    led.detect(e, NOW)
    led.dispute(e.id, "ops", NOW, "P")
    led.confirm_manual(e.id, 398, "lojista", NOW + timedelta(days=8), "extrato 02/11")
    assert led.verify_chain() and led.verify_chain(e.id)
    led._entries[1] = replace(led._entries[1], amount_cents=1)
    assert not led.verify_chain() and not led.verify_chain(e.id)


def test_deleting_whole_recovery_is_detected(flags):
    led = RecoveryLedgerService(T, flags)
    a, b = exc(), exc(500, "2")
    led.detect(a, NOW)
    led.detect(b, NOW)
    del led._entries[0]  # some a recuperação "a" inteira
    assert not led.verify_chain()


def test_ct_l_5_invalid_transition_rejected(flags):
    led = RecoveryLedgerService(T, flags)
    e = exc()
    led.detect(e, NOW)
    with pytest.raises(LedgerError, match="transição inválida"):
        led.transition(e.id, LedgerState.BILLED, actor="x", at=NOW)
    with pytest.raises(LedgerError, match="transição inválida"):
        led.confirm_manual(e.id, 398, "x", NOW, "y")


def test_amount_never_grows(flags):
    led = RecoveryLedgerService(T, flags)
    e = exc()
    led.detect(e, NOW)
    led.dispute(e.id, "ops", NOW, "P")
    with pytest.raises(LedgerError, match="crescer"):
        led.confirm_manual(e.id, 999, "x", NOW, "y")


def test_no_update_or_delete_api():
    assert not [m for m in dir(RecoveryLedgerService) if m.startswith(("update", "delete", "remove", "edit"))]


def test_confirmation_branch_follows_flag(flags):
    led = RecoveryLedgerService(T, flags)
    e = exc()
    led.detect(e, NOW)
    led.dispute(e.id, "ops", NOW, "P")
    with pytest.raises(ConfirmationModeError):
        led.confirm_auto(e.id, adjustment(), e.cycle_id, NOW)       # flag default false
    flags.set(T, Flag.CONFIRMATION_METHOD_AUTO, True, "admin", "sandbox iFood: relatório com linha AJUSTE+pedido", NOW)
    with pytest.raises(ConfirmationModeError):
        led.confirm_manual(e.id, 398, "x", NOW, "y")                 # manual desabilitado no ramo auto
    with pytest.raises(LedgerError, match="ciclo posterior"):
        led.confirm_auto(e.id, adjustment(cycle="ifood:2026-10-19"), e.cycle_id, NOW)
    with pytest.raises(LedgerError, match="não referencia"):
        led.confirm_auto(e.id, adjustment(ref="999"), e.cycle_id, NOW)
    entry = led.confirm_auto(e.id, adjustment(amount=300), e.cycle_id, NOW)
    assert entry.confirmation_method is ConfirmationMethod.AUTO and entry.amount_cents == 300


def test_reject_is_terminal(flags):
    led = RecoveryLedgerService(T, flags)
    e = exc()
    led.detect(e, NOW)
    led.dispute(e.id, "ops", NOW, "P")
    led.reject(e.id, "ops", NOW, "plataforma negou")
    with pytest.raises(LedgerError):
        led.confirm_manual(e.id, 1, "x", NOW, "y")


def test_detect_rejects_other_tenant_and_non_positive(flags):
    led = RecoveryLedgerService(T, flags)
    with pytest.raises(PermissionError):
        led.detect(ReconciliationException("outro", ExceptionType.TAXA_DIVERGENTE, 1, "1", None, "x"), NOW)
    with pytest.raises(LedgerError):
        led.detect(exc(amount=-5), NOW)
