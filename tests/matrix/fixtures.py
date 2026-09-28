"""The fixtures of the regression matrix: `cell`, and `billed` for a row run once.

`billed` is the part of `cell` a row run once, which has no cell, still needs.

A plain module rather than a conftest, as every subsystem's fixtures here are -- see
`tests/tiers.py` -- and taken back by name in `tests/system/matrix/conftest.py`, the only
directory whose tests ask for it.
"""

from __future__ import annotations

import contextlib
import shutil
from pathlib import Path
from typing import TYPE_CHECKING, cast

import pytest

from tests.matrix import grid, places
from tests.matrix.cells import Cell, spent

if TYPE_CHECKING:
    from collections.abc import Iterator

__all__ = ["billed", "cell"]

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
