"""Independent replications with common random numbers, run in parallel processes.

Replication r of any configuration uses streams seeded from (seed, r), so configuration X and Y
evaluated on the same replication indices are paired (CRN). Fresh, independent replications for
a confirmation run are obtained by using a different block of replication indices.
"""

from __future__ import annotations

import os
import time
from concurrent.futures import ProcessPoolExecutor

import pandas as pd

from cafesim.model import simulate

DEFAULT_SEED = 20231128
MAX_WORKERS = 4


def run_replication(cfg: dict, replication: int, seed: int = DEFAULT_SEED, trace: bool = False) -> dict:
    t0 = time.perf_counter()
    out = simulate(cfg, seed=seed, replication=replication, trace=trace)
    out["replication"] = replication
    out["seed"] = seed
    out["config"] = cfg.get("name", "")
    out["wall_s"] = time.perf_counter() - t0
    return out


def _job(args):
    cfg, rep, seed, trace = args
    return run_replication(cfg, rep, seed, trace)


def run_replications(
    cfg: dict,
    n: int,
    seed: int = DEFAULT_SEED,
    start: int = 0,
    workers: int | None = None,
    trace: bool = False,
) -> pd.DataFrame | tuple[pd.DataFrame, list[dict]]:
    """Run replications ``start .. start+n-1``. Returns a DataFrame (and the traces if ``trace``)."""
    workers = min(workers or MAX_WORKERS, MAX_WORKERS, os.cpu_count() or 1)
    jobs = [(cfg, r, seed, trace) for r in range(start, start + n)]
    if workers <= 1 or n == 1:
        results = [_job(j) for j in jobs]
    else:
        with ProcessPoolExecutor(max_workers=workers) as pool:
            results = list(pool.map(_job, jobs))
    traces = [r.pop("trace") for r in results] if trace else None
    df = pd.DataFrame(results).sort_values("replication").reset_index(drop=True)
    return (df, traces) if trace else df
