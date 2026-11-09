"""Command-line interface.

cafesim run configs/base.yaml --reps 20
cafesim compare configs/base.yaml configs/alternatives/a07_cashier2_BCD_peak.yaml --reps 40
cafesim cost configs/base.yaml
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from cafesim.analysis import paired_t, t_ci
from cafesim.config import load_config
from cafesim.costs import daily_cost
from cafesim.experiment import DEFAULT_SEED, run_replications


def _summarise(df) -> str:
    m1 = t_ci(df["measure1_s"])
    m2 = t_ci(df["measure2"])
    lines = [
        f"replications           : {len(df)}",
        f"customers per day      : {df['n_customers'].mean():.0f}",
        f"measure 1 (s)          : {m1.mean:.2f} +/- {m1.half_width:.2f}  (95% t-CI, sd {m1.sd:.2f})",
        f"measure 2 (customers)  : {m2.mean:.1f} +/- {m2.half_width:.1f}  (95% t-CI, sd {m2.sd:.1f})",
        f"daily labour cost      : {df['cost_total'].iloc[0]:.2f} units",
        f"wall time / replication: {df['wall_s'].mean():.2f} s",
    ]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="cafesim", description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_run = sub.add_parser("run", help="run replications of one configuration")
    p_run.add_argument("config")
    p_run.add_argument("--reps", type=int, default=20)
    p_run.add_argument("--seed", type=int, default=DEFAULT_SEED)
    p_run.add_argument("--start", type=int, default=0, help="first replication index")
    p_run.add_argument("--workers", type=int, default=4)
    p_run.add_argument("--out", type=Path, help="write per-replication results to this CSV")

    p_cmp = sub.add_parser("compare", help="paired-t comparison of two configurations under CRN")
    p_cmp.add_argument("base")
    p_cmp.add_argument("candidate")
    p_cmp.add_argument("--reps", type=int, default=20)
    p_cmp.add_argument("--seed", type=int, default=DEFAULT_SEED)
    p_cmp.add_argument("--start", type=int, default=0)
    p_cmp.add_argument("--workers", type=int, default=4)

    p_cost = sub.add_parser("cost", help="daily labour cost of a configuration")
    p_cost.add_argument("config")

    args = parser.parse_args(argv)
    if args.cmd == "run":
        cfg = load_config(args.config)
        df = run_replications(cfg, args.reps, seed=args.seed, start=args.start, workers=args.workers)
        print(_summarise(df))
        if args.out:
            args.out.parent.mkdir(parents=True, exist_ok=True)
            df.to_csv(args.out, index=False)
    elif args.cmd == "compare":
        base = load_config(args.base)
        cand = load_config(args.candidate)
        kw = dict(seed=args.seed, start=args.start, workers=args.workers)
        a = run_replications(base, args.reps, **kw)
        b = run_replications(cand, args.reps, **kw)
        print(f"cost: base {daily_cost(base)['total']:.2f}, candidate {daily_cost(cand)['total']:.2f}")
        for col, label in (("measure1_s", "measure 1 (s)"), ("measure2", "measure 2")):
            r = paired_t(b[col], a[col])
            print(
                f"{label:15s} candidate - base = {r.mean_diff:+.3f}  95% CI [{r.ci_low:+.3f}, {r.ci_high:+.3f}]"
                f"  p = {r.p_value:.2g}"
            )
    elif args.cmd == "cost":
        for k, v in daily_cost(load_config(args.config)).items():
            print(f"{k:15s} {v:8.2f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
