import numpy as np
from scipy import stats

from cafesim.arrivals import (
    expected_group_size,
    group_size_pmf,
    rate_function,
    sample_group_size,
    thinning_arrivals,
)
from cafesim.config import clock_to_seconds, with_overrides


def test_rate_function_matches_table(base_cfg):
    rate = rate_function(base_cfg)
    assert rate(clock_to_seconds("11:45")) * 3600 == 600
    assert rate(clock_to_seconds("15:00")) * 3600 == 150
    assert rate(clock_to_seconds("19:59")) * 3600 == 240
    assert rate(clock_to_seconds("20:00")) == 0
    # 600*0.5 + 450 + 180 + 150*4 + 450 + 240 arrival events per day
    assert np.isclose(rate.expected_count(0, rate.horizon), 2220)


def test_customer_rate_unit_divides_by_mean_group_size(base_cfg):
    cfg = with_overrides(base_cfg, arrivals={"rate_unit": "customers"})
    eg = expected_group_size(0.5, 6)
    assert np.isclose(rate_function(cfg).expected_count(0, 30600), 2220 / eg)


def test_arrival_counts_per_period_match_expected_rate(base_cfg):
    """Over 300 seeded days, per-period counts are Poisson with the tabulated mean."""
    rate = rate_function(base_cfg)
    periods = [(clock_to_seconds(p["start"]), clock_to_seconds(p["end"])) for p in base_cfg["arrivals"]["periods"]]
    n_days = 300
    counts = np.zeros((n_days, len(periods)))
    for d in range(n_days):
        times = thinning_arrivals(rate, np.random.default_rng(1000 + d))
        for j, (a, b) in enumerate(periods):
            counts[d, j] = np.sum((times >= a) & (times < b))
    expected = np.array([rate.expected_count(a, b) for a, b in periods])
    # z-test of the mean count in each period (Poisson variance = mean); Bonferroni over 6 periods
    z = (counts.mean(axis=0) - expected) / np.sqrt(expected / n_days)
    assert np.all(np.abs(z) < stats.norm.ppf(1 - 0.01 / (2 * len(periods))))
    # Poisson dispersion: variance / mean close to 1 in each period
    dispersion = counts.var(axis=0, ddof=1) / counts.mean(axis=0)
    assert np.all((dispersion > 0.75) & (dispersion < 1.3))


def test_arrivals_are_sorted_and_inside_horizon(base_cfg):
    times = thinning_arrivals(rate_function(base_cfg), np.random.default_rng(0))
    assert np.all(np.diff(times) > 0)
    assert times[0] >= 0 and times[-1] < clock_to_seconds("20:00")


def test_group_size_pmf():
    pmf = group_size_pmf(0.5, 6)
    assert set(pmf) == {1, 2, 3, 4, 5, 6}
    assert np.isclose(sum(pmf.values()), 1.0)
    assert np.isclose(pmf[1], np.exp(-0.5))
    assert np.isclose(pmf[2], 0.5 * np.exp(-0.5))
    # P(size = 6) = P(N >= 5)
    assert np.isclose(pmf[6], stats.poisson.sf(4, 0.5))
    assert np.isclose(
        expected_group_size(0.5, 6), 1 + 0.5 - sum((k - 5) * stats.poisson.pmf(k, 0.5) for k in range(6, 40))
    )


def test_group_size_sampling_distribution():
    rng = np.random.default_rng(7)
    n = 40_000
    sizes = np.array([sample_group_size(rng, 0.5, 6) for _ in range(n)])
    assert sizes.min() == 1 and sizes.max() <= 6
    pmf = group_size_pmf(0.5, 6)
    # chi-square on {1, 2, 3, >=4} (pool the rare sizes so expected counts are >= 5)
    obs = [np.sum(sizes == 1), np.sum(sizes == 2), np.sum(sizes == 3), np.sum(sizes >= 4)]
    exp = [n * pmf[1], n * pmf[2], n * pmf[3], n * (pmf[4] + pmf[5] + pmf[6])]
    _, p = stats.chisquare(obs, exp)
    assert p > 0.001
