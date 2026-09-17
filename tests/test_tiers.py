"""The checks that keep the three trees honest, so the split is true rather than aspirational.

Two things can go wrong when a test moves, and neither of them is loud on its own.

A test can end up in the wrong tree, or wearing a marker the tree does not agree with -- a `git
mv` into the tier next door, or a `@pytest.mark.system` written by hand on a test that sits in
`tests/unit` and so is run by CI anyway, on a machine with no docker.

And a test can arrive in a tree without the fixtures it was written against. A fixture is
inherited down a directory tree, so a test that left `tests/tui` left that directory's autouse
fixtures behind it unless the conftest beside it took them back by name -- and an autouse
fixture is asked for by nobody, so losing one is a test that goes on passing while reading the
real home directory of whoever ran it. That is a green suite over a test that checks nothing,
which is worse than a red one.

Nothing here can tell that a test filed as a unit test opens no sockets; that is a thing a
reader knows and a reviewer asks about. What it can tell is that the directory, the marker and
the fixtures all say the same thing, which is what the mechanism in `tests/tiers.py` promises.

Tier-neutral on purpose, and the one test file that is. These are read against the whole
collection, and a gate that ran only when its own tier was selected would not be a gate: under
`-m unit` it would be deselected, and a system test misfiled into `tests/integration` would sail
through the run that was meant to catch it. So the rule below is "the tree a test is in is the
marker it carries" rather than "every test carries a tier": a test outside all three trees
carries none. Today that is the migration backlog -- the files not yet moved -- and when the
last of them has moved it is this file alone.
"""

from __future__ import annotations

import importlib
from pathlib import Path
from typing import TYPE_CHECKING, Final

from _pytest.fixtures import FixtureFunctionDefinition

from tests import tiers
from tests.conftest import COLLECTED

if TYPE_CHECKING:
    import pytest

#: The root of the tree, which is where the conftest every test inherits from lives.
_TESTS: Final = Path(__file__).parent

#: What each directory's conftests declare autouse, worked out the first time it is asked for:
#: importing a conftest and reading its fixtures back is cheap once and three thousand times
#: over is a second of every run.
_AUTOUSE: Final[dict[Path, frozenset[str]]] = {}


def _carried(item: pytest.Item) -> list[str]:
    """Which tier markers a test carries, in a list rather than a set.

    Read off the markers rather than `item.keywords`, which is the other way to ask and the
    wrong one: keywords hold the names of a test's parents too, so every test under
    `tests/unit` answers to "unit" there whether anything marked it or not -- and a check
    written against that would pass over a tree nobody was marking at all.

    A list because a duplicate is a finding: a hand-written `@pytest.mark.unit` on a test in
    `tests/unit` says nothing new today and is a stale marker the day that file moves, which is
    a disagreement reported against a line nobody remembers writing.
    """
    return [mark.name for mark in item.iter_markers() if mark.name in tiers.TIERS]


def _given(item: pytest.Item) -> set[str]:
    """Every fixture this test is given without asking: the autouse ones in scope for it.

    Which is pytest's own answer rather than a reading of the conftests -- the same list it
    will act on when the test runs.
    """
    return set(item.session._fixturemanager._getautousenames(item))


def _declared(directory: Path) -> frozenset[str]:
    """The autouse fixtures a directory is under, from its own conftest and its parents'.

    Read by importing each `conftest.py` and asking the fixtures themselves, rather than by
    reading the `__all__` beside them: a name re-exported into a tier conftest but no longer
    autouse where it is defined would pass a check on the spelling and fail the run.

    Args:
      directory: A directory under `tests`.

    Returns:
      The names, from `directory` up to `tests` itself.
    """
    if directory in _AUTOUSE:
        return _AUTOUSE[directory]
    names: set[str] = set()
    here = directory
    while True:
        conftest = here / "conftest.py"
        if conftest.is_file():
            module = importlib.import_module(
                ".".join(conftest.relative_to(_TESTS.parent).with_suffix("").parts)
            )
            names |= {
                fixture.name
                for fixture in vars(module).values()
                if isinstance(fixture, FixtureFunctionDefinition)
                and fixture._fixture_function_marker.autouse
            }
        if here == _TESTS:
            break
        here = here.parent
    _AUTOUSE[directory] = frozenset(names)
    return _AUTOUSE[directory]


def test_every_test_carries_the_tier_of_the_tree_it_was_collected_from() -> None:
    """One marker, put on by the directory, and no second one written over it.

    Both directions at once: a test in a tree without its marker is one `-m unit` would miss,
    and a test carrying a marker for a tree it is not in is one `--ignore=tests/system` would
    keep but `-m "not system"` would throw away.
    """
    assert COLLECTED, "the collection was never written down, so this checked nothing"
    filed = [item for item in COLLECTED if tiers.tier(item.path)]
    assert filed, "no test was collected from any tier tree, so this checked nothing"

    disagree = [
        f"{item.nodeid}: in {here or 'no tier tree'}, marked {carried or 'nothing'}"
        for item in COLLECTED
        for here in [tiers.tier(item.path)]
        for carried in [_carried(item)]
        if carried != ([here] if here else [])
    ]

    assert not disagree, (
        "a test's tier marker and its directory disagree:\n" + "\n".join(disagree)
    )


def test_a_test_that_drives_a_real_coding_agent_is_filed_as_a_system_test() -> None:
    """`agent` is a gate inside `tests/system`, so it cannot be worn anywhere else.

    A test that spends real tokens is a system test by every reading of the word, and one filed
    as a unit or an integration test is one CI would run -- against a coding agent the runner
    has not got, with an account it has not got either. `--run-agents` is what keeps it from
    running today; this is what keeps it from being filed somewhere that option is the only
    thing standing between a green suite and somebody's bill.
    """
    assert COLLECTED, "the collection was never written down, so this checked nothing"

    misfiled = [
        item.nodeid
        for item in COLLECTED
        if any(mark.name == "agent" for mark in item.iter_markers())
        and tiers.tier(item.path) not in {None, "system"}
    ]

    assert not misfiled, (
        "a test that drives a real agent is filed outside tests/system:\n"
        + "\n".join(misfiled)
    )


def test_a_test_that_moved_still_has_the_autouse_fixtures_it_was_written_under() -> (
    None
):
    """A tier tree named for a subsystem is held to that subsystem's autouse fixtures.

    This is the one a green run would otherwise hide. The autouse fixtures of `tests/tui`,
    `tests/coganchor` and the rest are what keep a suite off the network and out of the home
    directory of whoever is running it; a test that moved into `tests/<tier>/tui` and did not
    take them back reads the real thing and passes, and the only sign is a transcript from
    somebody else's machine turning up in an assertion months later.

    So the conftest beside a moved test has to re-export what it left behind, and the failure
    here names the fixture rather than the symptom.
    """
    assert COLLECTED, "the collection was never written down, so this checked nothing"

    lost = [
        f"{item.nodeid}: {', '.join(sorted(missing))}, from {written_in}"
        for item in COLLECTED
        for written_in in [tiers.came_from(item.path)]
        if written_in is not None and written_in.is_dir()
        for missing in [_declared(written_in) - _given(item)]
        if missing
    ]

    assert not lost, (
        "a test moved out of the directory that gave it these autouse fixtures, and the"
        " conftest beside it does not take them back:\n" + "\n".join(lost)
    )
