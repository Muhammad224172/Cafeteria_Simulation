import numpy as np
import pytest

from cafesim.config import clock_to_seconds, with_overrides
from cafesim.experiment import run_replication
from cafesim.model import Cafeteria
from cafesim.streams import Streams

CLOSE_D = {"closures": [{"line": "D", "start": "14:00", "end": "18:00"}]}
EXTRA_CASHIERS = {"extra_cashiers": [{"line": "C", "start": "11:30", "end": "14:00"}]}


def _model(cfg, seed=1, rep=0):
    m = Cafeteria(cfg, Streams(seed, rep))
    m.run()
    return m


@pytest.fixture(scope="module")
def base_run(base_cfg):
    return _model(base_cfg)


def test_customer_conservation(base_run):
    m = base_run
    assert m.n_arrived > 2500
    assert m.n_left == m.n_arrived
    assert m.in_system.value == 0 and m.in_lines.value == 0
    assert m.time_to_pay.n == m.n_arrived
    assert len(m.dining.queue) == 0
    assert all(occ == 0 for occ in m.dining.occupancy)
    assert m.n_arrived == sum(m.group_sizes)


@pytest.mark.parametrize("lines", [CLOSE_D, EXTRA_CASHIERS])
def test_customer_conservation_with_line_changes(base_cfg, lines):
    m = _model(with_overrides(base_cfg, lines=lines))
    assert m.n_left == m.n_arrived and m.time_to_pay.n == m.n_arrived


def test_closing_time_rule(base_run):
    m = base_run
    assert m.t_close >= clock_to_seconds("20:00")
    assert m.t_empty > m.t_close
    # measure 1 is a tally over all customers and every customer finished paying before t_close
    assert max(a + d for a, d in m.pay_records) <= m.t_close + 1e-9


def test_same_seed_reproducible(base_cfg):
    a = run_replication(base_cfg, replication=3, seed=99)
    b = run_replication(base_cfg, replication=3, seed=99)
    for key in ("measure1_s", "measure2", "n_customers", "t_empty_s", "stockout_waits"):
        assert a[key] == b[key]
    c = run_replication(base_cfg, replication=4, seed=99)
    assert c["measure1_s"] != a["measure1_s"]


def test_crn_identical_arrival_streams_across_configurations(base_cfg):
    alt = with_overrides(
        base_cfg,
        lines={**CLOSE_D, **EXTRA_CASHIERS},
        workers={"dispatch": "prefer_experienced"},
    )
    m1, m2 = _model(base_cfg, seed=5, rep=2), _model(alt, seed=5, rep=2)
    assert m1.arrival_times == m2.arrival_times
    assert m1.group_sizes == m2.group_sizes
    # per-customer attributes are drawn from attribute streams in arrival order, so they match too
    r1 = sorted(m1.pay_records)
    r2 = sorted(m2.pay_records)
    assert [a for a, _ in r1] == [a for a, _ in r2]


def test_crn_customer_attributes_match(base_cfg):
    alt = with_overrides(base_cfg, workers={"dispatch": "random"}, lines=CLOSE_D)
    seen = []
    for cfg in (base_cfg, alt):
        m = Cafeteria(cfg, Streams(3, 0))
        customers = []
        original = m._make_customer

        def spy(cid, group, meal, _orig=original, _store=customers):
            c = _orig(cid, group, meal)
            _store.append((meal, c.wants, c.pay_time, c.eat_time, c.sauce))
            return c

        m._make_customer = spy
        m.run()
        seen.append(customers)
    assert seen[0] == seen[1]


def test_routing_shares(base_run):
    m = base_run
    counts = {x: m.time_to_pay_by_line[x].n for x in "ABCD"}
    total = sum(counts.values())
    assert abs(counts["A"] / total - 0.10) < 0.03
    assert abs(counts["C"] / total - 0.30) < 0.04
    assert abs((counts["B"] + counts["D"]) / total - 0.60) < 0.04


def test_closed_line_gets_no_new_customers(base_cfg):
    cfg = with_overrides(base_cfg, lines=CLOSE_D)
    m = Cafeteria(cfg, Streams(1, 0))
    arrivals_by_line = {"B": [], "D": []}
    original = m.customer_process

    def spy(c, _orig=original):
        if c.line in arrivals_by_line:
            arrivals_by_line[c.line].append(c.arrival)
        return _orig(c)

    m.customer_process = spy
    m.run()
    d = np.asarray(arrivals_by_line["D"])
    assert not np.any((d >= clock_to_seconds("14:00")) & (d < clock_to_seconds("18:00")))
    assert len(d) > 0


def test_second_till_closed_unless_scheduled(base_cfg):
    m = Cafeteria(with_overrides(base_cfg, lines=EXTRA_CASHIERS), Streams(1, 0))
    m.run()
    # after the day, the placeholder holds the second till of every line
    assert all(line.cashier.count == 1 for line in m.lines.values())


def test_group_eating_rule(base_cfg):
    last = run_replication(base_cfg, 0, seed=8)
    first = run_replication(with_overrides(base_cfg, dining={"group_eating": "first_member"}), 0, seed=8)
    assert first["sojourn_mean_s"] < last["sojourn_mean_s"]
    assert first["measure1_s"] == last["measure1_s"]  # dining does not feed back on the lines
