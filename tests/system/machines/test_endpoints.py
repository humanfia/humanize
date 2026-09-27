"""A container on every kind of daemon endpoint, and the road to it that the turns take.

The same daemon each time -- this machine's -- reached five ways: docker's default, its socket
spelled out, a TCP port forwarded to that socket, docker's own ssh transport through an sshd of
the test's own, and a context kept in a configuration of the test's own. What is checked is
that each of them is a whole road: the container starts there, the target it is reached by
carries the endpoint, the flow's own reads, writes and commands land inside the container
through `docker exec` with no sshd in the image, and the container is gone when it is stopped.

And that nothing strays off it. Every explicit endpoint is exercised with `DOCKER_HOST` pointed
at a port nothing listens on, so a `docker` anywhere on the road that was not told where to go
fails the test rather than quietly reaching the default.

Needs a docker daemon holding `python:3.12-slim`; the ssh one also needs an `sshd` to start.
"""

from __future__ import annotations

import json
import os
import socket
import subprocess
from typing import TYPE_CHECKING, Any

import pytest

from hmz.coganchor.machines import DockerConfig, Mapped, allocations
from hmz.coganchor.transport import Endpoint, Target
from tests.machines.fixtures import IMAGE, socket_of_the_daemon

if TYPE_CHECKING:
    from pathlib import Path

#: The five ways in, as the fixture below makes each of them.
_KINDS = ("local", "unix", "tcp", "ssh", "context")


@pytest.fixture(params=_KINDS)
def endpoint(
    request: pytest.FixtureRequest, daemon: None, monkeypatch: pytest.MonkeyPatch
) -> str:
    """One way of reaching this machine's daemon, spelled as a setting spells it."""
    kind: str = request.param
    if kind == "local":
        return "local"
    spelled = {
        "unix": socket_of_the_daemon,
        "tcp": lambda: str(request.getfixturevalue("forwarded")),
        "ssh": lambda: str(request.getfixturevalue("sshd")),
        "context": lambda: str(request.getfixturevalue("context")),
    }[kind]()
    # Somewhere nothing answers: a command that was not told its endpoint goes here, and fails.
    monkeypatch.setenv("DOCKER_HOST", "tcp://127.0.0.1:9")
    return spelled


def _inspect(endpoint: str, container: str) -> dict[str, Any] | None:
    """What the daemon at `endpoint` says of one container, or None for no such container."""
    said = subprocess.run(
        Endpoint.parse(endpoint).docker("inspect", container),
        capture_output=True,
        text=True,
        check=False,
    )
    return json.loads(said.stdout)[0] if said.returncode == 0 else None


@pytest.mark.timeout(240)
def test_the_whole_road_to_a_container_goes_through_its_endpoint(
    endpoint: str, tmp_path: Path
) -> None:
    (tmp_path / "here.txt").write_text("written here\n")
    machine = DockerConfig(
        image=IMAGE,
        workspace=str(tmp_path),
        endpoint=endpoint,
        labels={"humanize.test": "endpoints"},
    ).create()

    anchor = machine.start()
    target = Target.parse(anchor.target)
    try:
        # The target carries the daemon, and names none at all for the default.
        assert str(target.endpoint) == str(Endpoint.parse(endpoint))
        assert anchor.target.endswith(f"@{endpoint}") == (endpoint != "local")

        with Mapped(anchor) as held:
            assert held.read_text("here.txt") == "written here\n"
            held.write_text("there.txt", "written from the flow\n")
            inside = held.run(
                ["/bin/sh", "-c", "test -f /.dockerenv && echo contained; hostname"]
            )
            assert inside.ok, inside.output
            said, hostname = inside.output.split()
            assert said == "contained"
            assert hostname != socket.gethostname()
            # No sshd in the image, and none needed: the command came in over `docker exec`.
            assert not held.run(["/bin/sh", "-c", "command -v sshd"]).ok

        found = _inspect(endpoint, target.host)
        assert found is not None
        assert found["Config"]["User"] == f"{os.getuid()}:{os.getgid()}"
        assert found["Config"]["Labels"]["humanize"] == str(os.getuid())
        assert found["Config"]["Labels"]["humanize.test"] == "endpoints"
        assert [one.name for one in allocations(endpoint)].count(target.host) == 1
    finally:
        machine.stop()

    assert (tmp_path / "there.txt").read_text() == "written from the flow\n"
    assert _inspect(endpoint, target.host) is None  # and it goes when it is stopped


@pytest.mark.timeout(120)
def test_a_workspace_a_daemon_elsewhere_has_not_got_is_refused_and_not_made(
    forwarded: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Asked of the daemon's own host, and never mounted into being there."""
    monkeypatch.setenv("DOCKER_HOST", "tcp://127.0.0.1:9")
    missing = tmp_path / "not-here"
    name = f"hmz-missing-{tmp_path.name}"

    with pytest.raises(FileNotFoundError, match="no directory"):
        DockerConfig(
            image=IMAGE, workspace=str(missing), endpoint=forwarded, name=name
        ).create().start()

    assert not missing.exists()
    assert _inspect(forwarded, name) is None
