import numpy as np
import pytest
from scipy import stats

from cafesim.analysis import (
    bonferroni_alpha,
    paired_t,
    replications_approx,
    replications_needed,
    t_ci,
)
from cafesim.stats import Tally, TimePersistent


def test_time_persistent_integral():
    tp = TimePersistent(0.0, 0)
    tp.update(2.0, 3)  # 0 on [0,2), 3 on [2,5), 1 on [5, ...)
    tp.update(5.0, 1)
    assert tp.integral(10.0) == pytest.approx(0 * 2 + 3 * 3 + 1 * 5)
    assert tp.time_average(10.0) == pytest.approx(14 / 10)
    assert tp.integral(4.0) == pytest.approx(6.0)
    assert tp.integral(6.0, t_start=3.0) == pytest.approx(3 * 2 + 1 * 1)
    assert list(tp.sample_on_grid(np.array([0.0, 2.0, 4.9, 5.0]))) == [0, 3, 3, 1]


def test_tally():
    t = Tally()
    for x in (1.0, 2.0, 6.0):
        t.record(x)
    assert t.n == 3 and t.mean() == 3.0 and t.max() == 6.0


def test_t_ci_matches_scipy():
    x = np.random.default_rng(0).normal(50, 4, size=20)
    ci = t_ci(x)
    lo, hi = stats.t.interval(0.95, len(x) - 1, loc=x.mean(), scale=stats.sem(x))
    assert ci.low == pytest.approx(lo) and ci.high == pytest.approx(hi)


def test_replications_needed():
    # with sd = 10 and target h = 5: n = 18 satisfies t_{17} * 10 / sqrt(18) = 4.97 <= 5, n = 17 does not
    assert replications_needed(10.0, 5.0) == 18
    assert replications_approx(20, 2.0, 1.0) == 80
    assert replications_approx(20, 1.0, 10.0) == 2


def test_paired_t_matches_scipy():
    rng = np.random.default_rng(1)
    base = rng.normal(50, 5, 30)
    cand = base - 1.0 + rng.normal(0, 1, 30)
    r = paired_t(cand, base)
    ref = stats.ttest_rel(cand, base)
    assert r.t_stat == pytest.approx(ref.statistic)
    assert r.p_value == pytest.approx(ref.pvalue)
    assert r.ci_low < r.mean_diff < r.ci_high < 0


def test_bonferroni():
    assert bonferroni_alpha(0.05, 10) == pytest.approx(0.005)
