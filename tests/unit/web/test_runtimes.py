"""`hmz.web.runtimes`: what a page is handed of the runtimes there are, and of a new one."""

from __future__ import annotations

from functools import partial
from types import SimpleNamespace
from typing import Any

from hmz.web.runtimes import listed


def _hmz(*held: dict[str, Any]) -> Any:
    """A stand-in for humanize's one object, whose runtimes are written down as `held`."""
    saved = [SimpleNamespace(held=partial(dict[str, Any], one)) for one in held]
    return SimpleNamespace(runtimes=SimpleNamespace(all=lambda: saved))


def test_every_runtime_is_listed_as_it_is_written_down() -> None:
    cluster = {"backend": "slurm", "name": "gpu", "partition": "gpu", "made": "typed"}

    assert listed(_hmz(cluster))["runtimes"] == [cluster]


def test_a_new_slurm_cluster_is_made_of_its_fields_with_nothing_said() -> None:
    blanks = listed(_hmz())["blanks"]

    assert set(blanks) == {"ssh", "docker", "swarm", "apple-container", "slurm"}
    assert blanks["slurm"] == {
        "partition": "",
        "account": "",
        "qos": "",
        "time": "",
        "constraint": "",
        "python": "",
        "via": "srun",
        "run_args": [],
        "cpus": 0.0,
        "memory": 0,
        "max_jobs": 0,
        "max_wait": 0,
        "workdir": "",
        "fallback": [],
        "harness": "env",
    }
