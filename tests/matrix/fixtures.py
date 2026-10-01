"""The fixtures of the regression matrix: `cell`, and `billed` for a row run once.

`billed` is the part of `cell` a row run once, which has no cell, still needs. And
`home_kept_here`, humanize's home where the default one is, which a row about an agent's
mirror asks for before its cell -- and so does `tests/system/flows/test_workdirs.py`.

A plain module rather than a conftest, as every subsystem's fixtures here are -- see
`tests/tiers.py` -- and taken back by name in `tests/system/matrix/conftest.py`, the only
directory whose tests ask for it.
"""

from __future__ import annotations

import contextlib
import os
import shutil
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING, cast

import pytest

from tests.matrix import grid, places
from tests.matrix.cells import Cell, spent

if TYPE_CHECKING:
    from collections.abc import Generator, Iterator

__all__ = ["billed", "cell", "home_kept_here"]

#: The unit prices this machine last fetched, which a cell's home is given a copy of: the
#: suite fetches nothing, and a cost cap over prices nobody has is a cap nothing reads.
_PRICES = Path.home() / ".humanize" / "prices.json"


def _priced() -> None:
    """Gives the test's home this machine's prices, where it has any."""
    from hmz import home

    home().mkdir(parents=True, exist_ok=True)
    if _PRICES.is_file():
        shutil.copy2(_PRICES, home() / "prices.json")


@pytest.fixture
def billed(request: pytest.FixtureRequest) -> Iterator[list[Path]]:
    """For a row run once that spends: prices to cap it by, and what it spent on the grid.

    What `cell` does for a row of every CLI, for one that has no cell: this machine's prices
    in the test's home, and the bill of every workspace it ran in told as it comes apart.

    Yields:
      The workspaces to bill, which the row adds each of its own to.
    """
    _priced()
    node = cast("pytest.Item", request.node)  # pyright: ignore[reportUnknownMemberType]
    held: list[Path] = []
    try:
        yield held
    finally:
        total = {"cost": 0.0, "output_tokens": 0.0}
        for one in held:
            for what, much in spent(one).items():
                total[what] += much
        node.user_properties.append((grid.SPENT, total))


@pytest.fixture
def cell(
    cli: str,
    request: pytest.FixtureRequest,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[Cell]:
    """One CLI, at the place its column is run at, with a workspace of its own to run in.

    Skips as environment -- saying what was missing -- where the CLI is not installed or no
    place of it answers on this machine. Borrows the account the place is under for as long
    as the cell runs, and takes it back off disk afterwards.
    """
    if not places.installed(cli):
        pytest.skip(f"environment: {cli} is not installed here")
    _priced()
    # The workspace before anything is asked, so that a CLI asked for a word while its place
    # is settled tidies up nothing of this project's.
    (tmp_path / "work").mkdir()
    monkeypatch.chdir(tmp_path / "work")
    place = places.settled(cli)
    if isinstance(place, str):
        pytest.skip(
            f"environment: {cli} takes a turn nowhere on this machine -- {place}"
        )
    # The test the cell is, which pytest does not type from here.
    node = cast("pytest.Item", request.node)  # pyright: ignore[reportUnknownMemberType]
    node.user_properties.append((grid.PLACE, str(place)))
    with contextlib.ExitStack() as holding:
        if place.provider:
            holding.enter_context(places.borrowed(cli, place.provider))
        held = Cell(cli, place, tmp_path)

        def billed() -> None:
            # Told as the cell comes apart, so that the teardown report carries it to
            # whichever process is drawing the grid.
            node.user_properties.append((grid.SPENT, held.spent()))

        holding.callback(billed)
        yield held


@pytest.fixture
def home_kept_here(monkeypatch: pytest.MonkeyPatch) -> Generator[Path]:
    """Humanize's home inside a directory every agent keeps on this machine, as the default is.

    `~/.humanize` is one of those, and a container's mirrors are kept under humanize's home:
    the suite's own home under the system's temporary directory is the one place a mirror
    swallowed by a directory kept here could not be seen. `~/.cache/humanize` is another, and
    on many a machine `~/.cache` is a link to somewhere else, which a mirror under it has to
    be found through as well. Asked for before `cell`, so that an account the cell borrows is
    borrowed into this home, and taken away with it.
    """
    from hmz.coganchor.statepaths import COMMON_STATE_PATHS

    kept = Path(os.path.expanduser("~/.cache/humanize"))  # noqa: PTH111
    assert "~/.cache/humanize" in COMMON_STATE_PATHS
    kept.mkdir(parents=True, exist_ok=True)
    home = Path(tempfile.mkdtemp(prefix="matrix-", dir=kept))
    monkeypatch.setenv("HUMANIZE_HOME", str(home))
    try:
        yield home
    finally:
        shutil.rmtree(home, ignore_errors=True)
