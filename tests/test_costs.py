import numpy as np

from cafesim.config import with_overrides
from cafesim.costs import daily_cost, worker_hours


def test_base_worker_hours(base_cfg):
    hours = worker_hours(base_cfg)
    # per area and level: 3 workers for 2.5 h + 2 for 4 h + 3 for 2 h = 21.5 worker-hours
    for area in ("AB", "CD"):
        assert np.isclose(hours[area]["experienced"], 21.5)
        assert np.isclose(hours[area]["inexperienced"], 21.5)


def test_base_daily_cost(base_cfg):
    cost = daily_cost(base_cfg)
    workers = 2 * (21.5 * 1.3 + 21.5 * 1.0)
    cashiers = 4 * 8.5 * 1.3
    assert np.isclose(cost["workers"], workers)
    assert np.isclose(cost["cashiers"], cashiers)
    assert np.isclose(cost["total"], workers + cashiers)
    assert np.isclose(cost["total"], 143.1)


def test_no_pay_after_2000(base_cfg):
    # adding a worker only in the "19:00 and after" slot costs exactly one hour
    sched = base_cfg["workers"]["schedule"]
    ab = {"experienced": sched["AB"]["experienced"], "inexperienced": sched["AB"]["inexperienced"][:-1] + [4]}
    cfg = with_overrides(base_cfg, workers={"schedule": {"AB": ab}})
    assert np.isclose(daily_cost(cfg)["total"] - daily_cost(base_cfg)["total"], 1.0)


def test_closed_line_cashier_unpaid(base_cfg):
    cfg = with_overrides(base_cfg, lines={"closures": [{"line": "D", "start": "14:00", "end": "18:00"}]})
    assert np.isclose(daily_cost(base_cfg)["total"] - daily_cost(cfg)["total"], 4 * 1.3)
    paid = with_overrides(cfg, costs={"cashier_paid_when_line_closed": True})
    assert np.isclose(daily_cost(paid)["total"], daily_cost(base_cfg)["total"])


def test_extra_cashier_paid(base_cfg):
    cfg = with_overrides(base_cfg, lines={"extra_cashiers": [{"line": "C", "start": "11:30", "end": "14:00"}]})
    assert np.isclose(daily_cost(cfg)["total"] - daily_cost(base_cfg)["total"], 2.5 * 1.3)
