from conciliacao.canonical import normalize_ref, parse_bank_csv, parse_bank_ofx, parse_settlement_csv
from conciliacao.engine import RunResult
from conciliacao.models import Channel
from tests.conftest import T, expected_for, make_input, settle_csv


def test_ct_0_1_canonicalization_preserves_expected_sum(engine, ifood_rule, calendar):
    exp = []
    for i, (g, p) in enumerate([(6890, 796), (5000, 0), (12345, 1000)]):
        exp += expected_for(ifood_rule, calendar, f"R{i}", g, p)
    p0 = engine.run_pass0(make_input(exp + exp[:1]), RunResult())  # inclui duplicata
    assert sum(e.expected_net_cents for e in p0.expected) == sum(e.expected_net_cents for e in exp)


def test_ct_0_2_bank_dedup_on_reimport():
    csv = "data;valor;descricao\n27/10/2026;1.234,56;TED IFOOD\n28/10/2026;-50,00;TARIFA\n"
    seen = set()
    a, _ = parse_bank_csv(T, csv, seen)
    b, rep = parse_bank_csv(T, csv, seen)
    assert len(a) == 2 and b == [] and rep.duplicates == 2


def test_ct_0_2_ofx_dedup_by_fitid():
    ofx = ("<OFX><STMTTRN><TRNTYPE>CREDIT<DTPOSTED>20261027<TRNAMT>1234.56<FITID>abc1<MEMO>IFOOD REPASSE</STMTTRN>"
           "<STMTTRN><TRNTYPE>DEBIT<DTPOSTED>20261028<TRNAMT>-5.00<FITID>abc2<MEMO>TARIFA</STMTTRN></OFX>")
    seen = set()
    a, _ = parse_bank_ofx(T, ofx, seen)
    b, rep = parse_bank_ofx(T, ofx, seen)
    assert [x.amount_cents for x in a] == [123456, -500] and rep.duplicates == 2 and not b


def test_ct_0_3_tolerance(engine):
    assert engine.tolerance_for(400) == 2       # R$ 4,00 → R$ 0,02
    assert engine.tolerance_for(10000) == 50    # R$ 100,00 → R$ 0,50


def test_ref_canonicalization_spec():
    assert normalize_ref("#if-000123-IFOOD") == "123"
    assert normalize_ref("00042") == "42"
    assert normalize_ref(" ifood 9988 ") == "9988"


def test_settlement_dedup(calendar):
    text = settle_csv([("IF-1", "venda", "10,00")])
    seen = set()
    a, _ = parse_settlement_csv(T, Channel.IFOOD, text, calendar, seen_hashes=seen)
    b, rep = parse_settlement_csv(T, Channel.IFOOD, text, calendar, seen_hashes=seen)
    assert len(a) == 1 and not b and rep.duplicates == 1


def test_parse_errors_are_reported_not_raised(calendar):
    text = "pedido;tipo;valor_liquido;data_repasse\nIF-1;venda;abc;26/10/2026\nIF-2;xpto;1,00;26/10/2026\n"
    lines, rep = parse_settlement_csv(T, Channel.IFOOD, text, calendar)
    assert not lines and len(rep.errors) == 2
