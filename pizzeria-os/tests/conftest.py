from datetime import date, datetime, timezone

import pytest

from conciliacao.engine import EngineInput, ReconciliationEngine
from conciliacao.fees import CycleCalendar, compute_expected
from conciliacao.flags import Flag, FlagService
from conciliacao.models import Channel, CommissionBase, EventType, FeeRule, OrderEvent
from conciliacao.service import ConciliacaoApp

T = "pizzaria-centro"
CNPJ = "11.222.333/0001-81"   # CNPJ sintético com dígitos verificadores válidos
D = date(2026, 10, 20)
SALES_CYCLE = "ifood:2026-10-19"
PAYOUT_CYCLE = "ifood:2026-10-26"
NOW = datetime(2026, 11, 3, 12, tzinfo=timezone.utc)


@pytest.fixture
def calendar():
    return CycleCalendar(length_days=7, anchor=date(2026, 1, 5))


@pytest.fixture
def engine(calendar):
    return ReconciliationEngine(calendar)


@pytest.fixture
def ifood_rule():
    # Prompt Mestre §6.3: 23% sobre o bruto + R$ 0,99, promoção cofinanciada meio a meio
    return FeeRule(T, Channel.IFOOD, 2300, CommissionBase.GROSS, 99, 5000, date(2026, 1, 1), None, 1)


@pytest.fixture
def flags():
    f = FlagService()
    f.init_tenant(T)
    return f


def expected_for(rule, calendar, ref, gross, promo=0, et=EventType.SALE, on=D):
    return compute_expected(OrderEvent(T, f"o-{ref}", ref, Channel.IFOOD, et, gross, on, promo), rule, calendar)


def settle_csv(rows, date_str="26/10/2026"):
    return "pedido;tipo;valor_liquido;data_repasse\n" + "\n".join(
        f"{r};{t};{v};{date_str}" for r, t, v in rows) + "\n"


def make_input(expected=(), settlements=(), bank=(), closed=(SALES_CYCLE, PAYOUT_CYCLE), itemized=True, **kw):
    return EngineInput(T, list(expected), list(settlements), list(bank), set(closed), itemized, **kw)


class Clock:
    def __init__(self, now=NOW):
        self.now = now

    def __call__(self):
        return self.now


def onboard(app: ConciliacaoApp, tenant=T, cnpj=CNPJ, calibrate=True):
    app.register_tenant(tenant, "Pizzaria Centro", cnpj, "Rua A, 1", "Maria Dona", "maria@pizzaria.test")
    app.configure_fee_contract(tenant, Channel.IFOOD, 2300, CommissionBase.GROSS, 99, 5000, date(2026, 1, 1))
    app.accept_attribution(tenant, "v1", "Considera-se valor recuperado por ação do módulo toda divergência "
                                         "tipada pelo motor e confirmada no ledger.", "Maria Dona", "200.1.1.1")
    app.connect_integrations(tenant, "ifood-token", "mp-token")
    if calibrate:
        app.calibrate(tenant, approve=True, actor="Maria Dona")


@pytest.fixture
def app():
    a = ConciliacaoApp(calendar=CycleCalendar(7, date(2026, 1, 5)), clock=Clock())
    onboard(a)
    return a
