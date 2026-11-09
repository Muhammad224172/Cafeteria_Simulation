"""Part 3(b): replications needed for a 10 s half-width on measure 1, then verified by simulation.

1. From the n0 = 20 baseline replications: half-width h0 and sd s0.
2. Approximation n ~ n0 (h0 / h)^2 and the exact search min{n : t_{n-1} s0 / sqrt(n) <= h}.
3. Verification: run that many fresh replications once and report the half-width actually obtained.
   Because a half-width from a handful of replications is itself very noisy, also repeat the
   n-replication experiment many times (disjoint replication indices) and report how often the
   half-width meets the target and how often the interval covers a high-precision estimate of the mean.

Writes results/replications.json.
"""

from __future__ import annotations

import argparse

import numpy as np
import pandas as pd
from _common import CONFIGS, RESULTS, SEED, write_json

from cafesim.analysis import replications_approx, replications_needed, t_ci
from cafesim.config import load_config
from cafesim.experiment import run_replications

TARGET_S = 10.0
FRESH_START = 5000  # replication indices disjoint from every other experiment in this repo


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--macro", type=int, default=200, help="repetitions of the n-replication experiment")
    ap.add_argument("--seed", type=int, default=SEED)
    args = ap.parse_args()

    base = pd.read_csv(RESULTS / "baseline" / "replications.csv")
    pilot = t_ci(base["measure1_s"])
    n_approx = replications_approx(pilot.n, pilot.half_width, TARGET_S)
    n_exact = replications_needed(pilot.sd, TARGET_S)
    n_run = max(n_approx, n_exact)

    cfg = load_config(CONFIGS / "base.yaml")
    once = run_replications(cfg, n_run, seed=args.seed, start=FRESH_START)
    once_ci = t_ci(once["measure1_s"])

    macro = run_replications(cfg, args.macro * n_run, seed=args.seed, start=FRESH_START + 1000)
    x = macro["measure1_s"].to_numpy()
    reference = t_ci(x)  # all macro replications pooled: a high-precision estimate of the mean
    hws, covers = [], []
    for k in range(args.macro):
        ci = t_ci(x[k * n_run : (k + 1) * n_run])
        hws.append(ci.half_width)
        covers.append(ci.low <= reference.mean <= ci.high)
    hws = np.asarray(hws)

    # same calculation with the instructor model's own pilot (sd 5.15 s over 20 replications)
    instructor_sd = 5.155
    instructor_hw = 2.41
    out = {
        "target_half_width_s": TARGET_S,
        "pilot": {"n0": pilot.n, "mean_s": pilot.mean, "sd_s": pilot.sd, "half_width_s": pilot.half_width},
        "n_approx_n0_h0_over_h_squared": n_approx,
        "n_exact_t_search": n_exact,
        "n_used": n_run,
        "verification_single_run": {
            "replication_indices": [FRESH_START, FRESH_START + n_run - 1],
            "mean_s": once_ci.mean,
            "sd_s": once_ci.sd,
            "half_width_s": once_ci.half_width,
            "meets_target": bool(once_ci.half_width <= TARGET_S),
        },
        "verification_repeated": {
            "experiments": args.macro,
            "replications_each": n_run,
            "share_half_width_le_target": float(np.mean(hws <= TARGET_S)),
            "half_width_median_s": float(np.median(hws)),
            "half_width_p90_s": float(np.quantile(hws, 0.9)),
            "coverage_of_pooled_mean": float(np.mean(covers)),
            "pooled_mean_s": reference.mean,
            "pooled_half_width_s": reference.half_width,
            "pooled_replications": reference.n,
        },
        "same_rule_with_instructor_pilot": {
            "sd_s": instructor_sd,
            "half_width_s": instructor_hw,
            "n_approx": replications_approx(20, instructor_hw, TARGET_S),
            "n_exact": replications_needed(instructor_sd, TARGET_S),
        },
        "measure2_for_reference": {
            "sd": t_ci(base["measure2"]).sd,
            "n_for_half_width_10_customers": replications_needed(t_ci(base["measure2"]).sd, 10.0),
        },
    }
    write_json(RESULTS / "replications.json", out)
    pd.DataFrame({"half_width_s": hws}).to_csv(RESULTS / "replications_halfwidths.csv", index=False)
    print(
        f"pilot sd {pilot.sd:.2f} s, h0 {pilot.half_width:.2f} s -> n approx {n_approx}, exact {n_exact};"
        f" single fresh run of {n_run}: h = {once_ci.half_width:.2f} s;"
        f" repeated x{args.macro}: P(h <= 10) = {np.mean(hws <= TARGET_S):.3f}, coverage {np.mean(covers):.3f}"
    )


if __name__ == "__main__":
    main()
