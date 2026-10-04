"""What a flow is called: humanize's own as its index lists them, and every other after an `@`.

humanize's index lists humanfia's flows bare, `flows/<flow>/<version>/`, and everybody else's
under who owns the repository, `flows/<user>/<flow>/<version>/` -- and a flow is called as the
index lists it: `aot`, `alice/demo`. An index somebody added is laid out the same way, and its
flows are called after it, `@mine/alice/demo`; the flows of your own are `@local/x` and
`@user/x`. A path is what starts with `.`, `/` or `~`, and nothing else is one.

What is checked is what somebody installing and running one would see: a flow listed under a
user installs a directory deeper and runs by that name, finds what it needs among the flows
installed out of the same index by what that index calls them, and a name said the way names
were said before -- or a path without its `./` -- says what it is now rather than only that
nothing answers to it.

Every repository here is one the test made a moment ago under its own directory, fetched with
git over `file://`. Nothing reaches a network.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

import pytest

from hmz.flows import FlowNotFound, FlowRefError
from hmz.runtime import Hmz
from hmz.runtime.flowing import ENTRY, LOCAL, MINE, OFFICIAL, finding, found, resolved
from hmz.runtime.flowing import verses as store
from hmz.runtime.flowing.fakes import run_fake
from hmz.runtime.flowing.index import RECORD, index, installed, kept
from tests.flows.indexes import committed, manifest, release
from tests.stubs import written

if TYPE_CHECKING:
    from pathlib import Path

#: A flow that answers with its own name, so that which one ran is what it said.
DEMO = '''"""Says which one it is."""

from hmz.flows import AgentCollection, EnvCollection, FlowParams, flow


@flow(agents=AgentCollection, envs=EnvCollection, params=FlowParams)
async def demo(task, *, agents, envs, params, ctx):
    return f"demo {task}"
'''

#: A flow that needs two others of its index, one listed bare and one under a user.
NEEDS = '''"""Needs two others."""

from hmz.flows import AgentCollection, EnvCollection, FlowParams, flow, load


@flow(agents=AgentCollection, envs=EnvCollection, params=FlowParams)
async def needs(task, *, agents, envs, params, ctx):
    bare = await load("helper")(task, agents={}, envs={}, params={})
    theirs = await load("bob/helper:inner")(task, agents={}, envs={}, params={})
    return [bare, theirs]
'''

#: What is needed, by one name and another.
HELPER = '''"""Helps."""

from hmz.flows import AgentCollection, EnvCollection, FlowParams, flow


@flow(agents=AgentCollection, envs=EnvCollection, params=FlowParams)
async def helper(task, *, agents, envs, params, ctx):
    return f"helper {task}"


@flow(agents=AgentCollection, envs=EnvCollection, params=FlowParams, hidden=True)
async def inner(task, *, agents, envs, params, ctx):
    return f"helper:inner {task}"
'''

#: A flow of your own that is called what an installed one needs, which it never stands in for.
IMPOSTOR = '''"""Not the one."""

from hmz.flows import AgentCollection, EnvCollection, FlowParams, flow


@flow(agents=AgentCollection, envs=EnvCollection, params=FlowParams)
async def helper(task, *, agents, envs, params, ctx):
    return "the wrong helper"
'''


@pytest.fixture
def code(tmp_path: Path) -> tuple[str, str]:
    """The repository the releases listed here live in: one directory per flow.

    Returns:
      Where it is fetched from, and the commit every release here was cut from.
    """
    at = tmp_path / "code"
    written(at, "demo", DEMO)
    written(at, "needs", NEEDS)
    written(at, "helper", HELPER)
    return f"file://{at}", committed(at, "flows")


def _index(tmp_path: Path, code: tuple[str, str]) -> Path:
    """An index listing a flow bare, and flows of two users: `alice/demo`, `bob/helper`.

    Returns:
      Its repository, committed.
    """
    url, commit = code
    at = tmp_path / "index"
    for listed, subdir, needs in [
        ("alice/demo", "demo", {}),
        ("alice/needs", "needs", {"helper": ">=0.1.0", "bob/helper": ">=0.1.0"}),
        ("bob/helper", "helper", {}),
        ("helper", "helper", {}),
    ]:
        name = listed.rpartition("/")[2]
        said = release(name, "0.1.0", url, commit, subdir=subdir, dependencies=needs)
        manifest(at, listed, "0.1.0", said)
    committed(at, "releases")
    return at


async def test_a_flow_humanize_s_index_lists_under_a_user_is_called_after_the_user(
    tmp_path: Path, code: tuple[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Installed a directory deeper, offered and run as `alice/demo`, and taken away again."""
    monkeypatch.setattr(store, "OFFICIAL_URL", str(_index(tmp_path, code)))
    verses = Hmz().flows.verses
    verses.fetch(OFFICIAL)
    assert index(OFFICIAL).flows() == [
        "alice/demo",
        "alice/needs",
        "bob/helper",
        "helper",
    ]

    (done,) = verses.install("alice/demo")

    assert (done.verse, done.owner, done.name, done.called) == (
        OFFICIAL,
        "alice",
        "demo",
        "alice/demo",
    )
    at = kept(OFFICIAL) / "alice" / "demo"
    assert sorted(one.name for one in at.iterdir()) == [RECORD, ENTRY]
    assert (OFFICIAL, "alice/demo") in [(one.whose, one.name) for one in found()]
    assert await run_fake(resolved("alice/demo"), "go") == "demo go"

    assert verses.uninstall("alice/demo")
    assert not (kept(OFFICIAL) / "alice").exists()
    assert installed() == []


async def test_a_flow_of_another_index_is_called_after_that_index_and_its_user(
    tmp_path: Path, code: tuple[str, str]
) -> None:
    """`@mine/alice/demo`, which no name without the `@` reaches: that is humanize's own."""
    verses = Hmz().flows.verses
    verses.add(str(_index(tmp_path, code)), "mine")

    verses.install("@mine/alice/demo")

    assert ("mine", "@mine/alice/demo") in [(one.whose, one.name) for one in found()]
    assert await run_fake(resolved("@mine/alice/demo"), "t") == "demo t"
    with pytest.raises(FlowNotFound, match=r"^alice/demo: the official flowverse"):
        resolved("alice/demo")  # humanize's own, which has not been fetched here


async def test_a_flow_finds_what_it_needs_among_its_index_s_by_what_the_index_calls_it(
    tmp_path: Path,
    code: tuple[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`helper` and `bob/helper` are the ones installed with it, whoever else has a `helper`.

    A flow of yours called `helper` would win a bare `helper` said anywhere else -- it is
    nearest -- and is no stand-in for what an installed flow named in its index.
    """
    monkeypatch.chdir(tmp_path)
    written(tmp_path / MINE[LOCAL], "helper", IMPOSTOR)
    verses = Hmz().flows.verses
    verses.add(str(_index(tmp_path, code)), "mine")

    done = verses.install("@mine/alice/needs")

    assert [one.called for one in done] == [
        "@mine/bob/helper",
        "@mine/helper",
        "@mine/alice/needs",
    ]
    said = await run_fake(resolved("@mine/alice/needs"), "t")
    assert said == ["helper t", "helper:inner t"]


async def test_a_flow_of_your_own_is_called_after_the_place_it_is_in(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`@local/demo`, and `demo` while nothing nearer is; a path is `./`, `/` or `~`."""
    monkeypatch.chdir(tmp_path)
    written(tmp_path / MINE[LOCAL], "demo", DEMO)
    written(tmp_path / "elsewhere", "demo", DEMO)

    assert (LOCAL, "@local/demo") in [(one.whose, one.name) for one in found()]
    assert await run_fake(resolved("@local/demo"), "a") == "demo a"
    assert await run_fake(resolved("demo"), "b") == "demo b"
    assert await run_fake(resolved("./elsewhere/demo"), "c") == "demo c"
    with pytest.raises(
        FlowNotFound, match=r"^local/demo: a flow of local is called @local/demo now$"
    ):
        resolved("local/demo")
    with pytest.raises(
        FlowNotFound,
        match=r"^elsewhere/demo: a path starts with \./, / or ~, as \./elsewhere/demo does$",
    ):
        resolved("elsewhere/demo")
    with pytest.raises(FlowRefError, match=r"a path starts with \./, / or ~"):
        resolved("a/deeper/path")


async def test_a_name_is_never_a_file_that_happens_to_be_where_it_runs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`demo.py` and `elsewhere/demo.py` are names, so a file of either name is not run."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / "elsewhere").mkdir()
    for path in ("demo.py", "elsewhere/demo.py"):
        (tmp_path / path).write_text(DEMO)

    for named in ("demo.py", "elsewhere/demo.py"):
        with pytest.raises(
            FlowNotFound,
            match=rf"^{re.escape(named)}: a path starts with \./, / or ~, "
            rf"as \./{re.escape(named)} does$",
        ):
            resolved(named)
        assert Hmz().flows.find(named) == ""
        with pytest.raises(ValueError, match="there is no flow called"):
            finding.fork(named)
    assert await run_fake(resolved("./elsewhere/demo.py"), "a") == "demo a"
    written(tmp_path / "elsewhere", "kit", DEMO)
    assert finding.at("elsewhere/kit/__init__.py") == ""
    assert finding.at("./elsewhere/kit") == str((tmp_path / "elsewhere/kit").resolve())
