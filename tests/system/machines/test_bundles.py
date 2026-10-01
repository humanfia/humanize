"""Two checkouts' bundles on one real container, and a copy there that is not what it says.

A target caches the archive under the digest of what is in it, so two checkouts -- two
worktrees, two installed versions -- each put their own archive there and each run their own.
And a file under one of those names that holds anything else, which an older humanize could
leave behind for a run of another checkout to find, is replaced rather than run. Both are said
of a stand-in next door; this is the real `docker exec`, the real image's Python doing the
checking, and the archive that lands being imported over there.

Needs a docker daemon holding `python:3.12-slim`.
"""

from __future__ import annotations

import secrets
import subprocess
from typing import TYPE_CHECKING

import pytest

from hmz.coganchor import transport
from hmz.coganchor.transport import CONTAINER_CACHE, Road, Target
from tests.coganchor.fixtures import checkout
from tests.machines.fixtures import IMAGE

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator
    from pathlib import Path


@pytest.fixture
def container(daemon: None) -> Iterator[str]:
    """A container of the test's own, with nothing of humanize in it yet."""
    name = f"hmz-bundles-{secrets.token_hex(4)}"
    subprocess.run(
        ["docker", "run", "-d", "--rm", "--name", name, IMAGE, "sleep", "600"],
        capture_output=True,
        check=True,
    )
    try:
        yield name
    finally:
        subprocess.run(["docker", "rm", "-f", name], capture_output=True, check=False)


def _checkout(under: Path, marker: str) -> tuple[Path, str]:
    """The archive a checkout told apart from this one by one line would ship.

    Returns:
      Where it is built, and its digest.
    """
    tree = checkout(under, marker)
    return transport._built(tree, transport._stamped(tree))


def _marker(road: Road, where: str) -> str:
    """What the archive at `where` in the container says it was built from."""
    reading = (
        "import sys; sys.path.insert(0, sys.argv[1]); "
        "from hmz.coganchor import checkout; print(checkout.MARKER)"
    )
    ran = road.run(["python3", "-c", reading, where])
    assert ran.returncode == 0, ran.stderr.decode()
    return ran.stdout.decode().strip()


def _shipping(held: tuple[Path, str]) -> Callable[[], tuple[Path, str]]:
    """A stand-in for `bundled` in a process of the checkout that built `held`."""
    return lambda: held


@pytest.mark.timeout(240)
def test_each_checkout_runs_its_own_archive_on_one_container(
    container: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("tempfile.tempdir", str(tmp_path))
    road = Road.to(Target.parse(f"docker://{container}"))
    built = {marker: _checkout(tmp_path / marker, marker) for marker in ("one", "two")}

    installed: dict[str, str] = {}
    for marker, held in built.items():
        monkeypatch.setattr(transport, "bundled", _shipping(held))
        installed[marker] = road.installed()

    assert installed["one"] != installed["two"]
    for marker, where in installed.items():
        assert where.startswith(f"{CONTAINER_CACHE}/humanize-")
        assert _marker(road, where) == marker

    # And a copy under one's name that is the other's bytes -- the collision itself -- is
    # put right by the next install, rather than believed for being there.
    road.run(["cp", installed["two"], installed["one"]])
    assert _marker(road, installed["one"]) == "two"
    road.forget()
    monkeypatch.setattr(transport, "bundled", _shipping(built["one"]))

    road.installed()

    assert _marker(road, installed["one"]) == "one"
