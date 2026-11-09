"""Configuration loading.

A config file is YAML. It may name a parent with ``extends: <path relative to this file>``;
the child is deep-merged over the parent (dicts merge key by key, everything else is replaced).
"""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

import yaml

OPEN_CLOCK = "11:30"


def clock_to_seconds(clock: str, open_clock: str = OPEN_CLOCK) -> float:
    """Convert "HH:MM" to seconds after opening time."""
    h, m = (int(x) for x in clock.split(":"))
    oh, om = (int(x) for x in open_clock.split(":"))
    return float((h * 60 + m - (oh * 60 + om)) * 60)


def deep_merge(base: dict, override: dict) -> dict:
    out = copy.deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = deep_merge(out[key], value)
        else:
            out[key] = copy.deepcopy(value)
    return out


def load_config(path: str | Path) -> dict[str, Any]:
    path = Path(path)
    with open(path, encoding="utf-8") as fh:
        raw = yaml.safe_load(fh) or {}
    parent = raw.pop("extends", None)
    if parent is not None:
        base = load_config(path.parent / parent)
        raw = deep_merge(base, raw)
    validate_config(raw)
    return raw


def with_overrides(cfg: dict, **sections: dict) -> dict:
    """Return a copy of ``cfg`` with whole-section overrides merged in (handy in tests)."""
    return deep_merge(cfg, sections)


def validate_config(cfg: dict) -> None:
    mix = cfg["routing"]["meal_mix"]
    if abs(sum(mix.values()) - 1.0) > 1e-9:
        raise ValueError(f"meal_mix must sum to 1, got {sum(mix.values())}")
    sched = cfg["workers"]["schedule"]
    n = len(sched["breakpoints"])
    for area in ("AB", "CD"):
        for level in ("experienced", "inexperienced"):
            counts = sched[area][level]
            if len(counts) != n:
                raise ValueError(f"schedule {area}/{level} has {len(counts)} entries, expected {n}")
            if any(c < 0 for c in counts):
                raise ValueError("negative worker count")
    for closure in cfg["lines"].get("closures", []):
        if closure["line"] not in ("B", "D"):
            raise ValueError("only line B or D can be closed (A and C serve vegan and salad customers)")
    closures = cfg["lines"].get("closures", [])
    for a in closures:
        for b in closures:
            if a is not b and a["line"] != b["line"]:
                lo = max(clock_to_seconds(a["start"]), clock_to_seconds(b["start"]))
                hi = min(clock_to_seconds(a["end"]), clock_to_seconds(b["end"]))
                if lo < hi:
                    raise ValueError("lines B and D cannot both be closed at the same time")
