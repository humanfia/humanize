"""The flows there are and the places they come from, reached through the SDK.

A command line, the interface and a daemon each ask this rather than the modules behind it,
so what is checked here is that all three would get the same answer: a flowverse added from
here is one whose index the listing reads a moment later, a flow installed out of it is one it
offers, a flow's name resolves to the file it is written in, and the handful of answers every
way in needs -- what a flow takes, what it says about itself, whether it can be picked up --
come off the flow rather than off a second copy of the facts.

The index fetched from, and the repository its releases live in, are git repositories under
`tmp_path`. Nothing here reaches a network, and nothing starts a coding agent.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from hmz.flows import FlowNotFound
from hmz.runtime.flowing import (
    ENTRY,
    LOCAL,
    OFFICIAL,
    USER,
    Index,
    Update,
)
from hmz.runtime.flowing import verses as store
from hmz.sdk import Hmz
from tests.flows.indexes import committed, listed, release
from tests.flows.kit import SHIPPED
from tests.stubs import written

if TYPE_CHECKING:
    from pathlib import Path

#: A flow, as short as one can be, that says a line about itself and takes one agent.
FLOW = '''"""A flow of somebody else's."""

from hmz.flows import Agent, AgentCollection, EnvCollection, FlowParams, LocalEnv, flow


class Agents(AgentCollection):
    agent: Agent


class Envs(EnvCollection):
    here: LocalEnv


@flow(agents=Agents, envs=Envs, params=FlowParams)
async def run(task, *, agents, envs, params, ctx):
    session = await agents["agent"].spawn(env=envs["here"])
    await agents["agent"].run(task, session=session)
'''

#: One that says it can be picked up where the last run of it left off, and takes a param.
KEEPS = '''"""A flow that is picked up."""

from hmz.flows import Agent, AgentCollection, EnvCollection, FlowParams, flow


class Agents(AgentCollection):
    agent: Agent


class Params(FlowParams):
    rounds: int = 1


@flow(agents=Agents, envs=EnvCollection, params=Params, resumable=True)
async def run(task, *, agents, envs, params, ctx):
    pass
'''


@pytest.fixture
def code(tmp_path: Path) -> tuple[str, str]:
    """The repository the releases here live in: two flows, a directory apiece.

    Returns:
      Where it is fetched from, and the commit every release here was cut from.
    """
    where = tmp_path / "code"
    written(where, "loop", FLOW)
    written(where, "second", FLOW)
    return f"file://{where}", committed(where, "two flows")


@pytest.fixture
def theirs(tmp_path: Path, code: tuple[str, str]) -> Path:
    """An index of one release of one flow, to be fetched from."""
    url, commit = code
    where = tmp_path / "theirs"
    listed(where, release("loop", "0.1.0", url, commit, subdir="loop"))
    committed(where, "one release")
    return where


@pytest.fixture
def project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A project with two flows of its own, stood in."""
    where = tmp_path / "project"
    flows = where / ".hmz" / "flows"
    flows.mkdir(parents=True)
    written(flows, "mine", FLOW)
    written(flows, "kept", KEEPS)
    monkeypatch.chdir(where)
    return where


# ------------------------------------------------------------ where flows come from


def test_the_places_are_listed_in_the_order_their_flows_are_offered() -> None:
    assert [one.name for one in Hmz().verses.all()] == [OFFICIAL, LOCAL, USER]


def test_a_name_is_looked_up_in_a_different_order_than_the_flows_are_offered_in() -> (
    None
):
    """Nearest first: this project's own flows answer to a name before the package's do."""
    verses = Hmz().verses

    assert next(one.name for one in verses.nearest()) == LOCAL
    assert {one.name for one in verses.nearest()} == {one.name for one in verses.all()}


def test_a_place_is_found_by_name_and_a_name_none_answers_to_is_nothing() -> None:
    verses = Hmz().verses

    found = verses.find(OFFICIAL)

    assert found is not None
    assert found.name == OFFICIAL
    assert verses.find("not-a-flowverse") is None


def test_a_place_added_here_is_one_whose_index_the_listing_reads_a_moment_later(
    theirs: Path,
) -> None:
    """What it lists is to install, and none of it is a flow to run until it is."""
    verses = Hmz().verses

    added = verses.add(str(theirs), "theirs")

    assert added.name == "theirs"
    assert added.fetched
    assert "theirs" in [one.name for one in verses.all()]
    assert verses.index("theirs").flows() == ["loop"]
    assert verses.holds(added) == []
    assert "theirs/loop" not in [one.name for one in Hmz().flows.all()]


def test_a_flow_installed_here_is_one_the_listing_offers_a_moment_later(
    theirs: Path,
) -> None:
    verses = Hmz().verses
    added = verses.add(str(theirs), "theirs")

    (done,) = verses.install("theirs/loop")

    assert (done.verse, done.name, done.version) == ("theirs", "loop", "0.1.0")
    assert verses.installed() == [done]
    assert [one.name for one in verses.holds(added)] == ["theirs/loop"]
    assert "theirs/loop" in [one.name for one in Hmz().flows.all()]
    assert Hmz().flows.about("theirs/loop") == "A flow of somebody else's."


def test_a_flow_uninstalled_here_is_gone_and_uninstalling_it_twice_says_so(
    theirs: Path,
) -> None:
    verses = Hmz().verses
    verses.add(str(theirs), "theirs")
    verses.install("theirs/loop")

    assert verses.uninstall("theirs/loop")

    assert verses.installed() == []
    assert "theirs/loop" not in [one.name for one in Hmz().flows.all()]
    assert not verses.uninstall("theirs/loop")


def test_a_bare_name_installs_one_of_humanize_s_own(
    theirs: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """As a bare name runs one: humanize's own flows are the ones nobody has to name."""
    monkeypatch.setattr(store, "OFFICIAL_URL", str(theirs))
    verses = Hmz().verses
    verses.fetch(OFFICIAL)

    (done,) = verses.install("loop")

    assert (done.verse, done.called) == (OFFICIAL, "loop")
    assert "loop" in [one.name for one in Hmz().flows.all()]
    assert verses.uninstall("loop")
    assert "loop" not in [one.name for one in Hmz().flows.all()]


def test_installing_what_an_index_does_not_list_is_refused(theirs: Path) -> None:
    verses = Hmz().verses
    verses.add(str(theirs), "theirs")

    with pytest.raises(ValueError, match="lists no flow called nothing"):
        verses.install("theirs/nothing")
    with pytest.raises(ValueError, match=r"lists no release 9\.9\.9 of loop"):
        verses.install("theirs/loop", "9.9.9")


def test_a_place_that_is_not_an_index_lists_nothing_to_install() -> None:
    verses = Hmz().verses

    assert verses.index(LOCAL) == Index(LOCAL)
    assert verses.index(OFFICIAL) == Index(OFFICIAL)  # not fetched yet
    assert verses.index("not-a-flowverse") == Index("not-a-flowverse")


def test_a_place_is_kept_in_the_directory_this_says_whether_or_not_it_was_fetched() -> (
    None
):
    verses = Hmz().verses

    at = verses.where("theirs")

    assert not at.exists()
    assert at.name == "theirs"


def test_a_place_fetched_again_lists_what_was_published_and_runs_what_it_ran(
    theirs: Path, code: tuple[str, str]
) -> None:
    """A newer release fetched is an update to offer, not one to take."""
    url, commit = code
    verses = Hmz().verses
    verses.add(str(theirs), "theirs")
    (loop,) = verses.install("theirs/loop")
    listed(
        theirs,
        release("loop", "0.2.0", url, commit, subdir="loop"),
        release("second", "0.1.0", url, commit, subdir="second"),
    )
    committed(theirs, "two more releases")
    assert verses.updates() == []  # published, and not fetched yet

    again = verses.fetch("theirs")

    assert verses.index("theirs").flows() == ["loop", "second"]
    assert verses.updates() == [Update(loop, "0.2.0")]
    assert [one.name for one in verses.holds(again)] == ["theirs/loop"]
    assert verses.installed() == [loop]


def test_a_place_taken_away_is_gone_and_taking_it_away_twice_says_so(
    theirs: Path,
) -> None:
    verses = Hmz().verses
    verses.add(str(theirs), "theirs")

    assert verses.remove("theirs")

    assert verses.find("theirs") is None
    assert not verses.remove("theirs")


def test_the_ones_that_are_always_there_cannot_be_taken_away() -> None:
    with pytest.raises(ValueError, match="not one to take away"):
        Hmz().verses.remove(OFFICIAL)


def test_a_place_that_has_not_been_fetched_holds_nothing_rather_than_failing() -> None:
    """Except for the flows humanize keeps in the package, which are there either way."""
    verses = Hmz().verses
    official = verses.find(OFFICIAL)
    assert official is not None

    assert not official.fetched
    held = [one.name for one in verses.holds(official)]
    assert "chat" in held
    assert {one.partition(":")[0] for one in held} == set(SHIPPED)


def test_what_was_signed_into_a_url_is_not_what_is_printed_of_it() -> None:
    plain = Hmz().verses.plain("https://someone:secret@example.invalid/theirs.git")

    assert "secret" not in plain
    assert "example.invalid/theirs.git" in plain


# ------------------------------------------------------------------- the flows


def test_every_flow_there_is_to_run_is_offered_by_the_name_dash_f_takes(
    project: Path,
) -> None:
    offered = Hmz().flows.all()

    assert ("local", "local/mine") in [(one.whose, one.name) for one in offered]
    assert "chat" in [one.name for one in offered]


def test_a_flow_s_name_is_the_file_it_is_written_in(project: Path) -> None:
    found = Hmz().flows.find("mine")

    assert found == str((project / ".hmz/flows/mine" / ENTRY).resolve())


def test_a_name_nothing_answers_to_comes_back_as_the_name_it_was_asked_by(
    project: Path,
) -> None:
    """Rather than as an exception: whatever asked hears the name, and says so itself."""
    assert Hmz().flows.find("definitely-not-a-flow") == "definitely-not-a-flow"


def test_the_line_a_flow_says_about_itself_is_read_off_the_flow(project: Path) -> None:
    assert Hmz().flows.about("mine") == "A flow of somebody else's."


def test_what_a_flow_declares_is_read_off_the_flow(project: Path) -> None:
    """Its roles -- the ones the runtime fills marked -- its params, and whether it resumes."""
    flows = Hmz().flows

    mine = flows.declared("mine")

    assert [(one.name, one.auto) for one in mine.agents] == [("agent", False)]
    assert [(one.name, one.auto) for one in mine.envs] == [("here", True)]
    assert "rounds" in flows.declared("kept").params.model_fields
    assert mine.params.model_fields == {}


def test_a_flow_that_is_not_there_is_said_to_be_as_the_flow_api_says_it(
    project: Path,
) -> None:
    with pytest.raises(FlowNotFound):
        Hmz().flows.declared("definitely-not-a-flow")


def test_whether_a_flow_can_be_picked_up_is_what_the_flow_said(project: Path) -> None:
    flows = Hmz().flows

    assert flows.resumes("kept")
    assert not flows.resumes("mine")


def test_a_flow_forked_into_this_project_is_offered_under_the_name_it_already_had(
    project: Path,
) -> None:
    """Yours are looked in first, so from then on that name means the copy."""
    flows = Hmz().flows

    where = flows.fork("chat")

    # Spelled as this project's own flows are spelled, which is from the project itself.
    assert where == ".hmz/flows/chat"
    assert (project / ".hmz" / "flows" / "chat").is_dir()
    assert flows.find("chat").startswith(str(project))


def test_forking_a_name_nothing_of_which_is_a_flow_is_refused(project: Path) -> None:
    with pytest.raises(ValueError, match="no flow called"):
        Hmz().flows.fork("definitely-not-a-flow")


def test_forking_over_a_flow_of_your_own_is_refused(project: Path) -> None:
    """A copy already there is one to edit, run or take away rather than to write over."""
    flows = Hmz().flows
    flows.fork("chat")

    with pytest.raises(ValueError, match="already a flow of your own"):
        flows.fork("chat")


def test_nothing_is_running_outside_a_run(project: Path) -> None:
    assert Hmz().flows.running() == ()


def test_the_places_flows_come_from_are_reached_from_the_flows_as_well() -> None:
    """One object, so that whatever holds the flows does not have to hold a second thing."""
    held = Hmz()

    assert [one.name for one in held.flows.verses.all()] == [
        one.name for one in held.verses.all()
    ]
