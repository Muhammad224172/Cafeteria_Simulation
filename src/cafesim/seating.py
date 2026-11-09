"""Dining-area table allocation.

Rule (from the problem): a party takes an empty table if one exists; otherwise the least occupied
table that can seat the whole party. Ties go to the lowest table number. Parties that cannot be
seated wait in a single queue. With ``allow_overtaking=False`` the queue is strict FIFO (a large
party at the head blocks smaller ones behind it); with ``True`` any waiting party that fits is seated.
"""

from __future__ import annotations

from collections import deque

import simpy

from cafesim.stats import TimePersistent


def choose_table(occupancy: list[int], seats: int, size: int) -> int | None:
    """Index of the table a party of ``size`` takes, or None if no table can seat it."""
    if size > seats:
        raise ValueError(f"party of {size} cannot fit at a {seats}-seat table")
    for i, occ in enumerate(occupancy):
        if occ == 0:
            return i
    best = None
    for i, occ in enumerate(occupancy):
        if seats - occ >= size and (best is None or occ < occupancy[best]):
            best = i
    return best


class DiningArea:
    def __init__(self, env: simpy.Environment, tables: int, seats: int, allow_overtaking: bool = False):
        self.env = env
        self.seats = seats
        self.occupancy = [0] * tables
        self.allow_overtaking = allow_overtaking
        self.queue: deque[tuple[int, simpy.Event]] = deque()
        self.seated = TimePersistent(env.now, 0)
        self.waiting = TimePersistent(env.now, 0)

    def request(self, size: int) -> simpy.Event:
        """Event that fires with the table index once the party is seated."""
        ev = self.env.event()
        self.queue.append((size, ev))
        self.waiting.add(self.env.now, size)
        self._assign()
        return ev

    def release(self, table: int, size: int) -> None:
        self.occupancy[table] -= size
        if self.occupancy[table] < 0:
            raise RuntimeError("negative table occupancy")
        self.seated.add(self.env.now, -size)
        self._assign()

    def _assign(self) -> None:
        i = 0
        while i < len(self.queue):
            size, ev = self.queue[i]
            table = choose_table(self.occupancy, self.seats, size)
            if table is None:
                if not self.allow_overtaking:
                    return
                i += 1
                continue
            del self.queue[i]
            self.occupancy[table] += size
            self.seated.add(self.env.now, size)
            self.waiting.add(self.env.now, -size)
            ev.succeed(table)
