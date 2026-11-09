"""SimPy model of the cafeteria: arrivals, serving lines, payment, sauce table, dining and workers.

Clock: seconds after opening (t = 0 is 11:30). One call to :func:`simulate` runs one day.
The day is simulated until the last diner leaves, so every customer who arrives also departs.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import simpy

from cafesim.arrivals import rate_function, sample_group_size, thinning_arrivals
from cafesim.config import clock_to_seconds
from cafesim.costs import daily_cost
from cafesim.seating import DiningArea
from cafesim.stats import Tally, TimePersistent
from cafesim.streams import Streams, tria, unif
from cafesim.workers import FOOD, LEVELS, LineSupplies, WorkArea

LINES = ("A", "B", "C", "D")
AREA_OF = {"A": "AB", "B": "AB", "C": "CD", "D": "CD"}
MEAL_LINE = {"vegan": "A", "salad": "C"}


@dataclass(slots=True)
class Customer:
    cid: int
    group: Group
    meal: str
    arrival: float
    wants: tuple[bool, bool, bool, bool]
    item_times: tuple[float, float, float, float]
    walks: tuple[float, ...]  # 6 walks: tray->dessert, ..., cutlery->payment
    tray_time: float
    cutlery_time: float
    pay_kind: str
    pay_time: float
    sauce: bool
    sauce_walk: float
    sauce_time: float
    eat_time: float
    line: str = ""


@dataclass(slots=True)
class Group:
    gid: int
    size: int
    arrival: float
    members: list[Customer] = field(default_factory=list)
    ready: int = 0


class Line:
    def __init__(self, env: simpy.Environment, name: str, supplies: LineSupplies):
        self.name = name
        self.tray = simpy.Resource(env, capacity=1)
        self.space = {s: simpy.Resource(env, capacity=1) for s in (*FOOD, "cutlery")}
        # Capacity 2 so a scheduled second cashier can open; an off-duty second cashier is
        # represented by a placeholder request that holds the slot (see Cafeteria.extra_cashier_process).
        self.cashier = simpy.PriorityResource(env, capacity=2)
        self.supplies = supplies
        self.in_line = 0  # joined the line and not yet finished paying


class Cafeteria:
    def __init__(self, cfg: dict, streams: Streams, trace: bool = False):
        self.cfg = cfg
        self.streams = streams
        self.trace = trace
        self.env = env = simpy.Environment()
        sup = cfg["supplies"]
        ready_main = set(sup["ready_main_lines"])
        self.lines: dict[str, Line] = {}
        for name in LINES:
            ready = {"dessert"} | ({"main"} if name in ready_main else set())
            supplies = LineSupplies(
                env,
                name,
                shelf_capacity=dict(sup["shelf_capacity"]),
                container_units=dict(sup["container_units"]),
                cutlery_units=int(sup["cutlery_units"]),
                ready_items=frozenset(ready),
                start_full=bool(sup.get("start_full", True)),
            )
            self.lines[name] = Line(env, name, supplies)
        self.areas = {
            area: WorkArea(
                env,
                area,
                [self.lines[x].supplies for x in LINES if AREA_OF[x] == area],
                cfg,
                streams["tasks"],
                streams["dispatch"],
            )
            for area in ("AB", "CD")
        }
        sauce = cfg["sauce"]
        self.sauce_table = simpy.Resource(env, capacity=int(sauce["capacity"]))
        dining = cfg["dining"]
        self.group_eating = dining.get("group_eating", "last_member")
        if self.group_eating not in ("last_member", "first_member"):
            raise ValueError(f"unknown group_eating {self.group_eating!r}")
        self.dining = DiningArea(env, int(dining["tables"]), int(dining["seats"]), bool(dining["allow_overtaking"]))

        self.last_arrival = clock_to_seconds(cfg["day"]["last_arrival"])
        self.closures = [
            (c["line"], clock_to_seconds(c["start"]), clock_to_seconds(c["end"])) for c in cfg["lines"]["closures"]
        ]

        # statistics
        self.in_system = TimePersistent(0.0, 0)
        self.in_lines = TimePersistent(0.0, 0)
        self.time_to_pay = Tally()
        self.time_to_pay_by_line = {x: Tally() for x in LINES}
        self.pay_records: list[tuple[float, float]] = []  # (arrival, time to pay)
        self.wait = {k: Tally() for k in ("tray", "section", "cutlery_space", "cashier", "sauce")}
        self.stockout_wait = Tally()
        self.cutlery_wait = Tally()
        self.table_wait = Tally()  # per group
        self.sojourn = Tally()  # per customer, arrival to leaving the dining area
        self.n_arrived = 0
        self.n_left = 0
        self.n_groups = 0
        self.t_close: float | None = None
        self.t_empty: float | None = None
        self.arrival_times: list[float] = []
        self.group_sizes: list[int] = []

    # helpers -----------------------------------------------------------------------------------
    def is_open(self, line: str, t: float) -> bool:
        return not any(name == line and s <= t < e for name, s, e in self.closures)

    def standard_line(self, t: float) -> str:
        b_open, d_open = self.is_open("B", t), self.is_open("D", t)
        if b_open and not d_open:
            return "B"
        if d_open and not b_open:
            return "D"
        nb, nd = self.lines["B"].in_line, self.lines["D"].in_line
        if nb < nd:
            return "B"
        if nd < nb:
            return "D"
        return self.cfg["routing"]["tie_break"]

    def _draw_meal(self) -> str:
        mix = self.cfg["routing"]["meal_mix"]
        u = self.streams["meal"].random()
        if u < mix["vegan"]:
            return "vegan"
        if u < mix["vegan"] + mix["standard"]:
            return "standard"
        return "salad"

    def _make_customer(self, cid: int, group: Group, meal: str) -> Customer:
        st = self.cfg["stations"]
        s = self.streams
        wants = tuple(bool(u < st["items"][sec]["p"]) for sec, u in zip(FOOD, s["item_wanted"].random(4), strict=True))
        item_times = tuple(unif(s["item_time"], st["items"][sec]["time"]) for sec in FOOD)
        walks = tuple(float(x) for x in s["walk"].uniform(st["walk"][0], st["walk"][1], 6))
        pay = st["payment"]
        rng = s["payment"]
        u_kind, u_credit = rng.random(), rng.random()
        if u_kind < pay["credit_card"]["p"]:
            kind, params = "credit_card", pay["credit_card"]["tria"]
        elif u_kind < pay["credit_card"]["p"] + pay["cash"]["p"]:
            kind, params = "cash", pay["cash"]["tria"]
        elif u_credit < pay["university_card"]["enough_credit_p"]:
            kind, params = "university_card", pay["university_card"]["enough"]
        else:
            kind, params = "university_card_top_up", pay["university_card"]["top_up"]
        pay_time = tria(rng, *params)
        sc = self.cfg["sauce"]
        rs = s["sauce"]
        sauce = bool(rs.random() < sc["p"])
        sauce_walk = unif(rs, sc["walk"])
        sauce_time = tria(rs, *sc["time"])
        eat = unif(s["eating"], self.cfg["dining"]["eat_minutes"]) * 60.0
        return Customer(
            cid=cid,
            group=group,
            meal=meal,
            arrival=self.env.now,
            wants=wants,
            item_times=item_times,
            walks=walks,
            tray_time=unif(s["tray"], st["tray"]),
            cutlery_time=unif(s["cutlery"], st["cutlery"]),
            pay_kind=kind,
            pay_time=pay_time,
            sauce=sauce,
            sauce_walk=sauce_walk,
            sauce_time=sauce_time,
            eat_time=eat,
        )

    # processes -------------------------------------------------------------------------------
    def arrival_process(self, times: np.ndarray):
        gs = self.cfg["arrivals"]["group_size"]
        cid = 0
        for gid, t in enumerate(times):
            yield self.env.timeout(t - self.env.now)
            size = sample_group_size(self.streams["group_size"], gs["poisson_mean"], gs["max"])
            group = Group(gid, size, self.env.now)
            self.n_groups += 1
            self.arrival_times.append(self.env.now)
            self.group_sizes.append(size)
            per_group = self.cfg["routing"]["meal_choice"] == "per_group"
            group_meal = self._draw_meal() if per_group else None
            std_line = self.standard_line(self.env.now)
            for _ in range(size):
                meal = group_meal or self._draw_meal()
                c = self._make_customer(cid, group, meal)
                cid += 1
                c.line = MEAL_LINE.get(meal, std_line)
                group.members.append(c)
                self.lines[c.line].in_line += 1
            self.n_arrived += size
            self.in_system.add(self.env.now, size)
            self.in_lines.add(self.env.now, size)
            for c in group.members:
                self.env.process(self.customer_process(c))
        if self.env.now < self.last_arrival:
            yield self.env.timeout(self.last_arrival - self.env.now)
        self._check_close()

    def _check_close(self) -> None:
        if self.t_close is None and self.env.now >= self.last_arrival and self.in_lines.value == 0:
            self.t_close = self.env.now

    def customer_process(self, c: Customer):
        env = self.env
        line = self.lines[c.line]
        sup = line.supplies

        t = env.now
        req = line.tray.request()
        yield req
        self.wait["tray"].record(env.now - t)
        yield env.timeout(c.tray_time)
        yield env.timeout(c.walks[0])
        line.tray.release(req)

        for k, sec in enumerate(FOOD):
            t = env.now
            req = line.space[sec].request()
            yield req
            self.wait["section"].record(env.now - t)
            if c.wants[k]:
                if sup.shelf[sec] == 0:
                    t = env.now
                    while sup.shelf[sec] == 0:
                        yield sup.wait_for_item(sec)
                    self.stockout_wait.record(env.now - t)
                sup.take_item(sec)
                yield env.timeout(c.item_times[k])
            yield env.timeout(c.walks[k + 1])
            line.space[sec].release(req)

        t = env.now
        req = line.space["cutlery"].request()
        yield req
        self.wait["cutlery_space"].record(env.now - t)
        if sup.cutlery == 0:
            t = env.now
            while sup.cutlery == 0:
                yield sup.wait_for_cutlery()
            self.cutlery_wait.record(env.now - t)
        sup.take_cutlery()
        yield env.timeout(c.cutlery_time)
        yield env.timeout(c.walks[5])
        line.space["cutlery"].release(req)

        t = env.now
        with line.cashier.request(priority=1) as req:
            yield req
            self.wait["cashier"].record(env.now - t)
            yield env.timeout(c.pay_time)
        elapsed = env.now - c.arrival
        self.time_to_pay.record(elapsed)
        self.time_to_pay_by_line[c.line].record(elapsed)
        self.pay_records.append((c.arrival, elapsed))
        line.in_line -= 1
        self.in_lines.add(env.now, -1)
        self._check_close()

        if c.sauce:
            yield env.timeout(c.sauce_walk)
            t = env.now
            with self.sauce_table.request() as req:
                yield req
                self.wait["sauce"].record(env.now - t)
                yield env.timeout(c.sauce_time)

        g = c.group
        g.ready += 1
        if g.ready == g.size:
            env.process(self.group_process(g))

    def group_process(self, g: Group):
        env = self.env
        t = env.now
        table = yield self.dining.request(g.size)
        self.table_wait.record(env.now - t)
        eats = [m.eat_time for m in g.members]
        yield env.timeout(max(eats) if self.group_eating == "last_member" else min(eats))
        self.dining.release(table, g.size)
        self.in_system.add(env.now, -g.size)
        for m in g.members:
            self.sojourn.record(env.now - m.arrival)
        self.n_left += g.size
        if self.n_left == self.n_arrived and env.now >= self.last_arrival:
            self.t_empty = env.now

    def extra_cashier_process(self, line: str, windows: list[tuple[float, float]]):
        """Hold the second till closed outside its on-duty windows.

        The placeholder request has priority over customers, so when the second cashier goes off
        duty they finish the customer in hand and then the till closes (like a worker's shift end).
        """
        till = self.lines[line].cashier
        t = 0.0
        for start, end in [*sorted(windows), (float("inf"), float("inf"))]:
            if start > t:
                req = till.request(priority=0)
                yield req
                if start == float("inf"):
                    return  # closed for the rest of the day; the request is never released
                yield self.env.timeout(max(0.0, start - self.env.now))
                till.release(req)
            if end == float("inf"):
                return
            yield self.env.timeout(max(0.0, end - self.env.now))
            t = end

    # run -------------------------------------------------------------------------------------
    def run(self) -> dict:
        cfg = self.cfg
        sched = cfg["workers"]["schedule"]
        bps = [clock_to_seconds(b) for b in sched["breakpoints"]]
        for area, wa in self.areas.items():
            self.env.process(wa.schedule_process(bps, {lv: sched[area][lv] for lv in LEVELS}))
        extra: dict[str, list[tuple[float, float]]] = {x: [] for x in LINES}
        for e in cfg["lines"].get("extra_cashiers", []):
            extra[e["line"]].append((clock_to_seconds(e["start"]), clock_to_seconds(e["end"])))
        for x in LINES:
            self.env.process(self.extra_cashier_process(x, extra[x]))
        times = thinning_arrivals(rate_function(cfg), self.streams["arrivals"])
        self.env.process(self.arrival_process(times))
        self.env.run()
        return self.summary()

    def summary(self) -> dict:
        if self.n_left != self.n_arrived:
            raise RuntimeError(f"customer conservation violated: {self.n_arrived} arrived, {self.n_left} left")
        t_close = self.t_close if self.t_close is not None else self.last_arrival
        t_empty = self.t_empty if self.t_empty is not None else self.env.now
        window = self.cfg["day"]["measure2_window"]
        if window not in ("lines_empty", "system_empty"):
            raise ValueError(f"unknown measure2_window {window!r}")
        t_end = t_close if window == "lines_empty" else t_empty
        out: dict = {
            "measure1_s": self.time_to_pay.mean(),
            "measure2": self.in_system.time_average(t_end),
            "measure2_lines_empty": self.in_system.time_average(t_close),
            "measure2_system_empty": self.in_system.time_average(t_empty),
            "measure2_until_2000": self.in_system.time_average(self.last_arrival),
            "sojourn_mean_s": self.sojourn.mean(),
            "measure2_window": window,
            "n_customers": self.n_arrived,
            "n_groups": self.n_groups,
            "t_close_s": t_close,
            "t_empty_s": t_empty,
            "time_to_pay_max_s": self.time_to_pay.max(),
            "avg_in_lines": self.in_lines.time_average(t_close),
            "avg_seated": self.dining.seated.time_average(t_close),
            "avg_waiting_for_table": self.dining.waiting.time_average(t_close),
            "table_wait_mean_s": self.table_wait.mean(),
            "table_wait_frac": float(np.mean(np.asarray(self.table_wait.values) > 0)) if self.table_wait.n else 0.0,
            "stockout_waits": self.stockout_wait.n,
            "stockout_wait_mean_s": self.stockout_wait.mean() if self.stockout_wait.n else 0.0,
            "stockout_wait_per_customer_s": float(np.sum(self.stockout_wait.values)) / max(self.n_arrived, 1),
            "cutlery_waits": self.cutlery_wait.n,
            "max_in_system": self.in_system.maximum(),
        }
        for k, tally in self.wait.items():
            out[f"wait_{k}_mean_s"] = tally.mean() if tally.n else 0.0
        for x in LINES:
            out[f"measure1_line_{x}_s"] = self.time_to_pay_by_line[x].mean()
            out[f"customers_line_{x}"] = self.time_to_pay_by_line[x].n
        paid_end = clock_to_seconds(self.cfg["costs"]["paid_until"])
        for area, wa in self.areas.items():
            for lv in LEVELS:
                staffed = wa.staffed[lv].integral(paid_end)
                busy = wa.busy_count[lv].integral(paid_end)
                out[f"util_{area}_{lv}"] = busy / staffed if staffed > 0 else float("nan")
            for kind, n in wa.tasks_done.items():
                out[f"tasks_{area}_{kind}"] = n
        cost = daily_cost(self.cfg)
        out["cost_total"] = cost["total"]
        out["cost_workers"] = cost["workers"]
        out["cost_cashiers"] = cost["cashiers"]
        if self.trace:
            grid = np.arange(0.0, t_empty + 300.0, 300.0)
            out["trace"] = {
                "grid_s": grid.tolist(),
                "in_system": self.in_system.sample_on_grid(grid).tolist(),
                "in_lines": self.in_lines.sample_on_grid(grid).tolist(),
                "seated": self.dining.seated.sample_on_grid(grid).tolist(),
                "waiting_for_table": self.dining.waiting.sample_on_grid(grid).tolist(),
                "pay_records": self.pay_records,
            }
        return out


def simulate(cfg: dict, seed: int, replication: int, trace: bool = False) -> dict:
    """Run one replication (one day) and return its summary statistics."""
    model = Cafeteria(cfg, Streams(seed, replication), trace=trace)
    return model.run()
