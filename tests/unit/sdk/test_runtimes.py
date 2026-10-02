"""The runtimes half of the SDK, which is the same store every other way in walks.

`Runtimes` is a facade: each method is one call into :mod:`hmz.coganchor.machines`. What is
worth checking about a facade is that it is wired to the right call, so these go through the
SDK and read back through the store, and the two have to agree. Asking a runtime what it has
starts `ssh` or `docker`, which is the integration and system tiers'.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

import hmz.sdk
from hmz.coganchor.machines import store
from hmz.sdk import Hmz, Runtimes

if TYPE_CHECKING:
    from pathlib import Path


def test_it_is_offered_where_the_other_stores_are() -> None:
    assert "Runtimes" in hmz.sdk.__all__
    assert isinstance(Hmz().runtimes, Runtimes)
    held = Hmz()
    assert held.runtimes is held.runtimes


def test_a_runtime_made_from_here_is_one_the_store_reads_back() -> None:
    envs = Hmz().runtimes

    made = envs.add(envs.new("ssh", "gpu", host="10.0.0.2", user="me", port=2222))
    box = envs.write(envs.new("docker", "box", endpoint="ssh:gpu", cpus=4))

    assert store.find("ssh", "gpu") == made
    assert store.find("docker", "box") == box
    assert envs.find("ssh", "gpu") == made
    assert envs.all() == [made, box]
    assert envs.all("docker") == [box]
    assert envs.where("ssh", "gpu") == made.at


def test_a_name_already_taken_is_refused_by_add_and_written_over_by_write() -> None:
    envs = Hmz().runtimes
    envs.add(envs.new("ssh", "gpu", host="a"))

    with pytest.raises(ValueError, match="already exists"):
        envs.add(envs.new("ssh", "gpu", host="b"))
    envs.write(envs.new("ssh", "gpu", host="b"))
    assert envs.find("ssh", "gpu") == envs.new("ssh", "gpu", host="b")
    assert envs.remove("ssh", "gpu")
    assert envs.find("ssh", "gpu") is None


def test_one_made_again_from_what_it_holds_is_itself() -> None:
    envs = Hmz().runtimes
    made = envs.new("docker", "box", gpus=["0"], run_args=["--rm"], memory=1 << 30)

    assert envs.new(**made.held()) == made


def test_importing_from_here_writes_what_the_store_would(tmp_path: Path) -> None:
    config = tmp_path / "config"
    config.write_text("Host gpu builder\n")

    written = Hmz().runtimes.import_ssh(config, ["builder"])

    assert [one.alias for one in written] == ["builder"]
    assert store.runtimes() == written
