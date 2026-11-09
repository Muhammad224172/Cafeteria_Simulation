"""Shared paths for the scripts. Makes ``src/`` importable when the package is not installed."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

CONFIGS = ROOT / "configs"
RESULTS = ROOT / "results"
SEED = 20231128


def write_json(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(obj, fh, indent=2, default=float)
        fh.write("\n")


def read_json(path: Path):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)
