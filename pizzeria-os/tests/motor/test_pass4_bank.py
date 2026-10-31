from conciliacao.canonical import parse_bank_csv, parse_settlement_csv
from conciliacao.models import Channel, ExceptionStatus, ExceptionType, MatchMethod, MatchStatus
from tests.conftest import PAYOUT_CYCLE, T, expected_for, make_input, settle_csv


def scenario(ifood_rule, calendar, deposit: str | None):
    exp = expected_for(ifood_rule, calendar, "A1", 5000) + expected_for(ifood_rule, calendar, "A2", 10000)
    lines, _ = parse_settlement_csv(T, Channel.IFOOD, settle_csv([("A1", "venda", "37,51"), ("A2", "venda", "76,01")]), calendar)
    bank_csv = "data;valor;descricao\n" + (f"28/10/2026;{deposit};TED IFOOD.COM AGENCIA\n" if deposit else "") \
               + "28/10/2026;3.000,00;PIX CLIENTE BALCAO\n"
    bank, _ = parse_bank_csv(T, bank_csv)
    return make_input(exp, lines, bank)


def bank_excs(res):
    return [e for e in res.exceptions if e.type in (ExceptionType.ANTECIPACAO, ExceptionType.DIFERENCA_CAIXA)]


def test_ct_4_1_sum_equals_deposit_closes_cycle(engine, ifood_rule, calendar):
    res = engine.run(scenario(ifood_rule, calendar, "113,52"))
    assert not bank_excs(res)
    (bm,) = [m for m in res.matches if m.match_method is MatchMethod.BANK]
    assert bm.status is MatchStatus.MATCHED and bm.bank_txn_id
    assert all(m.bank_txn_id == bm.bank_txn_id for m in res.matches)  # matches de pedido ligados ao depósito (N1-N2-N3)


def test_ct_4_2_deposit_greater_is_antecipacao(engine, ifood_rule, calendar):
    res = engine.run(scenario(ifood_rule, calendar, "150,00"))
    (e,) = bank_excs(res)
    assert e.type is ExceptionType.ANTECIPACAO and e.amount_cents == 15000 - 11352
    assert e.status is ExceptionStatus.HUMAN_QUEUE and e.cycle_id == PAYOUT_CYCLE


def test_ct_4_3_deposit_smaller_is_diferenca_caixa(engine, ifood_rule, calendar):
    res = engine.run(scenario(ifood_rule, calendar, "100,00"))
    (e,) = bank_excs(res)
    assert e.type is ExceptionType.DIFERENCA_CAIXA and e.amount_cents == 1352 and e.status is ExceptionStatus.OPEN


def test_missing_deposit_after_close(engine, ifood_rule, calendar):
    (e,) = bank_excs(engine.run(scenario(ifood_rule, calendar, None)))
    assert e.type is ExceptionType.DIFERENCA_CAIXA and "nenhum depósito" in e.probable_cause


def test_pass4_waits_for_open_payout_cycle(engine, ifood_rule, calendar):
    inp = scenario(ifood_rule, calendar, None)
    inp.closed_cycles = {"ifood:2026-10-19"}
    assert not bank_excs(engine.run(inp))


def test_bank_tolerance_two_cents(engine, ifood_rule, calendar):
    assert not bank_excs(engine.run(scenario(ifood_rule, calendar, "113,54")))
