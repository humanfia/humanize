"""The checks that keep the three trees honest, so the split is true rather than aspirational.

Three things can go wrong when a test moves, and none of them is loud on its own.

A test can end up in the wrong tree, or wearing a marker the tree does not agree with -- a `git
mv` into the tier next door, or a `@pytest.mark.system` written by hand on a test that sits in
`tests/unit` and so is run by CI anyway, on a machine with no docker.

A test can arrive in a tree without the fixtures it was written against. A fixture is
inherited down a directory tree, so a test that left `tests/tui` left that directory's autouse
fixtures behind it unless the conftest beside it took them back by name -- and an autouse
fixture is asked for by nobody, so losing one is a test that goes on passing while reading the
real home directory of whoever ran it. That is a green suite over a test that checks nothing,
which is worse than a red one.

And the directory a test left can go on being treated as though tests were still under it.
A hook is not inherited the way a fixture is re-exported: it fires from a conftest pytest
loaded as a plugin, so one written where the tests no longer are fires for a run of the whole
tree and not for a run that names a tier. Which of the two a contributor typed is then the
difference between two green suites that ran different code.

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

import ast
import importlib
from pathlib import Path
from typing import Final, NoReturn

import pytest
from _pytest.fixtures import FixtureFunctionDefinition

from tests import tiers
from tests.conftest import COLLECTED

#: The root of the tree, which is where the conftest every test inherits from lives.
_TESTS: Final = Path(__file__).parent

#: What each directory's conftests declare autouse, worked out the first time it is asked for:
#: importing a conftest and reading its fixtures back is cheap once and three thousand times
#: over is a second of every run.
_AUTOUSE: Final[dict[Path, frozenset[str]]] = {}

#: The two files a directory can declare fixtures in, in the order a reader would find them.
#: `conftest.py` is pytest's own answer and is what the root of the tree uses; `fixtures.py` is
#: what a subsystem directory uses now that it holds no tests, for the reason in `tests/tiers.py`.
_DECLARE: Final = ("conftest.py", "fixtures.py")

#: What a name has to start with to be something only a conftest is read for: a hook, or one
#: of the two `collect_ignore` lists, which are assignments pytest reads out of a conftest and
#: out of nothing else. Used twice over -- as a substring to decide whether a file is worth
#: parsing, and as the prefix that says which of the names it binds are these.
_HOOKISH: Final = ("pytest_", "collect_ignore")

#: The conftests a hook may be written in. The root of the tree, which every run of any part
#: of it loads, and each tier's own, which every run that collects one of its tests loads.
#: Anywhere else is a hook that fires or does not depending on how the run was spelled.
_PLUGINS: Final = frozenset(
    {_TESTS / "conftest.py"} | {_TESTS / name / "conftest.py" for name in tiers.TIERS}
)

#: The hooks pytest reads only from an initial conftest -- the ones on the path to what the
#: command line named, consulted before the run knows what else it will load. A tier conftest
#: is one of those for `uv run pytest tests/unit` and not for `uv run pytest`, so an option
#: added there is an option half the runs refuse; `tests/conftest.py` is one for every run.
_INITIAL: Final = frozenset(
    {
        "pytest_addoption",
        "pytest_cmdline_main",
        "pytest_cmdline_parse",
        "pytest_load_initial_conftests",
    }
)


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
    """The autouse fixtures a directory is under, from its own declarations and its parents'.

    Read by importing each file and asking the fixtures themselves, rather than by reading the
    `__all__` beside them: a name re-exported into a tier conftest but no longer autouse where
    it is defined would pass a check on the spelling and fail the run.

    Both `_DECLARE` names are looked for at every level, because a subsystem and the root
    answer in different files and each is right where it is. `tests/conftest.py` is a conftest
    because it is one -- it holds the run's options and its hooks, over every test there is. A
    subsystem's is `fixtures.py` because its directory holds no tests any more, and a conftest
    over no tests is a plugin loaded by one run and not the next; `tests/tiers.py` has that at
    length. Looking for both is what keeps this honest if either ever answers differently: a
    `conftest.py` written back into `tests/tui` would be read here and held to the same
    re-export rule, rather than silently dropping every autouse fixture in it from the check.

    A directory that was never written in -- one of `tiers.MIRRORS_NOTHING` -- declares
    nothing, and the walk up to `tests` answers with the fixtures every test in the tree has
    anyway. Which is the true answer for it: those tests were written in `tests`.

    Args:
      directory: A directory under `tests`, which need not exist.

    Returns:
      The names, from `directory` up to `tests` itself.
    """
    if directory in _AUTOUSE:
        return _AUTOUSE[directory]
    names: set[str] = set()
    here = directory
    while here.is_relative_to(_TESTS):
        for declares in (here / name for name in _DECLARE):
            if not declares.is_file():
                continue
            module = importlib.import_module(
                ".".join(declares.relative_to(_TESTS.parent).with_suffix("").parts)
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


def _hooks(path: Path) -> set[str]:
    """The names a file binds that only a conftest would be honoured for, out of its source.

    Every top-level binding, whatever binds it, because pytest reads a plugin with `dir` and
    does not care how a name got there: `def pytest_configure` and `pytest_configure = _do_it`
    and `from tests.tui.fixtures import pytest_configure` are one hook three ways, and a check
    that saw only the first would be a rule anybody could step around by accident.
    `pytest_plugins` and `collect_ignore` are assignments rather than functions and are read
    out of a conftest just the same, which is why the names below are not only the `pytest_`
    ones.

    The substring pass first, because this walks every file in the tree on every run and all
    but a handful of them mention none of these at all -- an `in` over the text is most of a
    megabyte cheaper than an AST for each.

    Args:
      path: A Python file under `tests`.

    Returns:
      The hook-shaped names it binds at the top level, which is empty for nearly every file.
    """
    source = path.read_text(encoding="utf-8")
    if not any(word in source for word in _HOOKISH):
        return set()
    bound: set[str] = set()
    for node in ast.parse(source).body:
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            bound.add(node.name)
        elif isinstance(node, ast.Assign):
            bound |= {
                target.id for target in node.targets if isinstance(target, ast.Name)
            }
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            bound.add(node.target.id)
        elif isinstance(node, ast.Import | ast.ImportFrom):
            bound |= {alias.asname or alias.name.split(".")[0] for alias in node.names}
    return {name for name in bound if name.startswith(_HOOKISH)}


def _misplaced(path: Path, names: set[str]) -> set[str]:
    """Which of the hooks a file binds are hooks pytest will honour unevenly from there.

    Args:
      path: The file that binds them.
      names: What `_hooks` read out of it.

    Returns:
      The subset that is in the wrong file, which is empty for a file in the right one.
    """
    if path not in _PLUGINS:
        return names
    if path.parent == _TESTS:
        return set()
    return names & _INITIAL


def _nothing_to_check_against(config: pytest.Config) -> NoReturn:
    """Ends a check that was handed no tier test to look at -- skipped, or failed.

    The floor it ends is what stops the check below passing vacuously. It reads the whole
    collection rather than the run's own selection, so "found nothing to disagree with" and
    "found nothing at all" look alike from inside it, and a `tiers.tier` that stopped
    recognising a tree would be a guard that went green over three thousand unchecked tests.
    That is the failure the floor exists for, and it has to stay a failure.

    But it is only a failure when the run was in a position to hand over a tier test.
    `uv run pytest tests/test_tiers.py`, which is what somebody who has just edited this file
    runs, collects this file alone -- no tier tree is under that path, so there is nothing
    here to check and nothing wrong. Failing there is a red suite about no defect, which is
    the kind of red that teaches people to stop believing the gate.

    The two are told apart by what the run was pointed at rather than by how it was spelled:
    every path it named, against the three tier roots. If one of them is a tier root, or holds
    one, then tier tests were there to be collected and coming back with none is the bug.
    `uv run pytest`, `uv run pytest tests` and `uv run pytest tests/unit` all reach a root and
    all stay a failure -- the first names the invocation directory rather than a path, which
    is above all three. Only a run whose every argument is beside the trees, which is this
    file and the helpers, has nothing to be checked against.

    `-k` and `-m` are not a filter for this purpose and need no allowance: `COLLECTED` is
    written down from a conftest hook, which runs before pytest's own deselection, so it holds
    the whole tree under those whatever the run asked to execute.

    Args:
      config: The run's own configuration, for the paths it was pointed at.

    Raises:
      Skipped: No tier tree was under anything the run named.
      Failed: A tier tree was, and no test came back from it.
    """
    roots = [(_TESTS / name).resolve() for name in tiers.TIERS]
    # Split on `::` because an argument can name a test inside a file rather than a file, and
    # resolve against the directory pytest was started in because an argument is as the
    # developer typed it -- `tests/unit` from the root of the repository, `../unit` from
    # inside `tests/system`, and neither is comparable to a root until it is absolute.
    named = [
        (config.invocation_params.dir / argument.split("::")[0]).resolve()
        for argument in config.args
    ]
    if any(
        root.is_relative_to(path) or path.is_relative_to(root)
        for path in named
        for root in roots
    ):
        pytest.fail("no test was collected from any tier tree, so this checked nothing")
    pytest.skip(
        "this check needs the whole tree, so run it without a path filter:"
        " `uv run pytest`, not `uv run pytest tests/test_tiers.py`"
    )


def test_every_test_carries_the_tier_of_the_tree_it_was_collected_from(
    pytestconfig: pytest.Config,
) -> None:
    """One marker, put on by the directory, and no second one written over it.

    Both directions at once: a test in a tree without its marker is one `-m unit` would miss,
    and a test carrying a marker for a tree it is not in is one `--ignore=tests/system` would
    keep but `-m "not system"` would throw away.
    """
    assert COLLECTED, "the collection was never written down, so this checked nothing"
    if not any(tiers.tier(item.path) for item in COLLECTED):
        _nothing_to_check_against(pytestconfig)

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

    Autouse only, which is the whole of what needs a check: a fixture asked for by name says
    `fixture 'sandbox' not found` when it is missing, and no assertion improves on that. Note
    that there are two fixtures called `sandbox` in this tree -- one in `tests.composing`,
    handed to a test that asks for it by name, and the autouse one in `tests/tracing/fixtures.py`
    that redirects four environment variables and returns nothing. Only the second is the kind
    of thing this is about, and a directory that re-exports the first is not covered by it.
    """
    assert COLLECTED, "the collection was never written down, so this checked nothing"

    lost = [
        f"{item.nodeid}: {', '.join(sorted(missing))}, from {written_in}"
        for item in COLLECTED
        for written_in in [tiers.came_from(item.path)]
        if written_in is not None
        for missing in [_declared(written_in) - _given(item)]
        if missing
    ]

    assert not lost, (
        "a test moved out of the directory that gave it these autouse fixtures, and the"
        " conftest beside it does not take them back:\n" + "\n".join(lost)
    )


def test_a_tier_directory_is_named_for_the_subsystem_it_holds_or_says_why_not() -> None:
    """The mirroring the check above is read through, held up by the one thing that can.

    `came_from` answers by name: `tests/<tier>/tui` holds what was written in `tests/tui`. A
    directory named for nothing therefore mirrors nothing, the fixture check over it compares
    against `tests/conftest.py` alone, and it passes -- silently, whether that silence was
    earned or is a misspelling of `tracing` nobody has noticed.

    Some of them earn it: the tests that were written directly in `tests/` were grouped by
    subject as they moved, into directories no subsystem ever had. `tiers.MIRRORS_NOTHING` is
    where those are written down, with what is in each, so that a name not on that list and not
    matching a real directory is a typo the run reports rather than a hole it keeps.
    """
    assert COLLECTED, "the collection was never written down, so this checked nothing"

    unexplained = sorted(
        {
            f"tests/{tiers.tier(item.path)}/{named}"
            for item in COLLECTED
            for named in [tiers.unmirrored(item.path)]
            if named is not None
        }
    )

    assert not unexplained, (
        "a tier directory is named for no directory under tests/. Rename it for the subsystem"
        " it mirrors, or add it to tiers.MIRRORS_NOTHING with what it holds:\n"
        + "\n".join(unexplained)
    )


def test_a_hook_is_written_where_pytest_will_load_it_for_the_tests_it_speaks_for() -> (
    None
):
    """The other half of what a directory declares, and the half that does not travel.

    A fixture reaches a moved test through the re-export the check above holds a tier to. A
    hook has no such thing. `pytest_configure`, `pytest_collection_modifyitems` and the rest
    are called from a conftest pytest loaded as a plugin, which is a conftest on the path from
    the rootdir to what is being collected -- and `tests/tui` is on the path to nothing, now
    that every `test_*.py` under it has moved into a tree. A hook written there fires for
    `uv run pytest`, which walks past the directory on its way through `tests`, and does not
    fire for `uv run pytest tests/integration`, which never looks at it. Neither run says a
    word about the difference. That is why those files are `fixtures.py` rather than
    `conftest.py`: a plain module cannot be loaded as a plugin, so a hook in one is dead
    rather than half-alive -- which is quieter still, and is the other shape this catches.

    So the rule is about where a `pytest_*` is written rather than about what it does, and
    `_PLUGINS` is the whole of where: `tests/conftest.py`, which every run of any part of this
    tree loads, and the three tier conftests, each of which is loaded by every run that
    collects a test it speaks for. A conftest deeper in a tier is left out although pytest
    would load it, because the hook it would hold is not: `pytest_collection_modifyitems` is
    handed the whole session's items wherever it is written, so one in
    `tests/integration/tui/conftest.py` speaks for tests in `tests/unit` and fires only when
    something under `tests/integration/tui` is collected. A hook over the session belongs at
    the top of the tree it is about, filtering by path the way `tiers.applied` does.

    `_INITIAL` is the narrower case inside that: pytest reads the initial hooks only from the
    conftests on the path to what the command line named, before it knows what else it is
    going to load. `pytest_addoption` in `tests/unit/conftest.py` would give `uv run pytest
    tests/unit --whatever` an option that `uv run pytest --whatever` refuses outright, which
    is how CI comes to fail on a flag that works locally. `tests/conftest.py` is on that path
    for every run of this tree, so it is the only place they hold.

    Read off the source rather than by importing: every test module in the tree would have to
    be imported to ask it this, which is most of a collection for a question `ast` answers
    from the text.
    """
    written = {
        path: names
        for path in sorted(_TESTS.rglob("*.py"))
        for names in [_hooks(path)]
        if names
    }
    assert written, (
        "no pytest hook was found under tests/ at all, so this checked nothing"
    )

    stray = [
        f"{path.relative_to(_TESTS.parent)}: {', '.join(sorted(misplaced))}"
        for path, names in written.items()
        for misplaced in [_misplaced(path, names)]
        if misplaced
    ]

    assert not stray, (
        "a pytest hook is written where pytest honours it for some runs and not others. A"
        " hook belongs in tests/conftest.py or in a tier's own conftest, and an option or a"
        " command-line hook belongs in tests/conftest.py alone:\n" + "\n".join(stray)
    )
