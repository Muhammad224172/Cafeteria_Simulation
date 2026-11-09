"""Output analysis: t confidence intervals, replication counts, paired comparisons with CRN."""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass

import numpy as np
from scipy import stats


@dataclass(frozen=True)
class CI:
    mean: float
    sd: float
    n: int
    half_width: float
    alpha: float

    @property
    def low(self) -> float:
        return self.mean - self.half_width

    @property
    def high(self) -> float:
        return self.mean + self.half_width

    def as_dict(self) -> dict:
        d = asdict(self)
        d.update(low=self.low, high=self.high)
        return d


def t_ci(x, alpha: float = 0.05) -> CI:
    """Two-sided 100(1-alpha)% t interval for the mean of i.i.d. replication outputs."""
    x = np.asarray(x, dtype=float)
    n = x.size
    if n < 2:
        raise ValueError("need at least two replications")
    sd = float(np.std(x, ddof=1))
    hw = float(stats.t.ppf(1 - alpha / 2, n - 1) * sd / math.sqrt(n))
    return CI(float(np.mean(x)), sd, n, hw, alpha)


def replications_approx(n0: int, h0: float, h_target: float) -> int:
    """The textbook approximation n ~ n0 (h0 / h)^2, rounded up."""
    return max(2, math.ceil(n0 * (h0 / h_target) ** 2))


def replications_needed(sd: float, h_target: float, alpha: float = 0.05, n_min: int = 2, n_max: int = 100_000) -> int:
    """Smallest n with t_{n-1, 1-alpha/2} * sd / sqrt(n) <= h_target (sd treated as known)."""
    for n in range(n_min, n_max + 1):
        if stats.t.ppf(1 - alpha / 2, n - 1) * sd / math.sqrt(n) <= h_target:
            return n
    raise ValueError("target half-width not reachable within n_max replications")


@dataclass(frozen=True)
class PairedResult:
    mean_diff: float  # mean of (candidate - base)
    sd_diff: float
    n: int
    t_stat: float
    p_value: float  # two-sided
    ci_low: float
    ci_high: float
    alpha: float

    def as_dict(self) -> dict:
        return asdict(self)


def paired_t(candidate, base, alpha: float = 0.05) -> PairedResult:
    """Paired-t on per-replication differences (valid for CRN: pairs share random numbers)."""
    d = np.asarray(candidate, dtype=float) - np.asarray(base, dtype=float)
    n = d.size
    mean = float(np.mean(d))
    sd = float(np.std(d, ddof=1))
    se = sd / math.sqrt(n)
    t_stat = mean / se if se > 0 else (0.0 if mean == 0 else math.copysign(math.inf, mean))
    p = float(2 * stats.t.sf(abs(t_stat), n - 1)) if se > 0 else (1.0 if mean == 0 else 0.0)
    hw = float(stats.t.ppf(1 - alpha / 2, n - 1) * se)
    return PairedResult(mean, sd, n, float(t_stat), p, mean - hw, mean + hw, alpha)


def bonferroni_alpha(alpha: float, k: int) -> float:
    """Per-comparison level giving family-wise error <= alpha over k comparisons."""
    return alpha / k


def crn_variance_reduction(candidate, base) -> float:
    """Var(X - Y) under CRN divided by Var(X) + Var(Y) (what independent sampling would give)."""
    x = np.asarray(candidate, dtype=float)
    y = np.asarray(base, dtype=float)
    return float(np.var(x - y, ddof=1) / (np.var(x, ddof=1) + np.var(y, ddof=1)))
