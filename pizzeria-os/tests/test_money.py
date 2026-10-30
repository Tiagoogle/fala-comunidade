import pytest

from conciliacao.money import apply_bps, fmt_brl, parse_brl, tolerance_cents


def test_apply_bps_half_up_symmetric():
    assert apply_bps(6890, 2300) == 1585          # 1584,7 → 1585
    assert apply_bps(-6890, 2300) == -1585
    assert apply_bps(1, 5000) == 1                 # 0,5 → 1
    with pytest.raises(TypeError):
        apply_bps(68.9, 2300)


@pytest.mark.parametrize("raw,cents", [
    ("1.234,56", 123456), ("1234.56", 123456), ("R$ -12,30", -1230), ("(12,30)", -1230),
    ("44,10", 4410), ("1,234.56", 123456), ("7", 700),
])
def test_parse_brl(raw, cents):
    assert parse_brl(raw) == cents


def test_parse_brl_rejects_sub_cent():
    with pytest.raises(ValueError):
        parse_brl("1,234")  # ambíguo: 1,234 seria 3 casas decimais


def test_tolerance():
    assert tolerance_cents(100) == 2          # piso de R$ 0,02
    assert tolerance_cents(6890) == 34        # 0,5% de 68,90


def test_fmt():
    assert fmt_brl(123456) == "R$ 1.234,56"
    assert fmt_brl(-5) == "-R$ 0,05"
