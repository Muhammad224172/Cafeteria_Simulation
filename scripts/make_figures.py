"""Figures for the README, written to results/figures/. Run after the other scripts."""

from __future__ import annotations

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import yaml  # noqa: E402
from _common import RESULTS, ROOT, read_json  # noqa: E402

FIG = RESULTS / "figures"
SURFACE = "#fcfcfb"
INK = "#0b0b0b"
INK2 = "#52514e"
MUTED = "#898781"
GRID = "#e1e0d9"
BLUE, ORANGE, AQUA = "#2a78d6", "#eb6834", "#1baf7a"
GRAY = "#b5b3ab"

plt.rcParams.update(
    {
        "figure.facecolor": SURFACE,
        "axes.facecolor": SURFACE,
        "savefig.facecolor": SURFACE,
        "axes.edgecolor": GRID,
        "axes.labelcolor": INK2,
        "axes.titlecolor": INK,
        "axes.titlesize": 11,
        "axes.titleweight": "bold",
        "axes.titlelocation": "left",
        "axes.labelsize": 9,
        "xtick.color": MUTED,
        "ytick.color": MUTED,
        "xtick.labelsize": 8,
        "ytick.labelsize": 8,
        "axes.grid": True,
        "grid.color": GRID,
        "grid.linewidth": 0.8,
        "axes.spines.top": False,
        "axes.spines.right": False,
        "font.size": 9,
        "legend.frameon": False,
        "legend.fontsize": 8,
    }
)


def clock_ticks(ax, max_s: float) -> None:
    ticks = np.arange(1800, max_s + 1, 3600)  # 12:00, 13:00, ...
    ax.set_xticks(ticks)
    ax.set_xticklabels([f"{12 + i}:00" for i in range(len(ticks))])


def day_profile() -> None:
    prof = pd.read_csv(RESULTS / "baseline" / "profile.csv")
    t = prof["time_s"].to_numpy()
    fig, ax = plt.subplots(figsize=(7.2, 3.4))
    series = [
        ("waiting_for_table_mean", "Waiting for a table", ORANGE),
        ("seated_mean", "Seated (144 seats)", BLUE),
        ("in_lines_mean", "In the serving lines", AQUA),
    ]
    for key, label, color in series:
        y = prof[key].to_numpy()
        ax.plot(t, y, color=color, lw=2, solid_capstyle="round", label=label)
    ax.axvline(30600, color=MUTED, lw=1)
    ax.text(30600 + 300, ax.get_ylim()[1] * 0.95, "last arrival 20:00", color=INK2, fontsize=8, va="top")
    ax.set_ylabel("customers (mean of 20 days)")
    ax.set_ylim(bottom=0)
    clock_ticks(ax, t.max())
    ax.set_title("The dining area, not the serving lines, holds the queue")
    ax.legend(loc="upper right", bbox_to_anchor=(1.0, 0.88))
    fig.tight_layout()
    fig.savefig(FIG / "day_profile.png", dpi=160)
    plt.close(fig)


def measure1_by_time() -> None:
    df = pd.read_csv(RESULTS / "baseline" / "measure1_by_halfhour.csv")
    x = df["bin_start_s"] + 900
    fig, ax = plt.subplots(figsize=(7.2, 3.0))
    ax.errorbar(x, df["mean_s"], yerr=df["half_width_s"], fmt="none", ecolor=BLUE, elinewidth=1.2, capsize=0)
    ax.plot(x, df["mean_s"], color=BLUE, lw=2)
    ax.scatter(x, df["mean_s"], s=28, color=BLUE, edgecolor=SURFACE, linewidth=1.5, zorder=3)
    ax.set_ylabel("arrival to end of payment (s)")
    ax.set_ylim(bottom=0)
    clock_ticks(ax, 30600)
    ax.set_title("Measure 1 by arrival half-hour (base, 20 days, 95% CI)")
    fig.tight_layout()
    fig.savefig(FIG / "measure1_by_arrival_time.png", dpi=160)
    plt.close(fig)


def alternatives() -> None:
    s = pd.read_csv(RESULTS / "alternatives" / "screening.csv")
    conf = read_json(RESULTS / "alternatives" / "confirmation.json")
    s = s.iloc[::-1].reset_index(drop=True)
    fig, ax = plt.subplots(figsize=(8.0, 4.8))
    y = np.arange(len(s))
    for i, r in s.iterrows():
        color = BLUE if r["eligible"] else GRAY
        ax.plot([r["d_measure1_ci_low"], r["d_measure1_ci_high"]], [i, i], color=color, lw=2, solid_capstyle="round")
        ax.scatter([r["d_measure1_s"]], [i], s=40, color=color, edgecolor=SURFACE, linewidth=1.5, zorder=3)
    ax.axvline(0, color=INK2, lw=1)
    labels = [f"{c}  ({d:+.1f})" for c, d in zip(s["candidate"], s["cost_change"], strict=True)]
    ax.set_yticks(y)
    ax.set_yticklabels(labels, fontsize=8, color=INK2)
    ax.grid(axis="y", visible=False)
    c1 = conf["confirmation"]["measure1"]
    sel = list(s["candidate"]).index(conf["selected"])
    hi = s.loc[sel, "d_measure1_ci_high"]
    ax.text(hi + 0.3, sel, f"selected; on {c1['n']} fresh days: {c1['mean_diff']:+.2f} s", color=INK, fontsize=8,
            va="center")  # fmt: skip
    ax.set_xlim(-9, 4.5)
    ax.set_xlabel("change in measure 1 vs base (s); paired over 20 CRN days; Bonferroni 95% CIs (k = 11)")
    ax.set_title("Equal-or-cheaper alternatives (daily cost change in brackets)")
    ax.scatter([], [], color=BLUE, s=30, label="eligible: significant gain, measure 2 not worse")
    ax.scatter([], [], color=GRAY, s=30, label="not eligible")
    ax.legend(loc="upper center", bbox_to_anchor=(0.4, -0.13), ncol=2)
    fig.tight_layout()
    fig.savefig(FIG / "alternatives_screening.png", dpi=160)
    plt.close(fig)


def halfwidths() -> None:
    hw = pd.read_csv(RESULTS / "replications_halfwidths.csv")["half_width_s"]
    rep = read_json(RESULTS / "replications.json")
    fig, ax = plt.subplots(figsize=(7.2, 2.8))
    bins = np.arange(0, hw.max() + 1, 1.0)
    ax.hist(hw, bins=bins, color=BLUE, edgecolor=SURFACE, linewidth=2)
    ax.axvline(10, color=INK2, lw=1)
    share = rep["verification_repeated"]["share_half_width_le_target"]
    ax.text(10.3, ax.get_ylim()[1] * 0.9, f"target 10 s\n{share:.1%} of runs meet it", color=INK2, fontsize=8, va="top")
    ax.set_xlabel("95% half-width of measure 1 (s)")
    ax.set_ylabel("experiments")
    n = rep["n_used"]
    ax.set_title(f"Half-widths from {rep['verification_repeated']['experiments']} experiments of {n} replications")
    ax.grid(axis="x", visible=False)
    fig.tight_layout()
    fig.savefig(FIG / "replication_halfwidths.png", dpi=160)
    plt.close(fig)


def validation() -> None:
    v = read_json(RESULTS / "validation.json")["instructor_solution_base"]
    ref = yaml.safe_load((ROOT / "validation" / "arena_reference.yaml").read_text(encoding="utf-8"))[
        "instructor_solution_base"
    ]
    rows = [
        ("Arena (instructor model)", ref["measure1_s"]["mean"], ref["measure1_s"]["half_width_95"],
         ref["measure2"]["mean"], ref["measure2"]["half_width_95"], INK2),
        ("This model, instructor reading", v["s02_instructor_interpretation"]["measure1_s"]["mean"],
         v["s02_instructor_interpretation"]["measure1_s"]["half_width"],
         v["s02_instructor_interpretation"]["measure2_system_empty"]["mean"],
         v["s02_instructor_interpretation"]["measure2_system_empty"]["half_width"], BLUE),
        ("This model, problem reading", v["base"]["measure1_s"]["mean"], v["base"]["measure1_s"]["half_width"],
         v["base"]["measure2_system_empty"]["mean"], v["base"]["measure2_system_empty"]["half_width"], ORANGE),
    ]  # fmt: skip
    fig, axes = plt.subplots(1, 2, figsize=(7.2, 2.4), sharey=True)
    y = np.arange(len(rows))[::-1]
    for ax, (mi, hi, title) in zip(axes, ((1, 2, "Measure 1 (s)"), (3, 4, "Measure 2 (customers)")), strict=True):
        for yy, r in zip(y, rows, strict=True):
            ax.plot([r[mi] - r[hi], r[mi] + r[hi]], [yy, yy], color=r[5], lw=2, solid_capstyle="round")
            ax.scatter([r[mi]], [yy], s=40, color=r[5], edgecolor=SURFACE, linewidth=1.5, zorder=3)
        ax.set_title(title, fontsize=10)
        ax.grid(axis="y", visible=False)
    axes[0].set_yticks(y)
    axes[0].set_yticklabels([r[0] for r in rows], color=INK2)
    fig.suptitle("Validation: 20-day means with 95% CIs (measure 2 until the last diner leaves)", x=0.01, ha="left",
                 fontsize=10, fontweight="bold", color=INK)  # fmt: skip
    fig.tight_layout()
    fig.savefig(FIG / "validation.png", dpi=160)
    plt.close(fig)


def main() -> None:
    FIG.mkdir(parents=True, exist_ok=True)
    day_profile()
    measure1_by_time()
    alternatives()
    halfwidths()
    validation()
    print(f"figures written to {FIG}")


if __name__ == "__main__":
    main()
