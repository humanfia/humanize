"""Where flows come from when they come from somewhere else.

A flowverse is an index: somebody's repository of `flows/<flow>/<version>/flow.yaml`, cloned
under humanize's home and listed under the name it is kept there. It holds no code, so what it
lists is offered to install rather than to run, and what runs is what somebody installed out of
it, offered under the flowverse's name. One of them is always there whatever has been fetched
-- `official`, which is humanize's own: the flows in the package, together with whatever was
installed out of humanize's index -- so what is checked here is that the list says what there is
rather than what has been downloaded, that an index's releases are not flows until somebody
installs one, that both halves of humanize's own are offered under the one name, that fetching
an index twice is a fetch rather than a merge, that taking one away takes what was installed
out of it, and that the ones that are always there cannot be taken away.

Every repository here is one the test made a moment ago under its own directory: an index, and
the repository its releases live in. Nothing reaches a network.
"""

from __future__ import annotations

import asyncio
import os
import threading
import time
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
    fork,
    found,
    offered,
    resolved,
)
from hmz.runtime.flowing import verses as store
from hmz.runtime.flowing.index import (
    RECORD,
    RELEASE,
    index,
    install,
    installed,
    kept,
    uninstall,
)
from tests.flows.indexes import committed, listed, release
from tests.stubs import written

if TYPE_CHECKING:
    from collections.abc import Mapping
    from pathlib import Path

#: A flow, as short as one can be: where it comes from is what is checked, not what it does.
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


@pytest.fixture
def code(tmp_path: Path) -> tuple[str, str]:
    """The repository the releases listed here live in: two flows, each a directory.

    Returns:
      Where it is fetched from, and the commit every release here was cut from.
    """
    at = tmp_path / "code"
    written(at, "loop", FLOW)
    written(at, "review", FLOW)
    return f"file://{at}", committed(at, "two flows")


def _releases(code: tuple[str, str], *names: str) -> list[dict[str, object]]:
    """The first release of each of these flows, as an index lists it."""
    url, commit = code
    return [release(name, "0.1.0", url, commit, subdir=name) for name in names]


@pytest.fixture
def theirs(tmp_path: Path, code: tuple[str, str]) -> Path:
    """An index of two flows, and the repository around it that is not one of them."""
    at = tmp_path / "theirs"
    listed(at, *_releases(code, "loop", "review"))
    # Nothing else the repository is made of is read, and none of it is code to run.
    (at / "README.md").write_text("# theirs\n", encoding="utf-8")
    (at / "conftest.py").write_text("raise AssertionError\n", encoding="utf-8")
    (at / FLOWS / "loop" / "0.1.0" / ENTRY).write_text(
        "raise AssertionError\n", encoding="utf-8"
    )
    committed(at, "two flows")
    return at


def _offered(whose: str) -> list[str]:
    """What one flowverse offers to run, by the name each is offered under."""
    return [one.name for one in found() if one.whose == whose]


def _published(at: Path, *releases: Mapping[str, object]) -> None:
    """More releases in an index, committed -- and not fetched until somebody fetches."""
    listed(at, *releases)
    committed(at, "more releases")


# ------------------------------------------------------------------- the ones always there


def test_humanize_s_own_is_always_there_and_is_never_a_fetch_away() -> None:
    """Listed first, listed from the start, and not one anybody has to add."""
    listed_ = flowverses()

    assert listed_[0].name == OFFICIAL
    assert listed_[0].fixed
    assert listed_[0].url.endswith("humanfia/flowverse")
    assert [one.name for one in listed_] == [OFFICIAL, LOCAL, USER]


def test_humanize_s_own_flows_are_read_from_the_package_and_from_what_was_installed() -> (
    None
):
    """The package's first: a name both hold is the one that is always there."""
    one = store.named(OFFICIAL)
    assert one is not None

    assert store.holds(one) == (BUILTIN_AT, kept(OFFICIAL))
    assert "chat" in store.flows(one)
    assert find("chat") == str((BUILTIN_AT / "chat" / ENTRY).resolve())


def test_the_official_one_offers_the_package_s_own_before_it_is_fetched() -> None:
    """Or a list of what there is to run would be a list of what has been downloaded."""
    (official,) = [one for one in flowverses() if one.name == OFFICIAL]

    assert not official.fetched
    # The half that is in the package is there whatever has been downloaded, and nothing is
    # raised about the half that has not been.
    assert store.flows(official) == offered(BUILTIN_AT)
    assert not index(official).releases


@pytest.mark.parametrize("name", [OFFICIAL, LOCAL, USER])
def test_none_of_the_ones_always_listed_may_be_taken_away(name: str) -> None:
    """Humanize's own, and the two directories your own flows live in."""
    with pytest.raises(ValueError, match="always here"):
        store.remove(name)


@pytest.mark.parametrize("name", [LOCAL, USER])
def test_there_is_nothing_to_fetch_for_the_flows_of_your_own(name: str) -> None:
    with pytest.raises(ValueError, match="nothing to fetch"):
        store.fetch(name)


@pytest.mark.parametrize("name", [OFFICIAL, LOCAL, USER])
def test_none_of_the_ones_always_listed_may_be_added_over(
    theirs: Path, name: str
) -> None:
    with pytest.raises(ValueError, match=name):
        store.add(str(theirs), name)


# ------------------------------------------------------------------- adding, fetching, removing


@pytest.mark.parametrize("said", ["..", "one/two", "", ".", "/absolute"])
def test_a_name_that_is_not_one_directory_is_refused(said: str) -> None:
    """A flowverse is a directory under humanize's home, and a name that climbs out is not one."""
    with pytest.raises(ValueError, match="not a flowverse name"):
        store.where(said)


def test_one_that_was_added_is_listed_under_the_name_it_was_kept_under(
    theirs: Path,
) -> None:
    added = store.add(str(theirs))

    # The repository's own name, nobody having said otherwise.
    assert added.name == "theirs"
    assert added.fetched
    assert added.url == str(theirs)  # where it came from, as its own clone says
    assert not added.fixed
    assert [one.name for one in flowverses()] == [OFFICIAL, "theirs", LOCAL, USER]
    # What it lists, which is releases to install and not yet flows to run.
    assert index(added).flows() == ["loop", "review"]
    assert store.flows(added) == []


def test_it_may_be_called_something_else_here(theirs: Path) -> None:
    """Two people's repositories may share a name; the name it is kept under is yours."""
    added = store.add(str(theirs), "mine")

    assert added.name == "mine"
    assert (store.under() / "mine" / FLOWS / "loop" / "0.1.0" / RELEASE).is_file()
    assert index("mine").flows() == ["loop", "review"]


def test_adding_one_twice_is_refused(theirs: Path) -> None:
    store.add(str(theirs))

    with pytest.raises(ValueError, match="already a flowverse called"):
        store.add(str(theirs))


def test_a_repository_that_is_not_there_says_so(tmp_path: Path) -> None:
    """Said where it was asked for, rather than left as a flowverse with nothing in it."""
    with pytest.raises(OSError, match=r"git|repository"):
        store.add(str(tmp_path / "nowhere"))

    assert [one.name for one in flowverses()] == [OFFICIAL, LOCAL, USER]


def test_fetching_something_nobody_added_says_so() -> None:
    with pytest.raises(ValueError, match="no flowverse called"):
        store.fetch("nobodys")


def test_fetching_takes_what_the_index_says_now_and_leaves_what_runs_alone(
    theirs: Path, code: tuple[str, str]
) -> None:
    """An index is a copy of somebody's repository, so a fetch is what it says now.

    And what it says is what may be installed: what was installed out of it is what runs,
    and a newer release listed is an update to offer rather than one to take.
    """
    store.add(str(theirs))
    (before,) = install("theirs", "loop")
    url, commit = code
    _published(
        theirs,
        release("loop", "0.2.0", url, commit, subdir="loop"),
        *_releases(code, "third"),
    )

    again = store.fetch("theirs")

    assert index(again).flows() == ["loop", "review", "third"]
    assert [one.version for one in index(again).versions("loop")] == ["0.2.0", "0.1.0"]
    assert installed() == [before]
    assert _offered("theirs") == ["theirs/loop"]


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
    assert index(OFFICIAL).flows() == ["loop", "review"]
    # Fetched is not installed: the package's own are still all it offers to run.
    assert store.flows(official) == offered(BUILTIN_AT)


def test_one_that_was_added_may_be_taken_away(theirs: Path) -> None:
    store.add(str(theirs))

    assert store.remove("theirs")
    assert [one.name for one in flowverses()] == [OFFICIAL, LOCAL, USER]
    assert not store.remove("theirs")  # and again is not an error, it is already gone


def test_taking_one_away_takes_away_what_was_installed_out_of_it(theirs: Path) -> None:
    """Nothing else would ever reach them: an installed flow is offered under its index's name.

    So a flow left behind would be one nobody could update, uninstall, or tell was there.
    """
    store.add(str(theirs))
    install("theirs", "loop")
    install("theirs", "review")

    assert store.remove("theirs")

    assert not kept("theirs").exists()
    assert installed() == []
    assert _offered("theirs") == []
    assert find("theirs/loop") == "theirs/loop"


# ------------------------------------------------------------------- racing clones


def test_two_callers_cloning_one_place_leave_a_whole_clone_behind(
    theirs: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Two of them reach one directory, and whichever loses must not take the winner's with it.

    Both callers are real. The interface takes what every index says now as it opens, and the
    flow menu fetches whatever has never been fetched as it is opened -- so on a machine where
    `official` has never been fetched, opening `/flows` is two clones of one directory, each
    begun before the other had finished. A clone that tidied up after its own failure by
    taking that directory away would be taking away the clone the other one had just written,
    and `official` would be listed as never fetched with its index nowhere.

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
    assert (at / FLOWS / "loop" / "0.1.0" / RELEASE).is_file()
    # And whichever lost took its own copy away rather than leaving it under the flowverses.
    assert list(at.parent.iterdir()) == [at]


def test_half_a_clone_in_the_way_is_taken_away_rather_than_taken_for_one(
    theirs: Path,
) -> None:
    """A run killed partway through a clone used to leave a stump under the name it wanted.

    The version that cloned straight into the place left one there, and a stump has a `.git`
    in it -- git writes its config in the first moments -- so anything that told a repository
    from a stump by looking for that directory would call it somebody else's finished clone
    and hand back a flowverse that is fetched and lists nothing. What is asked instead is
    whether git will name a commit for it, which a stump has none of.

    Swept where the move fails rather than before the clone: what is in the way at that moment
    has been shown not to be a repository, and a caller that cleared the place beforehand
    would be clearing away whatever another caller had finished writing into it.
    """
    at = store.where("theirs")
    (at / ".git").mkdir(parents=True)
    (at / ".git" / "config").write_text("[core]\n\trepositoryformatversion = 0\n")

    store.clone(str(theirs), at)

    assert (at / FLOWS / "loop" / "0.1.0" / RELEASE).is_file()
    assert index("theirs").flows() == ["loop", "review"]


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


# ------------------------------------------------------------------- listed, installed, run


def test_what_an_index_lists_is_not_a_flow_to_run_until_it_is_installed(
    theirs: Path,
) -> None:
    """An index is manifests, and nothing in it is ever imported.

    Its repository has a `conftest.py` that raises and an `__init__.py` beside a manifest that
    raises, and neither is run getting here: listing an index is reading YAML.
    """
    store.add(str(theirs))

    assert _offered("theirs") == []
    assert find("theirs/loop") == "theirs/loop"
    assert find("loop") == "loop"


def test_an_installed_flow_is_offered_under_the_name_of_the_index_it_came_out_of(
    theirs: Path,
) -> None:
    """`<flowverse>/<flow>`, so that two flowverses may hold a `loop` apiece."""
    store.add(str(theirs))

    install("theirs", "loop")

    assert ("theirs", "theirs/loop", "A flow of somebody else's.") in found()
    assert _offered("theirs") == ["theirs/loop"]  # and not what it did not install
    assert find("theirs/loop") == str((kept("theirs") / "loop" / ENTRY).resolve())
    # And humanize's own are still called by a bare name.
    assert (OFFICIAL, "chat") in [(one.whose, one.name) for one in found()]


def test_an_installed_flow_runs_by_that_name(theirs: Path) -> None:
    """Which is the whole point of installing one: `-f theirs/loop` is a flow to run."""
    from hmz.runtime.flowing.fakes import FakeAgentDriver, run_fake

    store.add(str(theirs))
    install("theirs", "loop")
    flow = resolved("theirs/loop")

    assert [one.name for one in flow.describe().agents] == ["agent"]
    assert (
        asyncio.run(run_fake(flow, "hi", agents={"agent": FakeAgentDriver()})) == "ok"
    )


def test_uninstalling_one_takes_it_away_from_everything_that_offers_it(
    theirs: Path,
) -> None:
    store.add(str(theirs))
    install("theirs", "loop")

    assert uninstall("theirs", "loop")

    assert _offered("theirs") == []
    assert find("theirs/loop") == "theirs/loop"
    with pytest.raises(FlowNotFound, match="not installed"):
        resolved("theirs/loop")
    assert not uninstall("theirs", "loop")


def test_one_installed_out_of_humanize_s_own_is_said_the_same_way_as_the_package_s(
    theirs: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """One name for humanize's flows: which of its two places one is in is humanize's business.

    So `chat`, which is in the package, and `loop`, which was installed out of humanize's
    index, are both a bare name -- and `official/` in front of either is the spelling that
    says whose it is, which goes on resolving for both.
    """
    monkeypatch.setattr(store, "OFFICIAL_URL", str(theirs))
    store.fetch(OFFICIAL)

    (done,) = install(OFFICIAL, "loop")

    assert done.called == "loop"
    assert _offered(OFFICIAL) == sorted([*offered(BUILTIN_AT), "loop"])
    assert find("official/chat") == str((BUILTIN_AT / "chat" / ENTRY).resolve())
    assert find("loop") == str((kept(OFFICIAL) / "loop" / ENTRY).resolve())
    assert find("official/loop") == find("loop")


def test_the_package_s_own_wins_a_name_an_install_also_holds(
    theirs: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The half that is always there beats the half an install could change.

    An index may not list one of those names at all, so the only way one is there is by hand
    -- and it is still not the flow that name means.
    """
    monkeypatch.setattr(store, "OFFICIAL_URL", str(theirs))
    store.fetch(OFFICIAL)
    written(kept(OFFICIAL), "chat", FLOW)

    assert _offered(OFFICIAL).count("chat") == 1
    assert find("chat") == str((BUILTIN_AT / "chat" / ENTRY).resolve())
    assert find("official/chat") == find("chat")


def test_a_flow_of_your_own_still_wins_a_bare_name(
    theirs: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Nearest first: an installed flow is further away than this project's own flows."""
    monkeypatch.setattr(store, "OFFICIAL_URL", str(theirs))
    store.fetch(OFFICIAL)
    install(OFFICIAL, "loop")
    store.add(str(theirs))
    install("theirs", "review")
    project = tmp_path / "project"
    written(project / ".humanize/flows", "loop", FLOW)
    written(project / ".humanize/flows", "review", FLOW)
    monkeypatch.chdir(project)

    assert find("loop") == str((project / ".humanize/flows/loop" / ENTRY).resolve())
    assert find("review") == str((project / ".humanize/flows/review" / ENTRY).resolve())
    # But a flowverse's own name for one is not a name anything of yours can stand in for.
    assert find("official/loop") == str((kept(OFFICIAL) / "loop" / ENTRY).resolve())
    assert find("theirs/review") == str((kept("theirs") / "review" / ENTRY).resolve())


def test_an_installed_flow_forked_is_yours_and_says_nothing_of_where_it_came_from(
    theirs: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A copy carrying the record would say it was a release of somebody else's."""
    store.add(str(theirs))
    install("theirs", "loop")
    monkeypatch.chdir(tmp_path)

    at = fork("theirs/loop")

    assert at == ".humanize/flows/loop"
    assert sorted(one.name for one in (tmp_path / at).iterdir()) == [ENTRY]
    assert find("loop") == str((tmp_path / at / ENTRY).resolve())
    assert (
        kept("theirs") / "loop" / RECORD
    ).is_file()  # the installed one is as it was


# ------------------------------------------------------------------- a name not there


def test_a_flow_an_index_lists_and_nobody_installed_says_how_to_have_it(
    theirs: Path,
) -> None:
    """The name is right, and the flow is one install away, which is a different thing."""
    store.add(str(theirs))

    with pytest.raises(
        FlowNotFound,
        match=r"^theirs/loop: not installed -- install it from /flow \(flowverse theirs\)$",
    ):
        resolved("theirs/loop")
    with pytest.raises(
        FlowNotFound,
        match=r"^review: not installed -- install it from /flow \(flowverse theirs\)$",
    ):
        resolved("review")


def test_a_flowverse_that_has_not_been_fetched_says_so_rather_than_that_there_is_no_file() -> (
    None
):
    """The name may be right and the download has not happened, which is a different thing."""
    with pytest.raises(
        FlowNotFound,
        match=r"^official/nobody_wrote_this: the official flowverse has not been fetched "
        r"yet -- fetch it from /flow$",
    ):
        resolved(f"{OFFICIAL}/nobody_wrote_this")


def test_a_bare_name_says_so_too_when_humanize_s_own_has_not_been_fetched(
    theirs: Path,
) -> None:
    """Humanize's own flows are a bare name, so this is the first run's own failure.

    `-f` with one of them on a machine that has fetched nothing is a name that may well be
    right and a download that has not happened, which "no flow to read" is the least useful
    thing to say about.
    """
    store.add(str(theirs))  # one that is here, so the one that is not is named alone

    with pytest.raises(
        FlowNotFound, match=f"the {OFFICIAL} flowverse has not been fetched yet"
    ):
        resolved("nobody_wrote_this")


def test_a_name_no_fetched_index_lists_is_just_not_there(
    theirs: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(store, "OFFICIAL_URL", str(theirs))
    store.fetch(OFFICIAL)

    with pytest.raises(FlowNotFound, match="no flow is called") as raised:
        resolved("nobody_wrote_this")
    assert "fetched" not in str(raised.value)
    assert "installed" not in str(raised.value)


# ------------------------------------------------------------------- written into


def test_a_clone_somebody_has_written_into_says_so(theirs: Path) -> None:
    """Which is what anything fetching without being asked to has to ask first.

    A fetch resets the clone to what the repository says now, so what is written into one goes
    with it -- somebody writing the manifest of their next release into an index they added
    would lose it. Tracked files only: `reset --hard` leaves an untracked file alone, and so
    does a fetch.
    """
    added = store.add(str(theirs))
    manifest = added.at / FLOWS / "loop" / "0.1.0" / RELEASE

    assert not store.edited(added.at)

    said = manifest.read_text()
    manifest.write_text(said.replace("loop", "loop  # mine now", 1))
    assert store.edited(added.at)

    manifest.write_text(said)
    (added.at / FLOWS / "loop" / "0.2.0").mkdir()
    (added.at / FLOWS / "loop" / "0.2.0" / RELEASE).write_text("name: loop\n")
    assert not store.edited(added.at)  # nothing a fetch would take back


def test_a_directory_that_is_not_a_clone_has_nothing_a_fetch_could_take_away() -> None:
    """There being no fetch: `edited` is asked of a path and answers about one."""
    at = store.under() / "nobodys"
    at.mkdir(parents=True)

    assert not store.edited(at)
