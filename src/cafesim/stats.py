"""Tally (observation-based) and time-persistent (time-weighted) statistics."""

from __future__ import annotations

import numpy as np


class Tally:
    """Collects observations; reports their sample mean."""

    def __init__(self) -> None:
        self.values: list[float] = []

    def record(self, x: float) -> None:
        self.values.append(float(x))

    @property
    def n(self) -> int:
        return len(self.values)

    def mean(self) -> float:
        return float(np.mean(self.values)) if self.values else float("nan")

    def max(self) -> float:
        return float(np.max(self.values)) if self.values else float("nan")


class TimePersistent:
    """A piecewise-constant quantity; keeps its change log so it can be integrated over any window."""

    def __init__(self, t0: float = 0.0, value: float = 0.0) -> None:
        self.times = [float(t0)]
        self.levels = [float(value)]

    @property
    def value(self) -> float:
        return self.levels[-1]

    def update(self, t: float, value: float) -> None:
        if t == self.times[-1]:
            self.levels[-1] = float(value)
        else:
            self.times.append(float(t))
            self.levels.append(float(value))

    def add(self, t: float, delta: float) -> None:
        self.update(t, self.value + delta)

    def integral(self, t_end: float, t_start: float | None = None) -> float:
        times = np.asarray(self.times)
        levels = np.asarray(self.levels)
        t0 = times[0] if t_start is None else t_start
        edges = np.append(times, np.inf)
        lo = np.clip(edges[:-1], t0, t_end)
        hi = np.clip(edges[1:], t0, t_end)
        return float(np.sum(levels * (hi - lo)))

    def time_average(self, t_end: float, t_start: float | None = None) -> float:
        t0 = self.times[0] if t_start is None else t_start
        if t_end <= t0:
            return float("nan")
        return self.integral(t_end, t_start) / (t_end - t0)

    def maximum(self) -> float:
        return float(max(self.levels))

    def sample_on_grid(self, grid: np.ndarray) -> np.ndarray:
        """Value of the step function at each grid time (right-continuous)."""
        idx = np.searchsorted(np.asarray(self.times), grid, side="right") - 1
        idx = np.clip(idx, 0, None)
        return np.asarray(self.levels)[idx]
