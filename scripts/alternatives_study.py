"""Part 3(c, d): screen equal-or-cheaper alternatives with CRN, then confirm the best on fresh replications.

Stage 1 (screening). Every candidate in configs/alternatives/ and the base run on the same
replication indices 0..19, so outputs are paired by common random numbers. For each candidate a
paired-t test on measure 1 (candidate - base) is run at the Bonferroni level alpha/k, k = number of
candidates. Measure 2 is tested the same way. A candidate is eligible if it costs no more than the
base, improves measure 1 significantly, and does not make measure 2 significantly worse. The
eligible candidate with the largest mean reduction of measure 1 is selected.

Stage 2 (confirmation). Selecting the best of k on the same data biases its estimated gain, so the
selected candidate is re-run against the base on fresh, disjoint replication indices. The number of
replications is chosen from the screening sd of the paired differences so that the 95% half-width of
the measure-1 difference is at most 0.5 s. Both measures are tested at alpha/2 (Bonferroni over the
two measures).

Writes results/alternatives/{screening.csv, screening_replications.csv, confirmation.json,
confirmation_replications.csv}.
"""

from __future__ import annotations

import argparse

import pandas as pd
from _common import CONFIGS, RESULTS, SEED, write_json

from cafesim.analysis import bonferroni_alpha, crn_variance_reduction, paired_t, replications_needed
from cafesim.config import load_config
from cafesim.costs import daily_cost
from cafesim.experiment import run_replications

OUT = RESULTS / "alternatives"
ALPHA = 0.05
CONFIRM_START = 10_000
CONFIRM_TARGET_HW_S = 0.5


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--reps", type=int, default=20)
    ap.add_argument("--seed", type=int, default=SEED)
    args = ap.parse_args()

    base_cfg = load_config(CONFIGS / "base.yaml")
    base_cost = daily_cost(base_cfg)["total"]
    paths = sorted((CONFIGS / "alternatives").glob("*.yaml"))
    k = len(paths)
    alpha_k = bonferroni_alpha(ALPHA, k)

    base = run_replications(base_cfg, args.reps, seed=args.seed)
    frames = [base.assign(candidate="base")]
    rows = []
    for path in paths:
        cfg = load_config(path)
        cost = daily_cost(cfg)["total"]
        df = run_replications(cfg, args.reps, seed=args.seed)
        frames.append(df.assign(candidate=path.stem))
        r1 = paired_t(df["measure1_s"], base["measure1_s"], alpha=alpha_k)
        r2 = paired_t(df["measure2"], base["measure2"], alpha=alpha_k)
        rows.append(
            {
                "candidate": path.stem,
                "description": cfg["description"],
                "cost": cost,
                "cost_change": cost - base_cost,
                "measure1_s": df["measure1_s"].mean(),
                "d_measure1_s": r1.mean_diff,
                "d_measure1_ci_low": r1.ci_low,
                "d_measure1_ci_high": r1.ci_high,
                "d_measure1_sd": r1.sd_diff,
                "p_measure1": r1.p_value,
                "measure2": df["measure2"].mean(),
                "d_measure2": r2.mean_diff,
                "d_measure2_ci_low": r2.ci_low,
                "d_measure2_ci_high": r2.ci_high,
                "p_measure2": r2.p_value,
                "crn_var_ratio_measure1": crn_variance_reduction(df["measure1_s"], base["measure1_s"]),
                "wait_cashier_s": df["wait_cashier_mean_s"].mean(),
                "stockout_wait_per_customer_s": df["stockout_wait_per_customer_s"].mean(),
                "eligible": bool(
                    cost <= base_cost + 1e-9
                    and r1.p_value < alpha_k
                    and r1.mean_diff < 0
                    and not (r2.p_value < alpha_k and r2.mean_diff > 0)
                ),
            }
        )
    OUT.mkdir(parents=True, exist_ok=True)
    screening = pd.DataFrame(rows)
    screening.to_csv(OUT / "screening.csv", index=False, float_format="%.4f")
    pd.concat(frames, ignore_index=True).to_csv(OUT / "screening_replications.csv", index=False)

    eligible = screening[screening["eligible"]]
    if eligible.empty:
        print("no candidate passed screening")
        write_json(OUT / "confirmation.json", {"selected": None, "screened": k, "alpha_per_test": alpha_k})
        return
    best = eligible.sort_values("d_measure1_s").iloc[0]
    best_cfg = load_config(CONFIGS / "alternatives" / f"{best['candidate']}.yaml")

    n_conf = max(40, replications_needed(best["d_measure1_sd"], CONFIRM_TARGET_HW_S, alpha=ALPHA))
    b = run_replications(base_cfg, n_conf, seed=args.seed, start=CONFIRM_START)
    c = run_replications(best_cfg, n_conf, seed=args.seed, start=CONFIRM_START)
    alpha2 = bonferroni_alpha(ALPHA, 2)
    c1 = paired_t(c["measure1_s"], b["measure1_s"], alpha=alpha2)
    c2 = paired_t(c["measure2"], b["measure2"], alpha=alpha2)
    c2_alt = paired_t(c["measure2_system_empty"], b["measure2_system_empty"], alpha=alpha2)
    pd.concat([b.assign(candidate="base"), c.assign(candidate=best["candidate"])], ignore_index=True).to_csv(
        OUT / "confirmation_replications.csv", index=False
    )
    result = {
        "screened": k,
        "screening_replications": args.reps,
        "alpha_familywise": ALPHA,
        "alpha_per_test_screening": alpha_k,
        "eligible": eligible["candidate"].tolist(),
        "selected": best["candidate"],
        "description": best["description"],
        "cost": {"base": base_cost, "selected": float(best["cost"]), "change": float(best["cost_change"])},
        "confirmation": {
            "replication_indices": [CONFIRM_START, CONFIRM_START + n_conf - 1],
            "replications": n_conf,
            "alpha_per_test": alpha2,
            "base_measure1_s": float(b["measure1_s"].mean()),
            "selected_measure1_s": float(c["measure1_s"].mean()),
            "measure1": c1.as_dict(),
            "relative_change_measure1": c1.mean_diff / float(b["measure1_s"].mean()),
            "base_measure2": float(b["measure2"].mean()),
            "selected_measure2": float(c["measure2"].mean()),
            "measure2": c2.as_dict(),
            "measure2_system_empty": c2_alt.as_dict(),
            "crn_var_ratio_measure1": crn_variance_reduction(c["measure1_s"], b["measure1_s"]),
            "base_wait_cashier_s": float(b["wait_cashier_mean_s"].mean()),
            "selected_wait_cashier_s": float(c["wait_cashier_mean_s"].mean()),
            "base_stockout_wait_per_customer_s": float(b["stockout_wait_per_customer_s"].mean()),
            "selected_stockout_wait_per_customer_s": float(c["stockout_wait_per_customer_s"].mean()),
        },
    }
    write_json(OUT / "confirmation.json", result)
    cols = ["candidate", "cost", "d_measure1_s", "d_measure1_ci_low", "d_measure1_ci_high", "p_measure1"]
    cols += ["d_measure2", "p_measure2", "eligible"]
    print(screening[cols].round(4).to_string(index=False))
    print(
        f"selected {best['candidate']}: confirmation n={n_conf}, d_measure1 = {c1.mean_diff:+.2f} s"
        f" [{c1.ci_low:+.2f}, {c1.ci_high:+.2f}] p={c1.p_value:.2g}; d_measure2 = {c2.mean_diff:+.2f}"
        f" [{c2.ci_low:+.2f}, {c2.ci_high:+.2f}] p={c2.p_value:.2g}"
    )


if __name__ == "__main__":
    main()
