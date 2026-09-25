"""Where flows come from when they come from somewhere else.

A flowverse is somebody's repository with a `flows/` directory in it, cloned under humanize's
home and offered under the name it is kept there. One of them is always there whatever has been
fetched -- `official`, which is humanize's own and is the handful in the package together with
the repository of the rest -- so what is checked here is that the list says what there is to
run rather than what has been downloaded, that both halves of humanize's own are offered under
the one name, that the flows are the ones in `flows/` and nothing else the repository came
with, that fetching one twice is a fetch rather than a merge, and that the ones that are always
there cannot be taken away.
"""

from __future__ import annotations

import asyncio
import subprocess
import threading
from typing import TYPE_CHECKING

import pytest

from hmz.flows import FlowNotFound
from hmz.runtime.flowing import (
    BUILTIN_AT,
    ENTRY,
    FLOWS,
    LOCAL,
    OFFICIAL,
    USER,
    find,
    flowverses,
    found,
    resolved,
)
from hmz.runtime.flowing import verses as store
from tests.stubs import written

if TYPE_CHECKING:
    from pathlib import Path

#: A flow, as short as one can be: the file is what is being fetched, not what it does.
FLOW = '''"""A flow of somebody else's."""

from hmz.flows import Agent, AgentCollection, EnvCollection, FlowParams, LocalEnv, flow


class Agents(AgentCollection):
    agent: Agent


class Envs(EnvCollection):
    here: LocalEnv


@flow(agents=Agents, envs=Envs, params=FlowParams)
async def run(task, *, agents, envs, params, ctx):
    session = await agents["agent"].spawn(env=envs["here"])
    return await agents["agent"].run(task, session=session)
'''


#: How long one thread here waits on another before giving up on it. A race nobody resolves
#: is a suite that hangs rather than one that fails, so every wait here has a clock on it.
_PATIENCE = 30.0


def _git(*said: str, at: Path) -> None:
    """Runs one git command in a directory, failing the test if it fails."""
    subprocess.run(["git", "-C", str(at), *said], check=True, capture_output=True)


@pytest.fixture
def theirs(tmp_path: Path) -> Path:
    """A repository of two flows and something they import, to be fetched from."""
    where = tmp_path / "theirs"
    (where / FLOWS).mkdir(parents=True)
    written(where / FLOWS, "loop", FLOW)
    written(where / FLOWS, "review", FLOW)
    # Not a flow: what the flows beside it import, which is what the underscore means.
    (where / FLOWS / "_shared.py").write_text("HELD = 1\n")
    # Nor is anything else the repository is made of: it is outside the flows directory, and
    # only what is inside it is read.
    (where / "README.md").write_text("# theirs\n")
    (where / "conftest.py").write_text("HELD = 1\n")
    _git("init", "-b", "main", at=where)
    _git("config", "user.email", "t@example.com", at=where)
    _git("config", "user.name", "t", at=where)
    _git("add", "-A", at=where)
    _git("commit", "-m", "two flows", at=where)
    return where


def test_humanize_s_own_is_always_there_and_is_never_a_fetch_away() -> None:
    """Listed first, listed from the start, and not one anybody has to add."""
    listed = flowverses()

    assert listed[0].name == OFFICIAL
    assert listed[0].fixed
    assert listed[0].url.endswith("humanfia/flowverse")


def test_the_flows_in_the_package_are_read_where_they_stand() -> None:
    """No `flows/` for those: they are the package's own, with no repository around them.

    A fetched flowverse needs that directory to tell its flows from the README, the pyproject
    and the test suite that came down with them. That half of humanize's own is a directory of
    flows and nothing else, so there is nothing to tell them from.
    """
    one = store.named(OFFICIAL)
    assert one is not None

    assert store.holds(one) == (BUILTIN_AT, one.at / FLOWS)
    assert "chat" in store.flows(one)
    assert find("chat") == str((BUILTIN_AT / "chat" / ENTRY).resolve())


def test_the_official_one_is_offered_before_it_is_fetched() -> None:
    """Or a list of what there is to run would be a list of what has been downloaded."""
    (official,) = [one for one in flowverses() if one.name == OFFICIAL]

    assert not official.fetched
    # The half that is in the package is there whatever has been downloaded, and nothing is
    # raised about the half that has not been.
    assert store.flows(official) == ["chat"]


def test_a_flow_of_humanize_s_own_is_said_the_same_way_wherever_it_is_kept(
    theirs: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """One name for humanize's flows: which of its two places one is in is humanize's business.

    So `chat`, which is in the package, and `loop`, which is in the repository, are both a bare
    name -- and `official/` in front of either is the spelling that says whose it is, which
    goes on resolving for both.
    """
    monkeypatch.setattr(store, "OFFICIAL_URL", str(theirs))
    store.fetch(OFFICIAL)

    assert [one.name for one in found() if one.whose == OFFICIAL] == [
        "chat",
        "loop",
        "review",
    ]
    assert find("official/chat") == str((BUILTIN_AT / "chat" / ENTRY).resolve())
    assert find("official/loop") == find("loop")


def test_the_package_s_own_wins_a_name_the_repository_also_holds(
    theirs: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The half that is always there beats the half a fetch could take away."""
    written(theirs / FLOWS, "chat", FLOW)
    _git("add", "-A", at=theirs)
    _git("commit", "-m", "a chat of its own", at=theirs)
    monkeypatch.setattr(store, "OFFICIAL_URL", str(theirs))
    store.fetch(OFFICIAL)

    assert [one.name for one in found() if one.whose == OFFICIAL] == [
        "chat",
        "loop",
        "review",
    ]
    assert find("chat") == str((BUILTIN_AT / "chat" / ENTRY).resolve())


@pytest.mark.parametrize("said", ["..", "one/two", "", ".", "/absolute"])
def test_a_name_that_is_not_one_directory_is_refused(said: str) -> None:
    """A flowverse is a directory under humanize's home, and a name that climbs out is not one."""
    with pytest.raises(ValueError, match="not a flowverse name"):
        store.where(said)


def test_one_that_was_added_is_offered_under_the_name_it_was_kept_under(
    theirs: Path,
) -> None:
    added = store.add(str(theirs))

    assert (
        added.name == "theirs"
    )  # the repository's own name, nobody having said otherwise
    assert added.fetched
    assert added.url == str(theirs)  # where it came from, as its own clone says
    assert not added.fixed
    assert [one.name for one in flowverses()] == [OFFICIAL, "theirs", LOCAL, USER]
    # Its flows, less the file that is not one.
    assert store.flows(added) == ["loop", "review"]


def test_it_may_be_called_something_else_here(theirs: Path) -> None:
    """Two people's repositories may share a name; the name it is kept under is yours."""
    added = store.add(str(theirs), "mine")

    assert added.name == "mine"
    assert (store.under() / "mine" / FLOWS / "loop" / ENTRY).is_file()


def test_adding_one_twice_is_refused(theirs: Path) -> None:
    store.add(str(theirs))

    with pytest.raises(ValueError, match="already a flowverse called"):
        store.add(str(theirs))


def test_a_repository_that_is_not_there_says_so(tmp_path: Path) -> None:
    """Said where it was asked for, rather than left as a flowverse with nothing in it."""
    with pytest.raises(OSError, match=r"git|repository"):
        store.add(str(tmp_path / "nowhere"))

    assert [one.name for one in flowverses()] == [OFFICIAL, LOCAL, USER]


def test_fetching_takes_what_the_repository_says_now(theirs: Path) -> None:
    """A flowverse is a copy of somebody's repository, so a fetch is what it says now."""
    store.add(str(theirs))
    written(theirs / FLOWS, "loop", FLOW.replace("A flow", "The same flow, changed"))
    written(theirs / FLOWS, "third", FLOW)
    _git("add", "-A", at=theirs)
    _git("commit", "-m", "another", at=theirs)

    again = store.fetch("theirs")

    assert store.flows(again) == ["loop", "review", "third"]
    (held,) = store.holds(again)
    assert "changed" in (held / "loop" / ENTRY).read_text()


def test_fetching_one_that_was_never_fetched_clones_it(
    theirs: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Which is what `official` has done to it the first time somebody wants what is in it."""
    monkeypatch.setattr(store, "OFFICIAL_URL", str(theirs))
    before = store.named(OFFICIAL)
    assert before is not None
    assert not before.fetched

    official = store.fetch(OFFICIAL)

    assert official.fetched
    assert official.fixed  # and it is still the one that cannot be taken away
    assert store.flows(official) == ["chat", "loop", "review"]
    assert ("official", "loop", "A flow of somebody else's.") in found()


def test_two_callers_cloning_one_place_leave_a_whole_clone_behind(
    theirs: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Two of them reach one directory, and whichever loses must not take the winner's with it.

    Both callers are real. The interface takes what every flowverse says now as it opens, and
    the flow menu fetches whatever has never been fetched as it is opened -- so on a machine
    where `official` has never been fetched, typing `/flow` is two clones of one directory,
    each begun before the other had finished. A clone that tidied up after its own failure by
    taking that directory away would be taking away the clone the other one had just written,
    and `official` would be listed as never fetched with its flows nowhere.

    One interleaving is pinned, and it is the one that used to do the damage: the second
    caller reaches git after the first has finished cloning, finds the place taken, and is
    where the old code swept the winner's work away. Left to the clock that order happens
    sometimes, which is a guard that passes nineteen runs in twenty and says nothing about the
    twentieth. The other order the race has -- the second caller arriving while the first is
    still cloning -- is not produced here and is not claimed to be: git cannot be held still
    partway through a clone from the outside.

    What is not pinned is which of the two then moves its copy into place first, and the test
    does not ask. Either way round leaves one whole clone where the flowverse is kept and one
    copy thrown away, which is the invariant; who won is not something a caller can see and is
    not something asserted here. Both threads are real and both call the real clone.
    """
    at = store.where("theirs")
    at.parent.mkdir(parents=True, exist_ok=True)
    runs = store._git
    turn = threading.Lock()
    taken: list[str] = []
    first = threading.Event()

    def after_the_other(*said: str) -> None:
        """Runs git, holding whoever gets here second until the first one is done."""
        with turn:
            second = bool(taken)
            taken.append(said[0])
        if second:
            first.wait(_PATIENCE)
            runs(*said)
            return
        runs(*said)
        first.set()

    monkeypatch.setattr(store, "_git", after_the_other)
    ready = threading.Barrier(2)
    failed: list[OSError] = []

    def clones() -> None:
        """One caller, which is whichever of the two this thread turns out to be."""
        ready.wait(_PATIENCE)
        try:
            store.clone(str(theirs), at)
        except OSError as why:
            failed.append(why)

    both = [threading.Thread(target=clones) for _ in range(2)]
    for one in both:
        one.start()
    for one in both:
        one.join(_PATIENCE)

    # Both of them really did reach git, rather than one of them finding the place taken and
    # never cloning at all -- which would be a race nobody ran.
    assert taken == ["clone", "clone"]
    # And neither is left holding an error: a clone somebody else had already finished is a
    # fetched flowverse, which is what both callers were asking for.
    assert [str(one) for one in failed] == []
    assert (at / ".git").is_dir()
    assert (at / FLOWS / "loop" / ENTRY).is_file()
    # And whichever lost took its own copy away rather than leaving it under the flowverses.
    assert list(at.parent.iterdir()) == [at]


def test_half_a_clone_in_the_way_is_taken_away_rather_than_taken_for_one(
    theirs: Path,
) -> None:
    """A run killed partway through a clone used to leave a stump under the name it wanted.

    The version that cloned straight into the place left one there, and a stump has a `.git`
    in it -- git writes its config in the first moments -- so anything that told a repository
    from a stump by looking for that directory would call it somebody else's finished clone
    and hand back a flowverse that is fetched and holds no flows. What is asked instead is
    whether git will name a commit for it, which a stump has none of.

    Swept where the move fails rather than before the clone: what is in the way at that moment
    has been shown not to be a repository, and a caller that cleared the place beforehand
    would be clearing away whatever another caller had finished writing into it.
    """
    at = store.where("theirs")
    (at / ".git").mkdir(parents=True)
    (at / ".git" / "config").write_text("[core]\n\trepositoryformatversion = 0\n")

    store.clone(str(theirs), at)

    assert (at / FLOWS / "loop" / ENTRY).is_file()
    assert store.flows(store.Flowverse("theirs", "", at, True, False)) == [
        "loop",
        "review",
    ]


def test_a_copy_a_killed_clone_left_beside_the_place_is_swept_up_by_the_next(
    theirs: Path,
) -> None:
    """The copy is written under a name nothing lists, which is a name nothing would notice.

    A clone killed partway leaves what it had written; written beside the place under a
    leading dot, that is a directory no listing of the flowverses will ever show, so nobody
    would find it to take it away. The next clone of that name is what comes by for it.

    Old ones only. A clone in flight is a directory of exactly this shape belonging to
    whoever else is cloning the same place at this moment, and sweeping one of those is the
    thing the copy-and-move is there to stop -- so a fresh one is left alone, and what goes is
    what is older than the longest a clone is given before it is called off.
    """
    import os
    import time

    under = store.under()
    under.mkdir(parents=True, exist_ok=True)
    killed = under / ".theirs.abcdef"
    killed.mkdir()
    (killed / "half-written").write_text("what git had got to\n")
    long_ago = time.time() - 10 * 60
    os.utime(killed, (long_ago, long_ago))
    live = under / ".theirs.fedcba"
    live.mkdir()

    store.clone(str(theirs), store.where("theirs"))

    assert not killed.exists()
    assert live.is_dir()  # somebody else's clone, still being written


def test_one_that_was_added_may_be_taken_away(theirs: Path) -> None:
    store.add(str(theirs))

    assert store.remove("theirs")
    assert [one.name for one in flowverses()] == [OFFICIAL, LOCAL, USER]
    assert not store.remove("theirs")  # and again is not an error, it is already gone


@pytest.mark.parametrize("name", [OFFICIAL, LOCAL, USER])
def test_none_of_the_ones_always_listed_may_be_taken_away(name: str) -> None:
    """Humanize's own, and the two directories your own flows live in."""
    with pytest.raises(ValueError, match="always here"):
        store.remove(name)


@pytest.mark.parametrize("name", [LOCAL, USER])
def test_there_is_nothing_to_fetch_for_the_flows_of_your_own(name: str) -> None:
    with pytest.raises(ValueError, match="nothing to fetch"):
        store.fetch(name)


def test_fetching_something_nobody_added_says_so() -> None:
    with pytest.raises(ValueError, match="no flowverse called"):
        store.fetch("nobodys")


def test_its_flows_are_offered_under_its_name(theirs: Path) -> None:
    """`<flowverse>/<flow>`, so that two flowverses may hold a `loop` apiece."""
    store.add(str(theirs))

    listed = found()

    assert ("theirs", "theirs/loop", "A flow of somebody else's.") in listed
    # And humanize's own are still called by a bare name.
    assert (OFFICIAL, "chat") in [(one.whose, one.name) for one in listed]


def test_a_file_beside_the_flows_that_is_not_one_is_not_offered(theirs: Path) -> None:
    """A directory of flows holds other things: what sets their tests up, what they share."""
    (theirs / FLOWS / "conftest.py").write_text("HELD = 1\n")
    _git("add", "-A", at=theirs)
    _git("commit", "-m", "not a flow", at=theirs)
    store.add(str(theirs))

    assert [one.name for one in found() if one.whose == "theirs"] == [
        "theirs/loop",
        "theirs/review",
    ]


def test_only_the_flows_directory_is_read(theirs: Path) -> None:
    """A flowverse is a repository, and a repository is not all flows.

    Reading a flow means running it, so what a repository has outside its flows directory --
    its own test suite, the file that configures it, whatever it was built with -- is not
    offered and, more to the point, is never imported to find that out.
    """
    (theirs / "tests").mkdir()
    (theirs / "tests" / "test_loop.py").write_text("raise AssertionError\n")
    (theirs / "setup_hooks.py").write_text("raise AssertionError\n")
    _git("add", "-A", at=theirs)
    _git("commit", "-m", "a repository around the flows", at=theirs)
    store.add(str(theirs))

    # Nothing raised getting here: neither file was run, though either would have said so.
    assert [one.name for one in found() if one.whose == "theirs"] == [
        "theirs/loop",
        "theirs/review",
    ]
    assert find("theirs/setup_hooks") == "theirs/setup_hooks"


def test_a_repository_with_no_flows_directory_holds_nothing(tmp_path: Path) -> None:
    """Somebody's repository that keeps its flows elsewhere, which is a thing to say."""
    where = tmp_path / "elsewhere"
    where.mkdir()
    written(where, "loop", FLOW)
    _git("init", "-b", "main", at=where)
    _git("config", "user.email", "t@example.com", at=where)
    _git("config", "user.name", "t", at=where)
    _git("add", "-A", at=where)
    _git("commit", "-m", "flows in the wrong place", at=where)

    added = store.add(str(where))

    assert added.fetched  # it is here, and it holds nothing
    assert store.flows(added) == []
    assert [one.name for one in found() if one.whose == "elsewhere"] == []


def test_a_flow_that_will_not_import_is_still_offered(theirs: Path) -> None:
    """It is a flow somebody named, and saying so where they pick it beats hiding it."""
    written(theirs / FLOWS, "broken", "import nothing_of_the_sort\n")
    _git("add", "-A", at=theirs)
    _git("commit", "-m", "a flow that will not load", at=theirs)
    store.add(str(theirs))

    assert ("theirs", "theirs/broken", "") in found()


def test_a_flow_of_a_flowverse_is_found_by_that_name(theirs: Path) -> None:
    store.add(str(theirs))

    assert find("theirs/loop") == str(
        (store.under() / "theirs" / FLOWS / "loop" / ENTRY).resolve()
    )
    # And a name nothing answers to is handed back as it was given, to be said about.
    assert find("theirs/nothing") == "theirs/nothing"


def test_a_flow_of_your_own_still_wins_a_bare_name(
    theirs: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Nearest first: a flowverse is further away than this project's own flows directory."""
    store.add(str(theirs))
    project = tmp_path / "project"
    written(project / ".humanize/flows", "loop", FLOW)
    monkeypatch.chdir(project)

    assert find("loop") == str((project / ".humanize/flows/loop" / ENTRY).resolve())
    # But the flowverse's own name for it is not a name anything of yours can stand in for.
    assert find("theirs/loop") == str(
        (store.under() / "theirs" / FLOWS / "loop" / ENTRY).resolve()
    )


def test_a_flow_from_a_flowverse_runs_by_that_name(theirs: Path) -> None:
    """Which is the whole point of fetching one: `-f theirs/loop` is a flow to run."""
    from hmz.runtime.flowing.fakes import FakeAgentDriver, run_fake

    store.add(str(theirs))
    flow = resolved("theirs/loop")

    assert [one.name for one in flow.describe().agents] == ["agent"]
    assert (
        asyncio.run(run_fake(flow, "hi", agents={"agent": FakeAgentDriver()})) == "ok"
    )


def test_a_flowverse_that_has_not_been_fetched_says_so_rather_than_that_there_is_no_file() -> (
    None
):
    """The name is right and the download has not happened, which is a different thing."""
    with pytest.raises(FlowNotFound, match="has not been fetched yet"):
        resolved(f"{OFFICIAL}/rlar")


def test_a_bare_name_says_so_too_when_nothing_has_been_fetched(theirs: Path) -> None:
    """Humanize's own flows are a bare name now, so this is the first run's own failure.

    `-f rlar` on a machine that has fetched nothing is a name that is right and a download
    that has not happened, which "no flow to read" is the least useful thing to say about.
    """
    store.add(str(theirs))  # one that is here, so the one that is not is named alone

    with pytest.raises(
        FlowNotFound, match=f"the {OFFICIAL} flowverse has not been fetched yet"
    ):
        resolved("rlar")


def test_a_clone_somebody_has_written_into_says_so(theirs: Path) -> None:
    """Which is what anything fetching without being asked to has to ask first.

    A fetch resets the clone to what the repository says now, so what is written into one goes
    with it. Tracked files only: `reset --hard` leaves an untracked file alone, and reading a
    flow writes a `__pycache__` beside it that would otherwise make every repository without a
    `.gitignore` look edited for good.
    """
    added = store.add(str(theirs))
    (held,) = store.holds(added)

    assert not store.edited(added.at)

    (held / "loop" / ENTRY).write_text(FLOW.replace("A flow", "Mine now"))
    assert store.edited(added.at)

    (held / "__pycache__").mkdir()
    (held / "__pycache__" / "loop.pyc").write_bytes(b"\x00")
    (held / "loop" / ENTRY).write_text(FLOW)
    assert not store.edited(added.at)  # nothing a fetch would take back


def test_a_directory_that_is_not_a_clone_has_nothing_a_fetch_could_take_away() -> None:
    """There being no fetch: `edited` is asked of a path and answers about one."""
    at = store.under() / "nobodys"
    at.mkdir(parents=True)

    assert not store.edited(at)


def test_a_flowverse_may_hold_a_flow_that_is_one_file(theirs: Path) -> None:
    """A flow is a module, and both shapes of one are offered under the flowverse's name."""
    (theirs / FLOWS / "alone.py").write_text(FLOW)
    _git("add", "-A", at=theirs)
    _git("commit", "-m", "one that is a file", at=theirs)
    store.add(str(theirs))

    named = [one.name for one in found() if one.whose == "theirs"]

    assert named == ["theirs/alone", "theirs/loop", "theirs/review"]
    assert find("theirs/alone") == str(
        (store.under() / "theirs" / FLOWS / "alone.py").resolve()
    )
