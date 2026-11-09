"""Part 3(a): 20 replications of the base configuration, plus interpretation scenarios.

Writes results/baseline/{replications.csv, summary.json, profile.csv, measure1_by_halfhour.csv,
scenario_replications.csv, scenarios.csv}.
"""

from __future__ import annotations

import argparse
import time

import numpy as np
import pandas as pd
from _common import CONFIGS, RESULTS, SEED, write_json

from cafesim.analysis import t_ci
from cafesim.config import load_config
from cafesim.experiment import run_replications

OUT = RESULTS / "baseline"
DIAGNOSTICS = [
    "n_customers",
    "t_close_s",
    "t_empty_s",
    "measure2_system_empty",
    "avg_in_lines",
    "avg_seated",
    "avg_waiting_for_table",
    "table_wait_mean_s",
    "table_wait_frac",
    "sojourn_mean_s",
    "wait_tray_mean_s",
    "wait_section_mean_s",
    "wait_cutlery_space_mean_s",
    "wait_cashier_mean_s",
    "wait_sauce_mean_s",
    "stockout_waits",
    "stockout_wait_per_customer_s",
    "cutlery_waits",
    "util_AB_experienced",
    "util_AB_inexperienced",
    "util_CD_experienced",
    "util_CD_inexperienced",
    "measure1_line_A_s",
    "measure1_line_B_s",
    "measure1_line_C_s",
    "measure1_line_D_s",
]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--reps", type=int, default=20)
    ap.add_argument("--seed", type=int, default=SEED)
    args = ap.parse_args()

    cfg = load_config(CONFIGS / "base.yaml")
    t0 = time.perf_counter()
    df, traces = run_replications(cfg, args.reps, seed=args.seed, trace=True)
    elapsed = time.perf_counter() - t0
    OUT.mkdir(parents=True, exist_ok=True)
    df.to_csv(OUT / "replications.csv", index=False)

    m1, m2 = t_ci(df["measure1_s"]), t_ci(df["measure2"])
    summary = {
        "config": "configs/base.yaml",
        "seed": args.seed,
        "replications": args.reps,
        "measure1_s": m1.as_dict(),
        "measure2": m2.as_dict(),
        "measure2_window": cfg["day"]["measure2_window"],
        "measure2_system_empty": t_ci(df["measure2_system_empty"]).as_dict(),
        "cost_total": float(df["cost_total"].iloc[0]),
        "diagnostics_mean": {k: float(df[k].mean()) for k in DIAGNOSTICS},
        "runtime": {
            "wall_s_per_replication_single_process": float(df["wall_s"].mean()),
            "wall_s_total_parallel": elapsed,
        },
    }
    write_json(OUT / "summary.json", summary)

    # occupancy profile: mean over replications on a common 5-minute grid
    n_grid = max(len(t["grid_s"]) for t in traces)
    grid = np.arange(n_grid) * 300.0
    prof = {"time_s": grid}
    for key in ("in_system", "in_lines", "seated", "waiting_for_table"):
        mat = np.zeros((len(traces), n_grid))
        for i, t in enumerate(traces):
            v = np.asarray(t[key])
            mat[i, : len(v)] = v  # after the last diner leaves the value is 0
        prof[f"{key}_mean"] = mat.mean(axis=0)
    pd.DataFrame(prof).to_csv(OUT / "profile.csv", index=False)

    # measure 1 by arrival half-hour: per-replication bin means, then mean and CI over replications
    bins = np.arange(0, 30600 + 1, 1800)
    per_rep = []
    for t in traces:
        rec = np.asarray(t["pay_records"])
        idx = np.digitize(rec[:, 0], bins) - 1
        per_rep.append([rec[idx == j, 1].mean() if np.any(idx == j) else np.nan for j in range(len(bins) - 1)])
    per_rep = np.asarray(per_rep)
    rows = []
    for j in range(len(bins) - 1):
        col = per_rep[:, j]
        col = col[~np.isnan(col)]
        ci = t_ci(col)
        rows.append({"bin_start_s": bins[j], "mean_s": ci.mean, "half_width_s": ci.half_width})
    pd.DataFrame(rows).to_csv(OUT / "measure1_by_halfhour.csv", index=False)

    # interpretation scenarios on the same replication indices (CRN)
    frames = [df.assign(scenario="base")]
    for path in sorted((CONFIGS / "scenarios").glob("*.yaml")):
        scfg = load_config(path)
        frames.append(run_replications(scfg, args.reps, seed=args.seed).assign(scenario=path.stem))
    allreps = pd.concat(frames, ignore_index=True)
    allreps.to_csv(OUT / "scenario_replications.csv", index=False)
    rows = []
    for name, g in allreps.groupby("scenario", sort=False):
        a, b, c = t_ci(g["measure1_s"]), t_ci(g["measure2"]), t_ci(g["measure2_system_empty"])
        rows.append(
            {
                "scenario": name,
                "measure2_window": "lines_empty" if name != "s02_instructor_interpretation" else "system_empty",
                "measure1_s": a.mean,
                "measure1_hw": a.half_width,
                "measure2": b.mean,
                "measure2_hw": b.half_width,
                "measure2_system_empty": c.mean,
                "measure2_system_empty_hw": c.half_width,
                "customers": g["n_customers"].mean(),
                "t_empty_min": g["t_empty_s"].mean() / 60,
                "table_wait_min": g["table_wait_mean_s"].mean() / 60,
                "stockout_wait_per_customer_s": g["stockout_wait_per_customer_s"].mean(),
            }
        )
    pd.DataFrame(rows).to_csv(OUT / "scenarios.csv", index=False, float_format="%.3f")

    print(f"measure 1: {m1.mean:.2f} s +/- {m1.half_width:.2f} (sd {m1.sd:.2f})")
    print(f"measure 2: {m2.mean:.1f} +/- {m2.half_width:.1f} (sd {m2.sd:.1f}) [{cfg['day']['measure2_window']}]")
    print(f"runtime: {df['wall_s'].mean():.2f} s per replication, {elapsed:.1f} s total for {args.reps} (parallel)")
    print(pd.DataFrame(rows).round(2).to_string(index=False))


if __name__ == "__main__":
    main()
