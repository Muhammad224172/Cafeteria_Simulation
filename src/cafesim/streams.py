"""Named, independent random-number streams.

Each stream is a NumPy ``Generator`` seeded from ``SeedSequence(seed, spawn_key=(replication, stream_id))``.
The seed depends only on (seed, replication, stream name) and never on the configuration, so two
configurations run with the same seed see the same arrival times, group sizes, meal choices and
service-time draws: common random numbers (CRN).

Customer attributes are drawn at arrival from per-attribute streams, in arrival order. A configuration
change (a different schedule, a closed line) therefore cannot shift which random number a given
customer receives. Worker task times come from their own stream; their order can differ between
configurations, which is the only place synchronisation is partial.
"""

from __future__ import annotations

import numpy as np

STREAM_NAMES = (
    "arrivals",
    "group_size",
    "meal",
    "item_wanted",
    "item_time",
    "walk",
    "tray",
    "cutlery",
    "payment",
    "sauce",
    "eating",
    "tasks",
    "dispatch",
)


class Streams:
    def __init__(self, seed: int, replication: int):
        self.seed = int(seed)
        self.replication = int(replication)
        self._gens = {
            name: np.random.Generator(np.random.PCG64(np.random.SeedSequence(self.seed, spawn_key=(replication, i))))
            for i, name in enumerate(STREAM_NAMES)
        }

    def __getitem__(self, name: str) -> np.random.Generator:
        return self._gens[name]


def tria(rng: np.random.Generator, a: float, m: float, b: float) -> float:
    return float(rng.triangular(a, m, b))


def unif(rng: np.random.Generator, ab) -> float:
    return float(rng.uniform(ab[0], ab[1]))
