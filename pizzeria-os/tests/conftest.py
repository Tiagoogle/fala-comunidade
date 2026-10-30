from datetime import date

import pytest

from conciliacao.fees import CycleCalendar, FeeRuleBook
from conciliacao.gates import DecisionGates
from conciliacao.models import Channel, CommissionBase, FeeRule

T = "pizzaria-centro"


@pytest.fixture
def calendar():
    return CycleCalendar(length_days=7, anchor=date(2026, 1, 5))


@pytest.fixture
def gates():
    return DecisionGates()


@pytest.fixture
def ifood_rule():
    # PRD §5: comissão de 23% sobre o bruto + taxa fixa de R$ 0,99, promoção cofinanciada meio a meio
    return FeeRule(tenant_id=T, channel=Channel.IFOOD, commission_bps=2300, commission_base=CommissionBase.GROSS,
                   fixed_fee_cents=99, promo_platform_share_bps=5000, valid_from=date(2026, 1, 1),
                   valid_to=None, version=1)


@pytest.fixture
def book(ifood_rule):
    b = FeeRuleBook()
    b.add(ifood_rule)
    return b
