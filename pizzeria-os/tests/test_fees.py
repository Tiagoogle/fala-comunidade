from datetime import date

import pytest

from conciliacao.fees import FeeRuleError, compute_expected
from conciliacao.models import Channel, CommissionBase, EventType, FeeRule, OrderEvent
from tests.conftest import T


def order(**kw):
    base = dict(tenant_id=T, order_id="o1", external_order_ref="IF-1", channel=Channel.IFOOD,
                event_type=EventType.SALE, gross_cents=6890, occurred_on=date(2026, 10, 20))
    base.update(kw)
    return OrderEvent(**base)


def test_prd_example_expectation(ifood_rule, calendar):
    exp = compute_expected(order(promo_discount_cents=796), ifood_rule, calendar)
    sale, promo = exp
    assert sale.event_type is EventType.SALE and sale.expected_net_cents == 6890 - 1585 - 99  # 5206
    assert promo.event_type is EventType.PROMO and promo.expected_net_cents == -398          # metade do lojista
    assert sum(e.expected_net_cents for e in exp) == 4808
    assert sale.cycle_id == "ifood:2026-10-19"


def test_commission_net_of_promo(calendar):
    rule = FeeRule(T, Channel.IFOOD, 2300, CommissionBase.NET_OF_PROMO, 99, 5000, date(2026, 1, 1), None, 1)
    sale = compute_expected(order(promo_discount_cents=1000), rule, calendar)[0]
    assert sale.components["commission_cents"] == 1355  # 23% de 58,90


def test_refund_reverses_commission(ifood_rule, calendar):
    (r,) = compute_expected(order(event_type=EventType.REFUND, gross_cents=2000), ifood_rule, calendar)
    assert r.expected_net_cents == -2000 + 460


def test_versioning_rejects_overlap(book, ifood_rule):
    with pytest.raises(FeeRuleError, match="sobreposta"):
        book.add(FeeRule(T, Channel.IFOOD, 2500, CommissionBase.GROSS, 99, 5000, date(2026, 6, 1), None, 2))


def test_versioning_picks_effective_rule(ifood_rule):
    from conciliacao.fees import FeeRuleBook
    b = FeeRuleBook()
    from dataclasses import replace
    b.add(replace(ifood_rule, valid_to=date(2026, 7, 1)))
    v2 = b.add(FeeRule(T, Channel.IFOOD, 2500, CommissionBase.GROSS, 99, 5000, date(2026, 7, 1), None, 2))
    assert b.effective(T, Channel.IFOOD, date(2026, 6, 30)).version == 1
    assert b.effective(T, Channel.IFOOD, date(2026, 7, 1)) is v2
    with pytest.raises(FeeRuleError):
        b.effective(T, Channel.IFOOD, date(2025, 12, 31))
