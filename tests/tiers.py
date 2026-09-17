"""Which of the three trees a test lives in, and what living there says it may touch.

A test's tier is the directory it is in, rather than a decorator somebody remembered to write.
A decorator is a thing to forget, and one forgotten is a test in the wrong half of a gate: a
system test that CI runs on a machine with no docker and no coding agent installed, or a unit
test that quietly started spawning processes and is still counted in the fast suite. So each of
`tests/unit`, `tests/integration` and `tests/system` marks everything beneath it from its own
`conftest.py` -- `applied` below -- and `tests/test_tiers.py` fails the run if a marker and a
directory ever disagree.

The three trees, and the one question that sorts a test between them -- *does it need something
CI cannot be relied on to have?*

  `tests/unit`
    Imports `hmz`, calls it, asserts. No subprocess, no socket, no network, nothing written
    anywhere but `tmp_path`. Milliseconds.
  `tests/integration`
    More than one part working together, but everything it talks to is a fake this repo wrote:
    a stand-in CLI on PATH, a fake app server, a fake websocket, a loopback HTTP or unix
    socket, `ShellAgent`, the interface driven by a Textual pilot. Deterministic, offline, and
    safe anywhere -- a loopback socket is not a system test, because every machine has one.
  `tests/system`
    The real thing: a coding-agent CLI installed on this machine, real ptrace and seccomp, real
    docker, real ssh, a real daemon fork, a real `node`. Never run by CI.

Which is what makes the trees worth the move: a run can name one.

    uv run pytest -m unit                  # a tier, on a machine that has everything
    uv run pytest --ignore=tests/system    # everything CI can be relied on to run

Those two are not two spellings of one thing, and CI names the directory on purpose. `-m "not
system"` selects the same tests, but selecting happens after collecting: a deselected test has
been imported already, and importing a system test is where a module that probes the machine as
it loads does the probing. A red job about a tier that job never meant to run is the failure
the trees exist to prevent, so the run that has to be dependable ignores the directory, and `-m`
is left for a developer choosing what to run.

`agent` is a second gate inside `tests/system` rather than a fourth tier: a system test that
spends real tokens has to be asked for by name with `--run-agents`, and one that only needs a
real `node` or a real docker does not. It is registered and applied in `tests/conftest.py`,
where the option that gates it has to live.

Moving a test into a tree does not move what it was written against, and the two travel
differently. A *helper* is imported by path -- `tests.stubs`, `tests.agents.standins`,
`tests.supervising`, `tests.sampling`, and the ones that live inside a subsystem conftest, like
`tests.tui.conftest.until` -- and keeps working from anywhere, which is why those files stay
where they are while only `test_*.py` moves: a hundred-odd import lines name them there. A
*fixture* is inherited from the directory tree instead, so a test that leaves `tests/tui`
leaves `tests/tui/conftest.py` behind it -- and what it leaves behind there is the autouse pair
that runs the interface somewhere temporary and stops it fetching from a remote. An autouse
fixture left behind fails *green*: nothing asked for it by name, so nothing says it is missing,
and the test goes on passing while reading the home directory of whoever ran it. The tier-side
conftest takes them back by name:

    # tests/integration/tui/conftest.py
    from tests.tui.conftest import _elsewhere, _fetches_nothing

    __all__ = ["_elsewhere", "_fetches_nothing"]

Named one by one, so that a reader of that directory can see what it is borrowing and from
where -- and re-exported through `__all__` rather than a `# noqa`, because the two gates
disagree about what a re-export looks like: an unused import is an error to pyright, the
`import x as x` spelling that would answer that is an error to ruff, and a name in `__all__` is
deliberate to both. The subsystem conftests themselves --
`tests/tui/conftest.py`, `tests/coganchor/conftest.py`, `tests/tracing/conftest.py`,
`tests/daemon/conftest.py`, `tests/machines/conftest.py` -- stay put, because a fixture is
still one definition however many trees ask for it.

Leaving a name out of that list is the one mistake here nothing else would notice, so
`tests/test_tiers.py` reads it back: a test under `tests/<tier>/tui` is held to the autouse
fixtures of `tests/tui`, and a run says which one went missing rather than passing without it.
It is the *autouse* ones that need a guard. A fixture asked for by name -- the `sandbox` in
`tests.composing`, which hands a test a path -- announces its own absence as `fixture 'sandbox'
not found`, and no check can improve on that; the autouse `sandbox` of `tests/tracing/conftest.py`,
which redirects four environment variables and returns nothing, goes missing in silence. Two
fixtures, one name, and only one of them is what this is about.

There are three ways a fixture reaches a test that moved, and the check knows only the first:

1. **Re-exported into the tier conftest**, as above. The default, and the only one a reader of
   the directory can see at a glance -- so the only one worth a rule.
2. **Imported into the test module itself.** An autouse fixture imported into a test file is
   autouse for that file, which is a real answer for a fixture that belongs to one file and
   would say nothing in a conftest over a directory. Both gates have to be told it is
   deliberate, as they do for the conftest form -- `# noqa: F401` and a `# pyright:
   ignore[reportUnusedImport]`. There is no declaration to compare it against, so nothing here
   checks it: use it for one file, and re-export for a directory.
3. **Left in a helper module that never moves** -- `tests/answering.py`, `tests/composing.py`,
   `tests/recording.py`, `tests/logins.py`, `tests/stubs.py` and the rest. A helper travels by
   import path, so there is nothing to take back.

A tier root -- `tests/unit/conftest.py` and the other two -- holds its marker and nothing else,
deliberately. A fixture written there would reach every subsystem in that tree, which is how
one subsystem's sandbox comes to be half-applied to another's tests.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Final

import pytest

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping

#: The three trees hang off this directory, which is the one this file is in.
_TESTS: Final = Path(__file__).parent

#: Each tier, and the line that registers its marker. `--strict-markers` is on, so a marker
#: nobody registered is a collection error rather than a warning -- which is what makes a name
#: worth registering: `-m integraiton` otherwise selects nothing, says nothing about the
#: spelling, and passes. The descriptions live here, beside the rule they describe, and
#: `tests/conftest.py` writes them out where pytest reads them.
TIERS: Final[Mapping[str, str]] = {
    "unit": "unit: calls hmz and asserts -- no subprocess, no socket, no network",
    "integration": (
        "integration: several parts together, against fakes this repo wrote -- offline, and"
        " safe in CI"
    ),
    "system": (
        "system: needs the real thing -- an installed coding agent, ptrace, docker, ssh."
        " Never run by CI"
    ),
}


#: Where each tree starts, worked out once. `tier` is asked about every collected test by each
#: of the three conftests, and building the same three paths ten thousand times a run is ten
#: thousand `Path`s for an answer that was settled when this module was imported.
_ROOTS: Final = {name: _TESTS / name for name in TIERS}

#: The directories under a tier that are named for no subsystem, and what is in each.
#:
#: Every other directory under a tier mirrors one: `tests/integration/tui` holds tests written
#: in `tests/tui`, and that mirroring is what lets `came_from` ask what a moved test used to be
#: given. These mirror nothing because what they hold was never in a subsystem directory at
#: all -- it sat directly in `tests/`, and moving it into the trees is what grouped it by
#: subject. The conftest those tests were written under is `tests/conftest.py`, which is an
#: ancestor of every tier tree as well, so nothing was left behind and there is nothing for the
#: fixture check to compare them against.
#:
#: Written down rather than inferred, because a directory that mirrors nothing on purpose and a
#: directory whose name is a typo look exactly alike from here: `tests/unit/tracing` mirrors a
#: subsystem and `tests/unit/tracnig` mirrors nothing, and without this list the second is
#: indistinguishable from the first. Anything not named here has to mirror a real directory.
#:
#: The last two are here for the other reason a mirror can be missing: `providers` and `sdk`
#: were real subsystem directories, and every file in them moved into the trees. Neither had a
#: conftest and neither had a helper module, so what was left behind was an empty directory and
#: git does not keep one -- the mirror is gone because there was nothing in it to keep, which is
#: the same position as never having had one. Were either to be written into again, the mirror
#: would come back and its name should come out of here.
MIRRORS_NOTHING: Final[Mapping[str, str]] = {
    "backends": "what a backend is, what it runs and what it costs",
    "cli": "the command line, and what it prints",
    "flows": "flows as the person who writes one meets them",
    "layering": "the table of which package may depend on which",
    "providers": "accounts humanize keeps, and the credentials a turn is run under",
    "runtime": "what a run leaves behind it: epics, exports, budgets, telemetry",
    "sdk": "humanize driven from Python rather than from a command line",
}


def tier(path: Path) -> str | None:
    """Which of the three trees a file is in.

    Args:
      path: The file a test was collected from.

    Returns:
      The tier it lives in, or None for a file outside all three -- which today is the
      migration backlog, and afterwards is only `tests/test_tiers.py` itself.
    """
    for name, root in _ROOTS.items():
        if path.is_relative_to(root):
            return name
    return None


def came_from(path: Path) -> Path | None:
    """The directory a test was written in, which is its own with the tier taken back out.

    `tests/integration/tui/test_boxes.py` was written in `tests/tui`, and what it was written
    against is still there: the subsystem conftest, and the autouse fixtures a test of the
    interface is not correct without. That a tree under a tier is named for the subsystem it
    came from is the whole of the convention, and this is what lets a check ask what a test
    used to be given.

    Args:
      path: The file a test was collected from.

    Returns:
      The directory it mirrors, or None for a file in no tier tree, which has not moved. A file
      directly under a tier root mirrors `tests` itself, whose conftest is an ancestor of every
      tree and so was never left behind by anything. The answer is where the test came from
      rather than somewhere that necessarily exists: a directory named in `MIRRORS_NOTHING`
      mirrors a path nobody ever wrote in, and `tests` above it is the real ancestor.
    """
    name = tier(path)
    if name is None:
        return None
    return _TESTS / path.relative_to(_ROOTS[name]).parent


def unmirrored(path: Path) -> str | None:
    """The tier directory this test is in that is named for nothing, and says nothing about it.

    The mirroring is what the fixture check is read through, so a directory that mirrors
    nothing is a directory that check passes over in silence -- which is right for the handful
    that hold tests written in `tests/` itself, and wrong for a directory whose name is a
    misspelling of a real subsystem. The two are told apart by `MIRRORS_NOTHING`, and only by
    it: one is written down and the other is not.

    Args:
      path: The file a test was collected from.

    Returns:
      The name to be explained -- the first directory under the tier -- or None when it mirrors
      a real directory under `tests`, when it is written down as mirroring none, or when the
      test sits directly under the tier root and mirrors `tests` itself.
    """
    name = tier(path)
    if name is None:
        return None
    within = path.relative_to(_ROOTS[name]).parts
    if len(within) < 2:
        return None
    subsystem = within[0]
    if subsystem in MIRRORS_NOTHING or (_TESTS / subsystem).is_dir():
        return None
    return subsystem


def applied(name: str, items: Iterable[pytest.Item]) -> None:
    """Puts one tree's marker on every test collected from beneath it.

    Called from that tree's `conftest.py`, which is the seam that makes a directory a tier: a
    file moved into `tests/unit` is a unit test from the move alone, and nobody has to remember
    a decorator or keep a list of paths in step.

    `pytest_collection_modifyitems` is handed the whole session's items wherever it is
    implemented -- a conftest deeper in the tree is still called with every test the run
    collected, not just the ones under it -- so each item is checked against this tree before
    it is marked. Without that, the first tier conftest to be called would mark the suite.

    Args:
      name: The tier this conftest speaks for.
      items: Everything the run collected.
    """
    # Read off `pytest.mark` here rather than at import time: the markers are registered in
    # `pytest_configure`, and under `--strict-markers` reaching for one before that is a
    # failure about a marker that is about to exist.
    mark: pytest.MarkDecorator = getattr(pytest.mark, name)
    for item in items:
        if tier(item.path) == name:
            item.add_marker(mark)
