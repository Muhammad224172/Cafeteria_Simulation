from pathlib import Path

import pytest

from cafesim.config import load_config

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="session")
def base_cfg():
    return load_config(ROOT / "configs" / "base.yaml")
