"""What a module of flows offers, what each flow in it is called, and how one is asked for.

A flow is a function marked with `@flow`, and a flow directory is a module of them. The one a
bare name means is the one named after the directory, else the only one it does not hide; it is
listed under the directory's own name, and every other flow the module shows is listed as
`<flow>:<name>` -- which is also how it is asked for. A hidden flow is listed nowhere, and still
answers to its name.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from hmz.flows import FlowNotFound
from hmz.runtime.flowing import ENTRY, LOCAL, about, find, found, resolved
from tests.stubs import written

if TYPE_CHECKING:
    from pathlib import Path

#: What every flow here declares, which is nothing: what is checked is what each is called.
_HEAD = """
from hmz.flows import AgentCollection, EnvCollection, FlowParams, flow


class Nothing(AgentCollection):
    pass


class Nowhere(EnvCollection):
    pass
"""

#: A module named `three` whose three phases are three flows, one of them named for it.
THREE = (
    '"""Three phases of one thing, which are three things to run."""\n'
    + _HEAD
    + '''

@flow(agents=Nothing, envs=Nowhere, params=FlowParams, name="gen-idea")
async def first_pass(task, *, agents, envs, params, ctx):
    """Opens a loose idea into a draft."""
    return "idea"


@flow(agents=Nothing, envs=Nowhere, params=FlowParams, description="builds it")
async def three(task, *, agents, envs, params, ctx):
    """A docstring the decorator was told to say something else instead of."""
    return "three"


@flow(agents=Nothing, envs=Nowhere, params=FlowParams, hidden=True)
async def engine(task, *, agents, envs, params, ctx):
    """What the others call, and nobody picks."""
    return "engine"


async def run(task):
    """Called run, marked with nothing, and so not a flow at all."""
'''
)

#: A module that is one flow, under a function name that says nothing about it.
ONE = (
    '"""Just the one, and it says what it does here."""\n'
    + _HEAD
    + """

@flow(agents=Nothing, envs=Nowhere, params=FlowParams)
async def whatever_it_is_called(task, *, agents, envs, params, ctx):
    return "one"
"""
)

#: A module of two visible flows, neither named for its directory.
TWO = (
    '"""Two, and neither is the directory\'s own."""\n'
    + _HEAD
    + '''

@flow(agents=Nothing, envs=Nowhere, params=FlowParams)
async def left(task, *, agents, envs, params, ctx):
    """Goes left."""
    return "left"


@flow(agents=Nothing, envs=Nowhere, params=FlowParams)
async def right(task, *, agents, envs, params, ctx):
    """Goes right."""
    return "right"
'''
)


@pytest.fixture
def mine(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """This project's own flows directory, with the project as where things are run from."""
    monkeypatch.chdir(tmp_path)
    return tmp_path / ".humanize" / "flows"


def _local() -> list[tuple[str, str]]:
    """What this project's own flows are listed as, and what each says it does."""
    return [(one.name, one.about) for one in found() if one.whose == LOCAL]


def test_a_module_lists_its_own_flow_bare_and_the_rest_by_name(mine: Path) -> None:
    written(mine, "three", THREE)

    assert _local() == [
        ("local/three", "builds it"),
        ("local/three:gen-idea", "Opens a loose idea into a draft."),
    ]


def test_a_module_of_one_flow_lists_it_under_the_directory(mine: Path) -> None:
    """Whatever the function is called; and the module's docstring says what it does."""
    written(mine, "one", ONE)

    assert _local() == [("local/one", "Just the one, and it says what it does here.")]
    assert resolved("one").name == "whatever_it_is_called"


def test_two_flows_neither_named_for_the_module_are_each_listed_by_name(
    mine: Path,
) -> None:
    written(mine, "two", TWO)

    assert _local() == [
        ("local/two:left", "Goes left."),
        ("local/two:right", "Goes right."),
    ]


def test_a_bare_name_that_means_no_one_flow_says_which_there_are(mine: Path) -> None:
    written(mine, "two", TWO)

    with pytest.raises(FlowNotFound, match="left, right"):
        resolved("two")
    assert resolved("two:right").name == "right"


def test_a_hidden_flow_is_listed_nowhere_and_still_answers_to_its_name(
    mine: Path,
) -> None:
    written(mine, "three", THREE)

    assert all("engine" not in name for name, _ in _local())
    assert resolved("three:engine").hidden


def test_which_one_was_asked_for_is_the_half_after_the_colon(mine: Path) -> None:
    written(mine, "three", THREE)

    assert resolved("three:gen-idea").name == "gen-idea"
    assert resolved("local/three:gen-idea").name == "gen-idea"
    assert resolved("three").name == "three"
    assert about("three:gen-idea") == "Opens a loose idea into a draft."


def test_a_function_that_is_not_marked_is_not_a_flow(mine: Path) -> None:
    written(mine, "three", THREE)

    with pytest.raises(FlowNotFound, match="run"):
        resolved("three:run")


def test_a_flow_that_is_one_file_is_a_flow_too(mine: Path) -> None:
    mine.mkdir(parents=True)
    (mine / "alone.py").write_text(ONE)

    assert _local() == [("local/alone", "Just the one, and it says what it does here.")]
    assert find("alone") == str((mine / "alone.py").resolve())
    assert resolved("alone").name == "whatever_it_is_called"


def test_a_directory_wins_a_name_a_file_also_uses(mine: Path) -> None:
    written(mine, "both", ONE)
    (mine / "both.py").write_text(TWO)

    assert find("both") == str((mine / "both" / ENTRY).resolve())
    assert [name for name, _ in _local()] == ["local/both"]


def test_a_flow_is_found_by_its_path_as_well(tmp_path: Path) -> None:
    """A flow anywhere else is its directory, or its file, typed out."""
    at = written(tmp_path / "elsewhere", "three", THREE)

    assert resolved(str(at)).name == "three"
    assert resolved(f"{at}:gen-idea").name == "gen-idea"
