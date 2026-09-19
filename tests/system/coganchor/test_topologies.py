"""The three places a harness can run, each of them on real machines that are really apart.

Containers, because the questions here cannot be answered by anything standing in for one.
Whether a harness put beside its work reads that machine's disk, whether two machines with no
route between them are introduced anyway, whether the introduction falls back to humanize
carrying the bytes when it cannot be made, and whether a hostname read inside a turn is the
hostname of the machine the flow chose: every one of those is a fact about two kernels and
the network between them.

Docker is what supplies the network. Containers on one bridge can reach each other and are
where the punching is expected to work; containers on two bridges docker keeps apart cannot,
by the isolation rules the daemon writes itself, and are where the relay is expected to be
reached for. Both are checked against the broker's own count of what it had to carry, which
is the only honest witness: neither end of a connection can say whether it is being relayed.

That means a docker daemon, a pulled `python:3.12-slim` and a user who may talk to the socket,
which CI is not given. No agent runs and no token is spent: what these drive is `/bin/sh`.
"""

from __future__ import annotations

import concurrent.futures
import os
import subprocess
import uuid
from typing import TYPE_CHECKING

import pytest

from hmz.coganchor import AnchorConfig, connect
from hmz.coganchor import rendezvous as rv
from tests.machines.fixtures import IMAGE

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path

#: How many pairs of containers the parallel run puts up at once. Two apiece, so this is that
#: many harnesses supervising that many turns on that many other machines, all introduced
#: through one broker -- which is the shape a run driving a fleet of agents actually has.
PAIRS = 6

#: What a container is labelled with, so that a run killed outright leaves something anybody
#: can sweep up by name rather than a dozen containers nothing connects to this.
LABEL = "humanize-topologies"


def docker(*argv: str) -> str:
    """One docker command, with what it said, for a test that needs it to have worked."""
    done = subprocess.run(
        ["docker", *argv], capture_output=True, text=True, check=False
    )
    assert done.returncode == 0, f"docker {' '.join(argv)}: {done.stderr.strip()}"
    return done.stdout.strip()


class Lab:
    """The containers one test runs against, and the networks they are reachable on."""

    def __init__(self, workspace: Path) -> None:
        """Initializes a lab holding nothing yet.

        Args:
          workspace: The directory every container mounts, which is where the work lands and
            where this machine reads it back from afterwards.
        """
        self.workspace = workspace
        self._made: list[str] = []
        self._networks: list[str] = []

    def network(self) -> str:
        """A bridge of its own. Two of them are two networks docker will not route between."""
        name = f"hmz-{uuid.uuid4().hex[:10]}"
        docker("network", "create", name)
        self._networks.append(name)
        return name

    def machine(self, network: str | None = None) -> str:
        """One container, idling, holding the workspace at the path it has here.

        Args:
          network: Which bridge to put it on, or None for the default one.

        Returns:
          Its name, which is what a `docker://` target is spelled with.
        """
        name = f"hmz-{uuid.uuid4().hex[:10]}"
        docker(
            "run",
            "--detach",
            "--name",
            name,
            "--label",
            f"{LABEL}={os.getuid()}",
            # Named to itself as well as to docker, so that what a turn reads from `hostname`
            # is the name this test knows the machine by rather than the container id.
            "--hostname",
            name,
            *(["--network", network] if network else []),
            "--volume",
            f"{self.workspace}:{self.workspace}",
            "--workdir",
            str(self.workspace),
            IMAGE,
            "sleep",
            "infinity",
        )
        self._made.append(name)
        return name

    def close(self) -> None:
        """Takes down everything this lab put up, whatever became of the test."""
        for name in self._made:
            subprocess.run(
                ["docker", "rm", "--force", name], capture_output=True, check=False
            )
        for network in self._networks:
            subprocess.run(
                ["docker", "network", "rm", network], capture_output=True, check=False
            )


@pytest.fixture
def lab(daemon: None, tmp_path: Path) -> Iterator[Lab]:
    """A lab whose containers all mount one workspace, taken down at the end."""
    (tmp_path / "seed.txt").write_text("only in the workspace\n")
    made = Lab(tmp_path)
    try:
        yield made
    finally:
        made.close()


@pytest.fixture
def broker() -> rv.Broker:
    """The broker this process holds, which is the one a session with no other is given.

    The shared one rather than a fresh one, because the shared one is what
    `hmz.coganchor.elsewhere` books meetings at and the count of what it carried is the whole
    of what these tests read off it. Not torn down: it outlives every test here the way it
    outlives every session in a run, which is what makes one of it enough.
    """
    made, _, _ = rv.shared()
    return made


def ran(config: AnchorConfig, script: str) -> int:
    """Runs one shell line under an anchor and answers with its status."""
    return connect(["/bin/sh", "-c", script], config)


def test_a_harness_beside_its_work_runs_the_turn_on_that_machine(lab: Lab) -> None:
    """Both halves on the container, and this machine holding neither of them.

    The hostname proves where the turn ran and the file proves the work landed in the
    workspace rather than in a copy of it: the directory is mounted, so what the turn wrote
    is readable here the moment it exits.
    """
    box = lab.machine()
    config = AnchorConfig(
        harness="same", target=f"docker://{box}", workspace=str(lab.workspace)
    )

    status = ran(config, "hostname > where.txt; cat seed.txt > read-back.txt")

    assert status == 0
    assert (lab.workspace / "where.txt").read_text().strip() == box
    assert (lab.workspace / "read-back.txt").read_text() == "only in the workspace\n"


def test_two_machines_that_can_reach_each_other_are_introduced(
    lab: Lab, broker: rv.Broker
) -> None:
    """The harness on one container, its work on another, and humanize out of the path.

    Both are on one bridge, so the two ends can open holes at each other and the broker has
    nothing left to do once it has said where each of them is. Its own count is what says so.
    """
    network = lab.network()
    harness, work = lab.machine(network), lab.machine(network)
    carried = broker.carried
    config = AnchorConfig(
        harness=f"docker://{harness}",
        target=f"docker://{work}",
        workspace=str(lab.workspace),
    )

    status = ran(config, "hostname > where.txt")

    assert status == 0
    # The turn runs where the *work* is, the harness being the thing that supervises it.
    assert (lab.workspace / "where.txt").read_text().strip() == work
    assert broker.carried == carried, "a session that could be introduced was carried"


def test_two_machines_that_cannot_are_carried_by_humanize(
    lab: Lab, broker: rv.Broker
) -> None:
    """Two bridges docker keeps apart, which is a pair with no route between them at all.

    The punching window closes with nothing through it, both halves say so, and the two
    connections they are already holding to the broker are spliced. The session is the same
    session -- same status, same file, same everything -- which is the point.
    """
    harness = lab.machine(lab.network())
    work = lab.machine(lab.network())
    carried = broker.carried
    config = AnchorConfig(
        harness=f"docker://{harness}",
        target=f"docker://{work}",
        workspace=str(lab.workspace),
    )

    status = ran(config, "hostname > where.txt; cat seed.txt > read-back.txt")

    assert status == 0
    assert (lab.workspace / "where.txt").read_text().strip() == work
    assert (lab.workspace / "read-back.txt").read_text() == "only in the workspace\n"
    assert broker.carried == carried + 1, "a session with no route was not carried"


def test_a_turn_that_failed_elsewhere_fails_here_with_its_own_status(lab: Lab) -> None:
    """A harness on another machine is a pipe, and a pipe does not improve on what it carries."""
    box = lab.machine()
    config = AnchorConfig(
        harness="same", target=f"docker://{box}", workspace=str(lab.workspace)
    )

    assert ran(config, "exit 42") == 42


def test_many_harnesses_on_many_machines_run_at_once(
    lab: Lab, broker: rv.Broker
) -> None:
    """One broker, one archive, and a pair of containers per turn, all of it concurrently.

    Which is the shape a run driving a fleet has, and the one that would find what a single
    session cannot: a meeting that paired the wrong two halves, a bundle pushed twice to the
    same machine at once, a broker thread holding a lock across a splice. Every turn writes a
    file named for itself, so a session that was introduced to somebody else's half is a file
    with the wrong name in it.
    """
    network = lab.network()
    pairs = [(lab.machine(network), lab.machine(network)) for _ in range(PAIRS)]
    carried = broker.carried

    def turn(which: int, harness: str, work: str) -> int:
        return ran(
            AnchorConfig(
                harness=f"docker://{harness}",
                target=f"docker://{work}",
                workspace=str(lab.workspace),
            ),
            f"hostname > turn-{which}.txt",
        )

    with concurrent.futures.ThreadPoolExecutor(max_workers=PAIRS) as running:
        waiting = [
            running.submit(turn, which, harness, work)
            for which, (harness, work) in enumerate(pairs)
        ]
        statuses = [each.result() for each in waiting]

    assert statuses == [0] * PAIRS
    for which, (_, work) in enumerate(pairs):
        assert (lab.workspace / f"turn-{which}.txt").read_text().strip() == work, (
            "a turn landed on the machine another turn was introduced to"
        )
    assert broker.carried == carried, "a session on one bridge was carried"


def test_the_second_turn_against_a_workspace_finds_its_mirror_warm(lab: Lab) -> None:
    """The mirror is named for what it mirrors, so it is there the next time and holds files.

    Read off the container rather than off a timer: what makes the second turn cheaper is
    that the directory survived, and a stopwatch on a machine running six other tests would
    say nothing either way.
    """
    box = lab.machine()
    config = AnchorConfig(
        harness="same", target=f"docker://{box}", workspace=str(lab.workspace)
    )

    assert ran(config, "cat seed.txt > first.txt") == 0
    mirrors = docker(
        "exec",
        box,
        "/bin/sh",
        "-c",
        "ls -d /tmp/humanize-mirrors/* 2>/dev/null | wc -l",
    )
    assert ran(config, "cat seed.txt > second.txt") == 0

    assert mirrors == "1", "the harness did not keep a mirror of its own"
    assert (
        docker(
            "exec",
            box,
            "/bin/sh",
            "-c",
            "ls -d /tmp/humanize-mirrors/* 2>/dev/null | wc -l",
        )
        == "1"
    ), "the second turn made a mirror of its own instead of finding the first one"
    assert (lab.workspace / "second.txt").read_text() == "only in the workspace\n"
