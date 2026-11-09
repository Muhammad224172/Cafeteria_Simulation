"""cafesim: a discrete-event simulation of a university cafeteria (IE 305 term project, reimplemented in SimPy)."""

from cafesim.config import load_config
from cafesim.experiment import run_replication, run_replications

__all__ = ["load_config", "run_replication", "run_replications"]
__version__ = "0.1.0"
