import random

import pytest

from conciliacao.canonical import SettlementColumnMap, parse_settlement_csv
from conciliacao.models import Channel, ExceptionType, MatchMethod
from conciliacao.subset_sum import SolverLimits, SolveStatus, solve
from tests.conftest import T, expected_for, make_input


def test_unique_solution():
    r = solve(1000, [("a", 300), ("b", 700), ("c", 450)])
    assert r.status is SolveStatus.UNIQUE and r.keys == ("a", "b")


def test_ambiguous_by_alternative_subset():
    assert solve(1000, [("a", 300), ("b", 700), ("c", 300), ("d", 400)]).status is SolveStatus.AMBIGUOUS


def test_ambiguous_by_superset_within_tolerance():
    assert solve(1000, [("a", 999), ("b", 1)], tolerance_cents=1).status is SolveStatus.AMBIGUOUS


def test_none_when_fee_divergence_breaks_the_sum():
    assert solve(1000, [("a", 300), ("b", 650)]).status is SolveStatus.NONE


def test_too_large_guard():
    assert solve(10**9, [("a", 5), ("b", 7)], limits=SolverLimits(max_bitset_cells=1000)).status is SolveStatus.TOO_LARGE


def test_rejects_float():
    with pytest.raises(TypeError):
        solve(1000, [("a", 10.5)])


def test_brute_force_agreement():
    rng = random.Random(7)
    for _ in range(200):
        items = [(f"k{i}", rng.randint(1, 40)) for i in range(rng.randint(1, 9))]
        target = rng.randint(1, 120)
        sols = []
        for mask in range(1, 1 << len(items)):
            if sum(a for i, (_, a) in enumerate(items) if mask >> i & 1) == target:
                sols.append(tuple(sorted(k for i, (k, _) in enumerate(items) if mask >> i & 1)))
        r = solve(target, items)
        expected = SolveStatus.NONE if not sols else SolveStatus.UNIQUE if len(sols) == 1 else SolveStatus.AMBIGUOUS
        assert r.status is expected, (items, target, sols, r)
        if expected is SolveStatus.UNIQUE:
            assert r.keys == sols[0]


def test_degraded_path_end_to_end(engine, ifood_rule, calendar):
    exp = (expected_for(ifood_rule, calendar, "A1", 5000) + expected_for(ifood_rule, calendar, "A2", 10000)
           + expected_for(ifood_rule, calendar, "A3", 8000))                   # 37,51 · 76,01 · 60,61
    agg, _ = parse_settlement_csv(T, Channel.IFOOD, "valor_liquido;data_repasse\n113,52;26/10/2026\n", calendar,
                                  SettlementColumnMap(order_ref=None, line_type=None))
    inp = make_input(exp, agg, itemized=False, closed=("ifood:2026-10-19",))
    first = engine.run(inp)
    assert [s.id for s in first.subset_sum_requests] == [agg[0].id]
    assert not first.exceptions                                                 # Passe 2 aguarda o solver

    inp.subset_results[agg[0].id] = solve(agg[0].reported_net_cents, engine.subset_sum_candidates(inp, agg[0]))
    second = engine.run(inp)
    (m,) = [m for m in second.matches if m.match_method is MatchMethod.SUBSET_SUM]
    assert m.order_ref == "A1,A2"
    (miss,) = second.exceptions
    assert miss.type is ExceptionType.VENDA_SEM_REPASSE and miss.order_ref == "A3"


def test_aggregate_with_itemized_flag_goes_to_human_queue(engine, calendar):
    agg, _ = parse_settlement_csv(T, Channel.IFOOD, "valor_liquido;data_repasse\n10,00;26/10/2026\n", calendar,
                                  SettlementColumnMap(order_ref=None, line_type=None))
    res = engine.run(make_input([], agg, itemized=True, closed=()))
    assert not res.subset_sum_requests and res.warnings
    assert [e.type for e in res.exceptions] == [ExceptionType.REPASSE_SEM_VENDA]


def test_itemized_lines_use_primary_path_even_with_flag_false(engine, ifood_rule, calendar):
    from tests.conftest import settle_csv
    exp = expected_for(ifood_rule, calendar, "IF-1", 6890)
    lines, _ = parse_settlement_csv(T, Channel.IFOOD, settle_csv([("IF-1", "venda", "52,06")]), calendar)
    res = engine.run(make_input(exp, lines, itemized=False, closed=()))
    assert res.matches[0].match_method is MatchMethod.KEY_EVENT and not res.subset_sum_requests
