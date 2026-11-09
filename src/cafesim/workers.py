"""Workers behind the serving lines: supplies, the prioritized task pool, schedules and experience levels.

Each working area (AB, CD) owns the supplies of its two lines. A task is not a queued object; it is
a condition on the supply state, evaluated whenever a worker could start something:

* Task 1 (priority 1): a food container is empty and nobody is replacing it.
* Task 2 (priority 2): a line's cutlery is empty and nobody is refilling it.
* Task 3 (priority 3): a shelf is below capacity (counting items already being placed) and its
  container still has food. One Task 3 places one item; the worker then picks again, so a newly
  pending Task 1 or 2 is served as soon as the current item is placed.

At most ``max_workers_per_shelf`` workers fill the same shelf section at once (default 1: the
space behind one section fits one worker). Within a priority, the condition that has been pending
longest goes first. The first idle worker of the area takes the chosen task (the ``dispatch``
policy decides which idle worker). Tasks are not preempted. When a shift ends, an idle worker
leaves at once; a busy one finishes the task in hand.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import simpy

from cafesim.stats import TimePersistent

FOOD = ("dessert", "main", "side", "soup")
LEVELS = ("experienced", "inexperienced")
PRIORITY = {"container": 1, "cutlery": 2, "shelf": 3}


@dataclass
class LineSupplies:
    """Shelf, container and cutlery state of one serving line."""

    env: simpy.Environment
    line: str
    shelf_capacity: dict[str, int]
    container_units: dict[str, int]
    cutlery_units: int
    ready_items: frozenset[str]
    start_full: bool = True
    area: WorkArea | None = None
    shelf: dict[str, int] = field(init=False)
    incoming: dict[str, int] = field(init=False)
    container: dict[str, int] = field(init=False)
    replacing: dict[str, bool] = field(init=False)
    container_empty_since: dict[str, float] = field(init=False)
    shelf_short_since: dict[str, float | None] = field(init=False)
    cutlery: int = field(init=False)
    cutlery_refilling: bool = field(init=False, default=False)
    cutlery_empty_since: float = field(init=False, default=0.0)
    _shelf_waiters: dict[str, list[simpy.Event]] = field(init=False)
    _cutlery_waiters: list[simpy.Event] = field(init=False)

    def __post_init__(self) -> None:
        full = self.start_full
        self.shelf = {s: (self.shelf_capacity[s] if full else 0) for s in FOOD}
        self.incoming = dict.fromkeys(FOOD, 0)
        self.container = {s: (self.container_units[s] if full else 0) for s in FOOD}
        self.replacing = dict.fromkeys(FOOD, False)
        self.container_empty_since = dict.fromkeys(FOOD, 0.0)
        self.shelf_short_since = {s: (None if full else 0.0) for s in FOOD}
        self.cutlery = self.cutlery_units if full else 0
        self._shelf_waiters = {s: [] for s in FOOD}
        self._cutlery_waiters = []

    # customer side -------------------------------------------------------------------------
    def wait_for_item(self, section: str) -> simpy.Event:
        ev = self.env.event()
        self._shelf_waiters[section].append(ev)
        return ev

    def take_item(self, section: str) -> None:
        if self.shelf[section] <= 0:
            raise RuntimeError("took an item from an empty shelf")
        self.shelf[section] -= 1
        if self.shelf_short_since[section] is None:
            self.shelf_short_since[section] = self.env.now
        self._notify()

    def wait_for_cutlery(self) -> simpy.Event:
        ev = self.env.event()
        self._cutlery_waiters.append(ev)
        return ev

    def take_cutlery(self) -> None:
        if self.cutlery <= 0:
            raise RuntimeError("took cutlery from an empty container")
        self.cutlery -= 1
        if self.cutlery == 0:
            self.cutlery_empty_since = self.env.now
            self._notify()

    # worker side ---------------------------------------------------------------------------
    def is_ready_item(self, section: str) -> bool:
        return section in self.ready_items

    def finish_container(self, section: str) -> None:
        self.container[section] = self.container_units[section]
        self.replacing[section] = False

    def finish_cutlery(self) -> None:
        self.cutlery = self.cutlery_units
        self.cutlery_refilling = False
        self._wake(self._cutlery_waiters)

    def finish_shelf(self, section: str) -> None:
        self.incoming[section] -= 1
        self.shelf[section] += 1
        if self.shelf[section] + self.incoming[section] >= self.shelf_capacity[section]:
            self.shelf_short_since[section] = None
        self._wake(self._shelf_waiters[section])

    def _wake(self, waiters: list[simpy.Event]) -> None:
        pending = list(waiters)
        waiters.clear()
        for ev in pending:
            ev.succeed()

    def _notify(self) -> None:
        if self.area is not None:
            self.area.dispatch()


@dataclass
class Task:
    kind: str  # container | cutlery | shelf
    supplies: LineSupplies
    section: str | None
    since: float

    @property
    def priority(self) -> int:
        return PRIORITY[self.kind]


class Worker:
    __slots__ = ("wid", "level", "busy", "leaving", "idle_since")

    def __init__(self, wid: int, level: str, now: float):
        self.wid = wid
        self.level = level
        self.busy = False
        self.leaving = False
        self.idle_since = now


class WorkArea:
    def __init__(
        self,
        env: simpy.Environment,
        name: str,
        supplies: list[LineSupplies],
        cfg: dict,
        task_rng: np.random.Generator,
        dispatch_rng: np.random.Generator,
    ):
        self.env = env
        self.name = name
        self.supplies = supplies
        for s in supplies:
            s.area = self
        sup = cfg["supplies"]
        self.replace_mean = sup["container_replace_mean"]
        self.cutlery_mean = sup["cutlery_refill_mean"]
        self.ready_time = sup["ready_item_time"]
        self.prep_mean = sup["prepared_item_time"]["mean"]
        self.prep_sd = sup["prepared_item_time"]["sd"]
        self.slowdown = cfg["workers"]["inexperienced_slowdown"]
        self.max_per_shelf = cfg["workers"].get("max_workers_per_shelf", 1)
        self.policy = cfg["workers"]["dispatch"]
        if self.policy not in ("longest_idle", "prefer_experienced", "random"):
            raise ValueError(f"unknown dispatch policy {self.policy!r}")
        self.task_rng = task_rng
        self.dispatch_rng = dispatch_rng
        self.idle: list[Worker] = []
        self.busy: list[Worker] = []
        self._next_id = 0
        self.staffed = {lv: TimePersistent(env.now, 0) for lv in LEVELS}
        self.busy_count = {lv: TimePersistent(env.now, 0) for lv in LEVELS}
        self.tasks_done = {k: 0 for k in PRIORITY}
        self.task_log: list[tuple[float, int, str]] = []  # (start time, priority, level); kept small
        self.log_tasks = False
        self._dispatching = False

    # staffing ------------------------------------------------------------------------------
    def on_shift(self, level: str) -> int:
        """Workers of ``level`` currently on shift and not about to leave."""
        return sum(1 for w in self.idle if w.level == level) + sum(
            1 for w in self.busy if w.level == level and not w.leaving
        )

    def set_staff(self, level: str, target: int) -> None:
        current = self.on_shift(level)
        if target > current:
            need = target - current
            # first cancel pending departures, then bring in new workers
            for w in self.busy:
                if need and w.level == level and w.leaving:
                    w.leaving = False
                    need -= 1
            for _ in range(need):
                w = Worker(self._next_id, level, self.env.now)
                self._next_id += 1
                self.idle.append(w)
                self.staffed[level].add(self.env.now, 1)
        elif target < current:
            excess = current - target
            for w in [w for w in self.idle if w.level == level][:excess]:
                self.idle.remove(w)
                self.staffed[level].add(self.env.now, -1)
                excess -= 1
            for w in self.busy:
                if excess and w.level == level and not w.leaving:
                    w.leaving = True
                    excess -= 1
        self.dispatch()

    def schedule_process(self, breakpoints: list[float], counts: dict[str, list[int]]):
        for i, t in enumerate(breakpoints):
            if t > self.env.now:
                yield self.env.timeout(t - self.env.now)
            for level in LEVELS:
                self.set_staff(level, counts[level][i])

    # task selection --------------------------------------------------------------------------
    def pending_tasks(self) -> list[Task]:
        tasks: list[Task] = []
        for sup in self.supplies:
            for sec in FOOD:
                if sup.container[sec] == 0 and not sup.replacing[sec]:
                    tasks.append(Task("container", sup, sec, sup.container_empty_since[sec]))
            if sup.cutlery == 0 and not sup.cutlery_refilling:
                tasks.append(Task("cutlery", sup, None, sup.cutlery_empty_since))
            for sec in FOOD:
                short = sup.shelf[sec] + sup.incoming[sec] < sup.shelf_capacity[sec]
                room = self.max_per_shelf is None or sup.incoming[sec] < self.max_per_shelf
                if short and room and sup.container[sec] > 0:
                    since = sup.shelf_short_since[sec]
                    tasks.append(Task("shelf", sup, sec, since if since is not None else self.env.now))
        return tasks

    def next_task(self) -> Task | None:
        tasks = self.pending_tasks()
        if not tasks:
            return None
        # stable: list order (line, section) breaks exact ties
        return min(tasks, key=lambda t: (t.priority, t.since))

    def _claim(self, task: Task) -> None:
        sup, sec = task.supplies, task.section
        if task.kind == "container":
            sup.replacing[sec] = True
        elif task.kind == "cutlery":
            sup.cutlery_refilling = True
        else:
            sup.incoming[sec] += 1
            sup.container[sec] -= 1
            if sup.container[sec] == 0:
                sup.container_empty_since[sec] = self.env.now

    def _pick_worker(self) -> Worker:
        if self.policy == "longest_idle":
            idx = min(range(len(self.idle)), key=lambda i: self.idle[i].idle_since)
        elif self.policy == "prefer_experienced":
            exp = [i for i, w in enumerate(self.idle) if w.level == "experienced"]
            pool = exp if exp else list(range(len(self.idle)))
            idx = min(pool, key=lambda i: self.idle[i].idle_since)
        else:
            idx = int(self.dispatch_rng.integers(len(self.idle)))
        return self.idle.pop(idx)

    def base_duration(self, task: Task) -> float:
        """Task time for an experienced worker."""
        rng = self.task_rng
        if task.kind == "container":
            return float(rng.exponential(self.replace_mean))
        if task.kind == "cutlery":
            return float(rng.exponential(self.cutlery_mean))
        if task.supplies.is_ready_item(task.section):
            return float(rng.uniform(*self.ready_time))
        return max(0.0, float(rng.normal(self.prep_mean, self.prep_sd)))

    def speed_factor(self, level: str) -> float:
        return 1.0 if level == "experienced" else self.slowdown

    def dispatch(self) -> None:
        if self._dispatching:  # re-entrant calls (from _claim side effects) are folded into this loop
            return
        self._dispatching = True
        try:
            while self.idle:
                task = self.next_task()
                if task is None:
                    break
                worker = self._pick_worker()
                self._claim(task)
                worker.busy = True
                self.busy.append(worker)
                self.busy_count[worker.level].add(self.env.now, 1)
                duration = self.base_duration(task) * self.speed_factor(worker.level)
                if self.log_tasks:
                    self.task_log.append((self.env.now, task.priority, worker.level))
                self.env.process(self._work(worker, task, duration))
        finally:
            self._dispatching = False

    def _work(self, worker: Worker, task: Task, duration: float):
        yield self.env.timeout(duration)
        sup = task.supplies
        if task.kind == "container":
            sup.finish_container(task.section)
        elif task.kind == "cutlery":
            sup.finish_cutlery()
        else:
            sup.finish_shelf(task.section)
        self.tasks_done[task.kind] += 1
        self.busy.remove(worker)
        self.busy_count[worker.level].add(self.env.now, -1)
        worker.busy = False
        if worker.leaving:
            self.staffed[worker.level].add(self.env.now, -1)
        else:
            worker.idle_since = self.env.now
            self.idle.append(worker)
        self.dispatch()
