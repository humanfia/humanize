"""A tool as one more frontend of a workspace's runs, reached through the SDK.

What is checked is that the SDK hands through the classes humanize itself holds -- the host of
the runtime and the link of the daemon -- rather than copies of them, that naming one costs
only the layer it is written in, and that a tool can be a frontend both ways: of runs held in
its own process, and of runs a host is holding apart from it.
"""

from __future__ import annotations

import subprocess
import sys
from typing import TYPE_CHECKING

import pytest

import hmz.daemon
import hmz.runtime
from hmz.sdk import Daemons, Hmz, Host, Link

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path

    from hmz.daemon import Daemon


@pytest.fixture
def hosted(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Daemon]:
    where = tmp_path / "project"
    where.mkdir()
    monkeypatch.chdir(where)
    one = Daemons().host()
    try:
        yield one
    finally:
        if one.alive:
            one.kill()


def test_the_host_and_the_link_are_the_ones_humanize_holds() -> None:
    assert Host is hmz.runtime.Host
    assert Link is hmz.daemon.Link


def test_naming_the_link_costs_the_daemon_and_nothing_under_it() -> None:
    probe = (
        "import sys\n"
        "from hmz.sdk import Link\n"
        "print(' '.join(sorted(m for m in sys.modules if m.startswith('hmz.'))))\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", probe], capture_output=True, text=True, check=True
    )

    loaded = set(result.stdout.split())
    assert "hmz.daemon.link" in loaded
    assert not {one for one in loaded if one.startswith("hmz.runtime.")}


def test_a_tool_is_a_frontend_of_runs_held_in_its_own_process() -> None:
    from hmz.daemon import linked

    host = Hmz().host()
    try:
        with linked(host, "ci", "sdk") as link:
            assert isinstance(link, Link)
            assert link.claim("reviewer") == {"ok": True}
            said = next(iter(link))
            assert said["type"] == "welcome"
            assert said["name"] == "ci"
    finally:
        host.close()


@pytest.mark.timeout(60)
def test_a_tool_is_a_frontend_of_runs_a_host_is_holding(hosted: Daemon) -> None:
    with (Daemons().here() or Daemons().host()).link(name="ci", replay=False) as link:
        assert isinstance(link, Link)
        assert link.client
        link.claim("reviewer")
        claims = next(
            said["claims"]
            for said in link
            if said["type"] == "claims" and said["claims"]
        )
    assert claims == {"reviewer": link.client}
    assert Daemons().here() is not None
