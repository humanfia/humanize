"""What was kept before an `@` was a provider's alone, read back as `-e` spells one now.

Settings and the record of a run both hold environments as `-e` spelled them. Those kept the
old way -- `local@/x`, `docker@local/x`, an ssh host nobody saved out of brackets -- are read as
they are spelled now, once; those kept since say so, and are read as they were written whatever
has become of the runtimes they name since.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import yaml

from hmz import home
from hmz.coganchor.machines import store
from hmz.coganchor.machines.store import SPELLING, SSHRuntime
from hmz.runtime.epic import JOURNAL, Epic, read
from hmz.runtime.settings import Settings

if TYPE_CHECKING:
    from pathlib import Path


def test_a_run_recorded_the_old_way_is_read_back_as_e_spells_it_now(
    tmp_path: Path,
) -> None:
    epic = tmp_path / "epic"
    epic.mkdir()
    began = {
        "event": "began",
        "flow": "f",
        "task": "t",
        "envs": ["a=local@/x", "b=ssh@me@box/y", "c=docker@local/z"],
        "used": ["a=local@/x", "b=ssh@me@box/y", "c=docker@local/w"],
    }
    (epic / JOURNAL).write_text(json.dumps(began) + "\n")

    ran = read(epic)

    assert ran is not None
    assert ran.envs == ("a=local/x", "b=ssh@[me@box]/y", "c=docker/z")
    assert ran.used == ("a=local/x", "b=ssh@[me@box]/y", "c=docker/w")


def test_a_run_recorded_since_is_read_back_as_it_was_whatever_became_of_its_runtime(
    tmp_path: Path,
) -> None:
    """`ssh@gpu` named the runtime `gpu`, which taking it away does not make a host."""
    store.add(SSHRuntime(name="gpu", host="10.0.0.2"))
    with Epic("f", "t", tmp_path, envs=["box=ssh@gpu/srv"]) as epic:
        pass
    store.remove("ssh", "gpu")

    ran = read(epic.path)

    assert ran is not None
    assert ran.envs == ("box=ssh@gpu/srv",)


def test_settings_written_since_are_read_as_they_were_and_say_so(
    tmp_path: Path,
) -> None:
    store.add(SSHRuntime(name="gpu", host="10.0.0.2"))
    Settings(tmp_path).remember("f", {}, envs={"box": "ssh@gpu/srv"})
    store.remove("ssh", "gpu")

    assert Settings(tmp_path).envs("f") == {"box": "ssh@gpu/srv"}
    file = home() / "settings.yaml"
    assert yaml.safe_load(file.read_text())["spelling"] == SPELLING
