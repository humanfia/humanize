"""Installing a flow out of a flowverse's index: the release fetched, copied into place, and run.

An index names a repository, a commit and a directory of it per release, and installing one is
fetching that commit and copying that directory under humanize's home with a record of what it
is. Every repository here is one the test made a moment ago under its own directory, fetched
with git over `file://`: a flow's code at two commits, and an index listing releases of it.

What is checked is what somebody installing would see. A release lands whole -- the directory
and everything beside its entry point, never the repository's `.git` -- with a record that says
what it is, and runs by its name. Two installs racing each other leave one whole flow and the
record that goes with it; one that cannot find its flow leaves nothing; one killed partway
leaves something the next install sweeps up. Another release of a flow replaces it whole, the
same release again changes nothing, and what a flow needs is installed beside it, where it is
found the way a flow finds what is beside it. What would break another installed flow, or could
not be installed at all, is refused before anything is fetched.
"""

from __future__ import annotations

import os
import threading
import time
from typing import TYPE_CHECKING, NamedTuple

import pytest

from hmz import machine
from hmz.runtime.flowing import ENTRY, resolved
from hmz.runtime.flowing import index as indexing
from hmz.runtime.flowing import verses as store
from hmz.runtime.flowing.fakes import run_fake
from hmz.runtime.flowing.index import (
    RECORD,
    Installed,
    Update,
    install,
    installed,
    kept,
    uninstall,
    updates,
)
from tests.flows.indexes import committed, listed, release
from tests.stubs import written

if TYPE_CHECKING:
    from collections.abc import Mapping
    from pathlib import Path

#: How long one thread here waits on another before giving up on it. A race nobody resolves is
#: a suite that hangs rather than one that fails, so every wait here has a clock on it.
_PATIENCE = 30.0

#: A flow that says which release of it is running, by what it keeps beside its entry point.
LOOP = '''"""Goes round, once."""

from hmz.flows import Agent, AgentCollection, EnvCollection, FlowParams, LocalEnv, flow

from _loop import VERSION


class Agents(AgentCollection):
    agent: Agent


class Envs(EnvCollection):
    here: LocalEnv


@flow(agents=Agents, envs=Envs, params=FlowParams)
async def loop(task, *, agents, envs, params, ctx):
    session = await agents["agent"].spawn()
    said = await agents["agent"].run(task, session=session, env=envs["here"])
    return f"loop {VERSION}: {said}"
'''

#: What another flow needs: one flow named for its directory, and one it hides.
HELPER = '''"""Helps."""

from hmz.flows import AgentCollection, EnvCollection, FlowParams, flow


@flow(agents=AgentCollection, envs=EnvCollection, params=FlowParams)
async def helper(task, *, agents, envs, params, ctx):
    return f"helper {task}"


@flow(agents=AgentCollection, envs=EnvCollection, params=FlowParams, hidden=True)
async def inner(task, *, agents, envs, params, ctx):
    return f"helper:inner {task}"
'''

#: A flow that loads the flow it needs by name, as one loads what is beside it.
PROVER = '''"""Proves, with help."""

from hmz.flows import AgentCollection, EnvCollection, FlowParams, flow, load


@flow(agents=AgentCollection, envs=EnvCollection, params=FlowParams)
async def prover(task, *, agents, envs, params, ctx):
    whole = await load("helper")(task, agents={}, envs={}, params={})
    inner = await load("helper:inner")(task, agents={}, envs={}, params={})
    return [whole, inner]
'''

#: A flow that is one file.
SOLO = '''"""All by itself."""

from hmz.flows import AgentCollection, EnvCollection, FlowParams, flow


@flow(agents=AgentCollection, envs=EnvCollection, params=FlowParams)
async def solo(task, *, agents, envs, params, ctx):
    return f"solo {task}"
'''


class Code(NamedTuple):
    """The repository the flows here live in.

    Attributes:
      url: Where it is fetched from.
      first: The commit `loop` says `one` at, with a file only that release has.
      second: The commit it says `two` at.
    """

    url: str
    first: str
    second: str


@pytest.fixture
def code(tmp_path: Path) -> Code:
    """A repository of flows, each in a directory of its own, at two commits."""
    at = tmp_path / "code"
    written(at, "loop", LOOP)
    (at / "loop" / "_loop.py").write_text('VERSION = "one"\n', encoding="utf-8")
    (at / "loop" / "_only_in_one.py").write_text("", encoding="utf-8")
    # Committed by somebody who should not have, and never what an install copies.
    (at / "loop" / "__pycache__").mkdir()
    (at / "loop" / "__pycache__" / "_loop.cpython.pyc").write_bytes(b"\x00")
    written(at, "helper", HELPER)
    written(at, "prover", PROVER)
    (at / "singles").mkdir()
    (at / "singles" / "solo.py").write_text(SOLO, encoding="utf-8")
    (at / "singles" / "other.py").write_text("raise AssertionError\n", encoding="utf-8")
    first = committed(at, "one")
    (at / "loop" / "_loop.py").write_text('VERSION = "two"\n', encoding="utf-8")
    (at / "loop" / "_only_in_one.py").unlink()
    second = committed(at, "two")
    return Code(f"file://{at}", first, second)


def _added(tmp_path: Path, *releases: Mapping[str, object]) -> Path:
    """An index of these releases, committed and added as the flowverse `theirs`.

    Returns:
      The index's own repository, to publish more releases into.
    """
    at = tmp_path / "theirs"
    listed(at, *releases)
    committed(at, "releases")
    store.add(str(at))
    return at


def _published(index: Path, *releases: Mapping[str, object]) -> None:
    """More releases in an index, committed -- and not fetched until somebody fetches."""
    listed(index, *releases)
    committed(index, "more releases")


def _left(verse: str = "theirs") -> list[str]:
    """Everything in the place a flowverse's installed flows are kept, hidden or not."""
    at = kept(verse)
    return sorted(one.name for one in at.iterdir()) if at.is_dir() else []


def _loop(code: Code, version: str = "0.1.0", commit: str = "") -> dict[str, object]:
    return release(
        "loop",
        version,
        code.url,
        commit or code.first,
        subdir="loop",
        ref=f"v{version}",
    )


# ------------------------------------------------------------------- one flow, whole


async def test_an_installed_flow_is_the_release_s_directory_and_a_record_of_it(
    tmp_path: Path, code: Code
) -> None:
    """Everything beside its entry point, which is the flow as much as the entry point is."""
    _added(tmp_path, _loop(code))

    (done,) = install("theirs", "loop")

    at = kept("theirs") / "loop"
    assert done == Installed(
        verse="theirs",
        name="loop",
        version="0.1.0",
        commit=code.first,
        repo=code.url,
        ref="v0.1.0",
        subdir="loop",
    )
    assert done.at == at
    assert sorted(one.name for one in at.iterdir()) == [
        RECORD,
        ENTRY,
        "_loop.py",
        "_only_in_one.py",
    ]
    assert Installed.model_validate_json((at / RECORD).read_text()) == done
    assert installed() == [done]
    assert await run_fake(resolved("@theirs/loop"), "go") == "loop one: ok"


async def test_a_release_at_the_root_of_its_repository_is_the_repository_less_its_git(
    tmp_path: Path,
) -> None:
    at = tmp_path / "whole"
    at.mkdir()
    (at / ENTRY).write_text(LOOP.replace("_loop", "_whole"), encoding="utf-8")
    (at / "_whole.py").write_text('VERSION = "whole"\n', encoding="utf-8")
    commit = committed(at)
    _added(tmp_path, release("whole", "1.0.0", f"file://{at}", commit))

    install("theirs", "whole")

    assert sorted(one.name for one in (kept("theirs") / "whole").iterdir()) == [
        RECORD,
        ENTRY,
        "_whole.py",
    ]
    assert await run_fake(resolved("@theirs/whole"), "go") == "loop whole: ok"


async def test_a_flow_that_is_one_file_is_installed_as_the_entry_point_of_a_directory(
    tmp_path: Path, code: Code
) -> None:
    """So every installed flow is the one shape, with somewhere to keep its record.

    And only that file: what else is in the directory it was in is other flows' business.
    """
    _added(tmp_path, release("solo", "0.1.0", code.url, code.first, subdir="singles"))

    install("theirs", "solo")

    at = kept("theirs") / "solo"
    assert sorted(one.name for one in at.iterdir()) == [RECORD, ENTRY]
    assert (at / ENTRY).read_text() == SOLO
    assert await run_fake(resolved("@theirs/solo"), "go") == "solo go"


def test_an_install_whose_repository_has_no_flow_where_it_says_leaves_nothing_behind(
    tmp_path: Path, code: Code
) -> None:
    _added(tmp_path, release("loop", "0.1.0", code.url, code.first, subdir="nowhere"))

    with pytest.raises(
        ValueError, match=r"has no flow in nowhere: neither __init__\.py nor loop\.py"
    ):
        install("theirs", "loop")

    assert _left() == []
    assert installed() == []


def test_an_install_of_a_commit_that_cannot_be_fetched_leaves_nothing_behind(
    tmp_path: Path, code: Code
) -> None:
    _added(tmp_path, release("loop", "0.1.0", code.url, "f" * 40, subdir="loop"))

    with pytest.raises(OSError, match="could not be fetched"):
        install("theirs", "loop")

    assert _left() == []
    assert installed() == []


def test_a_copy_that_fails_partway_leaves_the_release_that_was_there_as_it_was(
    tmp_path: Path, code: Code, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Copied beside the place, so a disk that fills is half a copy nobody can see."""
    import shutil

    _added(tmp_path, _loop(code), _loop(code, "0.2.0", code.second))
    (before,) = install("theirs", "loop", "0.1.0")

    def fills(source: Path, into: Path, **said: object) -> object:
        (into / "half").mkdir(parents=True)
        raise OSError("the disk filled up")

    monkeypatch.setattr(shutil, "copytree", fills)

    with pytest.raises(OSError, match="disk filled"):
        install("theirs", "loop", "0.2.0")

    assert installed() == [before]
    assert (kept("theirs") / "loop" / "_only_in_one.py").is_file()
    assert _left() == ["loop"]


# ------------------------------------------------------------------- races and leftovers


@pytest.mark.parametrize(
    "versions", [("0.1.0", "0.1.0"), ("0.1.0", "0.2.0")], ids=["same", "different"]
)
def test_two_installs_of_one_flow_at_once_leave_one_whole_flow_and_its_record(
    tmp_path: Path,
    code: Code,
    monkeypatch: pytest.MonkeyPatch,
    versions: tuple[str, str],
) -> None:
    """Whoever moves into place second moves the first one aside, rather than half over it.

    Both installs are real, and the one interleaving that can do damage is pinned: each has
    its copy written and recorded before either moves it into place, and the second to move
    does so once the first has -- so it finds the place taken by a whole flow, as an install
    racing another does. Which of the two gets there first is not asked. What is asked is that
    what is there is one release, whole, whose record says what it is: the record is written
    into the copy before the move, which is what makes the two arrive together.
    """
    _added(tmp_path, _loop(code), _loop(code, "0.2.0", code.second))
    moves = indexing._moved
    both = threading.Barrier(2)
    turn = threading.Lock()
    taken: list[bool] = []
    first = threading.Event()

    def together(held: Path, at: Path, holding: Path) -> None:
        """Moves into place once both are ready to, the second after the first is in."""
        both.wait(_PATIENCE)
        with turn:
            second = bool(taken)
            taken.append(second)
        if not second:
            moves(held, at, holding)
            first.set()
            return
        first.wait(_PATIENCE)
        taken.append(at.is_dir())
        moves(held, at, holding)

    monkeypatch.setattr(indexing, "_moved", together)
    failed: list[BaseException] = []

    def installs(version: str) -> None:
        try:
            install("theirs", "loop", version)
        except BaseException as why:  # noqa: BLE001 -- said below, on the test's thread
            failed.append(why)

    threads = [threading.Thread(target=installs, args=(one,)) for one in versions]
    for one in threads:
        one.start()
    for one in threads:
        one.join(_PATIENCE)

    assert failed == []
    # Both really did reach the move, and the second found the first's flow in the place.
    assert taken == [False, True, True]
    (one,) = installed()
    at = kept("theirs") / "loop"
    said = {"0.1.0": ("one", code.first), "0.2.0": ("two", code.second)}
    assert one.version in versions
    assert one.commit == said[one.version][1]
    assert (at / "_loop.py").read_text() == f'VERSION = "{said[one.version][0]}"\n'
    assert (at / "_only_in_one.py").exists() == (one.version == "0.1.0")
    # And neither left its copy, or what it moved aside, beside the place.
    assert _left() == ["loop"]


def test_what_a_killed_install_left_beside_the_place_is_swept_up_by_the_next(
    tmp_path: Path, code: Code
) -> None:
    """Old ones only: an install in flight writes a directory of exactly that shape."""
    _added(tmp_path, _loop(code))
    root = kept("theirs")
    killed = root / ".loop.abcdefgh"
    (killed / "loop").mkdir(parents=True)
    (killed / "loop" / ENTRY).write_text("half of it\n", encoding="utf-8")
    long_ago = time.time() - 20 * 60
    os.utime(killed, (long_ago, long_ago))
    live = root / ".loop.hgfedcba"
    live.mkdir()

    install("theirs", "loop")

    assert not killed.exists()
    assert live.is_dir()  # somebody else's install, still being written
    assert [one.name for one in installed()] == ["loop"]


# ------------------------------------------------------------------- another release


async def test_another_release_replaces_the_one_installed_whole(
    tmp_path: Path, code: Code
) -> None:
    """Nothing of the old one is left behind in the new one: it is a directory, not a merge."""
    _added(tmp_path, _loop(code), _loop(code, "0.2.0", code.second))
    install("theirs", "loop", "0.1.0")
    assert await run_fake(resolved("@theirs/loop"), "go") == "loop one: ok"

    (done,) = install("theirs", "loop")

    at = kept("theirs") / "loop"
    assert (done.version, done.commit) == ("0.2.0", code.second)
    assert not (at / "_only_in_one.py").exists()
    assert installed() == [done]
    assert _left() == ["loop"]
    assert await run_fake(resolved("@theirs/loop"), "go") == "loop two: ok"
    # And back again, by naming the release.
    install("theirs", "loop", "0.1.0")
    assert (at / "_only_in_one.py").exists()


def test_installing_the_release_that_is_installed_changes_nothing(
    tmp_path: Path, code: Code, monkeypatch: pytest.MonkeyPatch
) -> None:
    _added(tmp_path, _loop(code))
    (first,) = install("theirs", "loop")
    at = kept("theirs") / "loop"
    before = at.stat().st_ino

    def copies(verse: str, one: object) -> Installed:
        raise AssertionError(f"{one} was copied again")

    monkeypatch.setattr(indexing, "_put", copies)

    assert install("theirs", "loop") == [first]
    assert at.stat().st_ino == before


def test_the_release_installed_when_nobody_says_which_is_the_newest_that_is_ready(
    tmp_path: Path, code: Code
) -> None:
    _added(
        tmp_path,
        _loop(code),
        _loop(code, "0.2.0", code.second),
        _loop(code, "0.3.0-rc.1", code.second),
    )

    (done,) = install("theirs", "loop")

    assert done.version == "0.2.0"


# ------------------------------------------------------------------- what a flow needs


def _needing(code: Code, spec: str = ">=0.1.0,<0.2.0") -> list[dict[str, object]]:
    """`prover`, which needs `helper` in a range, and three releases of `helper`."""
    return [
        release(
            "prover",
            "0.1.0",
            code.url,
            code.first,
            subdir="prover",
            dependencies={"helper": spec},
        ),
        release("helper", "0.1.0", code.url, code.first, subdir="helper"),
        release("helper", "0.1.1", code.url, code.second, subdir="helper"),
        release("helper", "0.2.0", code.url, code.second, subdir="helper"),
    ]


def test_what_a_flow_needs_is_installed_with_it(tmp_path: Path, code: Code) -> None:
    """The newest release its range takes, installed first."""
    _added(tmp_path, *_needing(code))

    done = install("theirs", "prover")

    assert [(one.name, one.version) for one in done] == [
        ("helper", "0.1.1"),
        ("prover", "0.1.0"),
    ]
    assert installed() == sorted(done, key=lambda one: one.name)
    assert done[1].dependencies == {"helper": ">=0.1.0,<0.2.0"}


async def test_an_installed_flow_loads_what_it_needs_from_beside_it(
    tmp_path: Path, code: Code
) -> None:
    """As in the repository the two came from: installed flows are each other's neighbours.

    Which is why an installed flow is kept under its own name: `load("helper:inner")` from
    inside `prover` is a flow beside it, wherever both were installed.
    """
    _added(tmp_path, *_needing(code))
    install("theirs", "prover")

    said = await run_fake(resolved("@theirs/prover"), "t")

    assert said == ["helper t", "helper:inner t"]


def test_what_a_flow_needs_that_is_installed_at_a_version_it_takes_is_left_alone(
    tmp_path: Path, code: Code
) -> None:
    _added(tmp_path, *_needing(code))
    (helper,) = install("theirs", "helper", "0.1.0")
    before = (kept("theirs") / "helper").stat().st_ino

    done = install("theirs", "prover")

    assert [(one.name, one.version) for one in done] == [("prover", "0.1.0")]
    assert [one for one in installed() if one.name == "helper"] == [helper]
    assert (kept("theirs") / "helper").stat().st_ino == before


def test_what_a_flow_needs_that_is_installed_at_a_version_it_does_not_take_is_moved(
    tmp_path: Path, code: Code
) -> None:
    _added(tmp_path, *_needing(code))
    install("theirs", "helper", "0.2.0")

    done = install("theirs", "prover")

    assert [(one.name, one.version) for one in done] == [
        ("helper", "0.1.1"),
        ("prover", "0.1.0"),
    ]
    assert [(one.name, one.version) for one in installed()] == [
        ("helper", "0.1.1"),
        ("prover", "0.1.0"),
    ]


def test_installing_what_would_break_another_installed_flow_is_refused(
    tmp_path: Path, code: Code
) -> None:
    """Rather than leaving somebody's other flow broken by the one they asked for."""
    _added(tmp_path, *_needing(code))
    install("theirs", "prover")

    with pytest.raises(ValueError, match="would break it"):
        install("theirs", "helper", "0.2.0")

    assert [(one.name, one.version) for one in installed()] == [
        ("helper", "0.1.1"),
        ("prover", "0.1.0"),
    ]


@pytest.mark.parametrize(
    ("releases", "why"),
    [
        (
            [
                {"name": "a", "dependencies": {"b": ">=0.1.0"}},
                {"name": "b", "dependencies": {"a": ">=0.1.0"}},
            ],
            "a needs itself, through a -> b -> a",
        ),
        (
            [{"name": "a", "dependencies": {"b": ">=1.0.0"}}, {"name": "b"}],
            "no release of it in that range",
        ),
    ],
    ids=["a cycle", "out of range"],
)
def test_an_install_that_cannot_be_had_is_refused_before_anything_is_fetched(
    tmp_path: Path,
    code: Code,
    releases: list[dict[str, object]],
    why: str,
) -> None:
    _added(
        tmp_path,
        *(
            release(
                str(one["name"]),
                "0.1.0",
                code.url,
                code.first,
                subdir="helper",
                dependencies=one.get("dependencies", {}),
            )
            for one in releases
        ),
    )

    with pytest.raises(ValueError, match=why):
        install("theirs", "a")

    assert _left() == []
    assert not (machine() / "pinned").exists()


def test_a_flow_another_installed_flow_needs_is_not_uninstalled(
    tmp_path: Path, code: Code
) -> None:
    """That one is to be uninstalled first, which then lets this one go."""
    _added(tmp_path, *_needing(code))
    install("theirs", "prover")

    with pytest.raises(
        ValueError, match=r"^@theirs/prover needs helper; uninstall that first$"
    ):
        uninstall("theirs", "helper")
    assert (kept("theirs") / "helper" / ENTRY).is_file()

    assert uninstall("theirs", "prover")
    assert uninstall("theirs", "helper")
    assert installed() == []
    assert _left() == []


# ------------------------------------------------------------------- what is newer


def test_what_is_newer_is_what_the_index_said_when_it_was_last_fetched(
    tmp_path: Path, code: Code
) -> None:
    """A fetch is what brings word of a release, and an install is what takes one."""
    index = _added(tmp_path, _loop(code))
    (loop,) = install("theirs", "loop")
    assert updates() == []

    _published(
        index, _loop(code, "0.2.0", code.second), _loop(code, "0.3.0-rc.1", code.second)
    )
    assert updates() == []  # published, and not yet fetched
    store.fetch("theirs")

    assert updates() == [Update(loop, "0.2.0")]
    assert installed() == [loop]  # told of, and not taken


def test_a_flow_on_a_prerelease_is_told_of_the_next_candidate(
    tmp_path: Path, code: Code
) -> None:
    index = _added(tmp_path, _loop(code), _loop(code, "0.2.0-rc.1", code.second))
    (candidate,) = install("theirs", "loop", "0.2.0-rc.1")
    _published(index, _loop(code, "0.2.0-rc.2", code.second))
    store.fetch("theirs")

    assert updates() == [Update(candidate, "0.2.0-rc.2")]
