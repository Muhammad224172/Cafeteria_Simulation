import numpy as np
import pytest
import simpy

from cafesim.config import with_overrides
from cafesim.workers import LineSupplies, WorkArea


def _area(cfg, seed=0, lines=("A", "B")):
    env = simpy.Environment()
    sup = cfg["supplies"]
    supplies = [
        LineSupplies(
            env,
            name,
            shelf_capacity=dict(sup["shelf_capacity"]),
            container_units=dict(sup["container_units"]),
            cutlery_units=sup["cutlery_units"],
            ready_items=frozenset({"dessert"}),
        )
        for name in lines
    ]
    area = WorkArea(env, "AB", supplies, cfg, np.random.default_rng(seed), np.random.default_rng(seed + 1))
    area.log_tasks = True
    return env, area, supplies


def test_task_priority_order(base_cfg):
    env, area, (a, b) = _area(base_cfg)
    # three tasks pending at once, created in reverse priority order
    a.shelf["dessert"] -= 1
    a.shelf_short_since["dessert"] = 0.0  # Task 3 (oldest)
    a.cutlery = 0
    a.cutlery_empty_since = 1.0  # Task 2
    b.container["main"] = 0
    b.container_empty_since["main"] = 2.0  # Task 1 (newest)
    area.set_staff("experienced", 1)  # one worker: tasks are done one at a time
    env.run()
    assert [p for _, p, _ in area.task_log] == [1, 2, 3]
    assert b.container["main"] == 45 and a.cutlery == 100 and a.shelf["dessert"] == 10


def test_task1_jumps_ahead_of_queued_task3(base_cfg):
    """A container emptied by a top-up is replaced before the remaining top-ups."""
    env, area, (a, _) = _area(base_cfg)
    a.shelf["main"] = 2  # three items to place
    a.shelf_short_since["main"] = 0.0
    a.container["main"] = 1  # only one unit left in the container
    area.set_staff("experienced", 1)
    env.run()
    assert [p for _, p, _ in area.task_log] == [3, 1, 3, 3]
    assert a.shelf["main"] == 5


def test_older_pending_task_first_within_priority(base_cfg):
    env, area, (a, b) = _area(base_cfg)
    b.shelf["soup"] -= 1
    b.shelf_short_since["soup"] = 5.0
    a.shelf["side"] -= 1
    a.shelf_short_since["side"] = 1.0
    task = area.next_task()
    assert task.supplies is a and task.section == "side"


def test_one_worker_per_shelf_section(base_cfg):
    env, area, (a, _) = _area(base_cfg)
    a.shelf["main"] = 0
    a.shelf_short_since["main"] = 0.0
    area.set_staff("experienced", 3)  # three idle workers, one short shelf
    assert len(area.busy) == 1 and a.incoming["main"] == 1
    cfg = with_overrides(base_cfg, workers={"max_workers_per_shelf": None})
    env, area, (a, _) = _area(cfg)
    a.shelf["main"] = 0
    a.shelf_short_since["main"] = 0.0
    area.set_staff("experienced", 3)
    assert len(area.busy) == 3 and a.incoming["main"] == 3


@pytest.mark.parametrize("kind", ["container", "shelf_prepared", "shelf_ready"])
def test_inexperienced_workers_are_40_percent_slower(base_cfg, kind):
    finish = {}
    for level in ("experienced", "inexperienced"):
        env, area, (a, _) = _area(base_cfg, seed=11)
        if kind == "container":
            a.container["soup"] = 0
        elif kind == "shelf_prepared":
            a.shelf["soup"] -= 1
            a.shelf_short_since["soup"] = 0.0
        else:
            a.shelf["dessert"] -= 1
            a.shelf_short_since["dessert"] = 0.0
        area.set_staff(level, 1)
        env.run()
        finish[level] = env.now
    assert finish["experienced"] > 0
    assert np.isclose(finish["inexperienced"] / finish["experienced"], 1.4)


def test_shift_end_lets_busy_worker_finish(base_cfg):
    env, area, (a, _) = _area(base_cfg)
    a.container["main"] = 0
    area.set_staff("experienced", 1)
    assert len(area.busy) == 1
    area.set_staff("experienced", 0)  # shift ends while the task is in progress
    assert area.busy[0].leaving
    env.run()
    assert a.container["main"] == 45  # the task was completed
    assert area.on_shift("experienced") == 0 and not area.idle
    assert area.staffed["experienced"].value == 0


def test_schedule_changes_staff_at_breakpoints(base_cfg):
    env, area, _ = _area(base_cfg)
    env.process(area.schedule_process([0.0, 100.0, 200.0], {"experienced": [3, 1, 2], "inexperienced": [0, 2, 0]}))
    seen = []

    def probe():
        for t in (50, 150, 250):
            yield env.timeout(t - env.now)
            seen.append((area.on_shift("experienced"), area.on_shift("inexperienced")))

    env.process(probe())
    env.run()
    assert seen == [(3, 0), (1, 2), (2, 0)]
