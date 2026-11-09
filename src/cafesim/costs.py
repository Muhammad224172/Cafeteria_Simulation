"""Daily labour cost of a configuration (deterministic: it depends only on the schedule).

Cost unit: one inexperienced worker-hour. Experienced workers and cashiers cost 1.3 units/hour.
Nobody is paid after 20:00. A cashier is paid for every hour the line is open; a closed line's
cashier is unpaid while it is closed (configurable). A scheduled second cashier at a line
(``lines.extra_cashiers``) is paid for its on-duty hours.
"""

from __future__ import annotations

from cafesim.config import clock_to_seconds

LINES = ("A", "B", "C", "D")


def _periods(cfg: dict) -> list[tuple[float, float]]:
    bps = [clock_to_seconds(b) for b in cfg["workers"]["schedule"]["breakpoints"]]
    paid_end = clock_to_seconds(cfg["costs"]["paid_until"])
    ends = bps[1:] + [paid_end]
    return [(s, min(e, paid_end)) for s, e in zip(bps, ends, strict=True)]


def worker_hours(cfg: dict) -> dict[str, dict[str, float]]:
    """Paid worker-hours per area and experience level."""
    sched = cfg["workers"]["schedule"]
    out: dict[str, dict[str, float]] = {}
    for area in ("AB", "CD"):
        out[area] = {}
        for level in ("experienced", "inexperienced"):
            hours = 0.0
            for (s, e), n in zip(_periods(cfg), sched[area][level], strict=True):
                hours += n * max(0.0, e - s) / 3600.0
            out[area][level] = hours
    return out


def closed_hours(cfg: dict, line: str) -> float:
    paid_end = clock_to_seconds(cfg["costs"]["paid_until"])
    total = 0.0
    for c in cfg["lines"].get("closures", []):
        if c["line"] == line:
            s, e = clock_to_seconds(c["start"]), min(clock_to_seconds(c["end"]), paid_end)
            total += max(0.0, e - s) / 3600.0
    return total


def daily_cost(cfg: dict) -> dict[str, float]:
    c = cfg["costs"]
    w = c["inexperienced_wage"]
    exp_rate = w * c["experienced_multiplier"]
    cashier_rate = w * c["cashier_multiplier"]
    day_hours = (clock_to_seconds(c["paid_until"]) - clock_to_seconds(cfg["day"]["open"])) / 3600.0
    hours = worker_hours(cfg)
    result: dict[str, float] = {}
    total_workers = 0.0
    for area, levels in hours.items():
        cost = levels["experienced"] * exp_rate + levels["inexperienced"] * w
        result[f"workers_{area}"] = cost
        total_workers += cost
    cashier_hours = 0.0
    for line in LINES:
        closed = closed_hours(cfg, line) if not c.get("cashier_paid_when_line_closed", False) else 0.0
        cashier_hours += day_hours - closed
    paid_end = clock_to_seconds(c["paid_until"])
    for e in cfg["lines"].get("extra_cashiers", []):
        start, end = clock_to_seconds(e["start"]), min(clock_to_seconds(e["end"]), paid_end)
        cashier_hours += max(0.0, end - start) / 3600.0
    result["workers"] = total_workers
    result["cashiers"] = cashier_hours * cashier_rate
    result["cashier_hours"] = cashier_hours
    result["total"] = total_workers + result["cashiers"]
    return result
