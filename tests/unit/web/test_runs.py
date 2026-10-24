"""`hmz.web.runs`: the runs written down here, as the pages list them, sum them and draw them."""

from __future__ import annotations

import datetime
import subprocess
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, cast

import pytest

from hmz.web.runs import held_by, local, refused, row

if TYPE_CHECKING:
    from hmz.runtime.epic import Ran


@dataclass(frozen=True)
class _Ran:
    """As much of a run written down as these read."""

    flow: str = "ralph"
    task: str = "fix it"
    began: str = "2026-10-08T10:00:00+00:00"
    workspace: str = "/work/one"
    at: str = ""
    ended: str = ""
    how: str = ""
    spent: dict[str, Any] | None = None
    name: str = ""


def _runs(*runs: _Ran) -> list[Ran]:
    return cast("list[Ran]", list(runs))


@pytest.mark.parametrize(
    ("standing", "found"),
    [
        ({"state": "running", "flow": "ralph", "task": "fix it", "at": 0.0}, 1),
        ({"state": "stopping", "flow": "ralph", "task": "fix it", "at": 60.0}, 1),
        ({"state": "running", "flow": "ralph", "task": "fix it", "at": 600.0}, None),
        ({"state": "running", "flow": "ralph", "task": "other", "at": 0.0}, None),
        ({"state": "running", "flow": "goal", "task": "fix it", "at": 0.0}, None),
        # Asked of the daemon, a host says which flow and nothing of the task or when.
        ({"state": "running", "flow": "ralph"}, 1),
        (None, None),
    ],
)
def test_the_run_going_is_the_one_opened_for_it_as_it_started(
    standing: dict[str, Any] | None, found: int | None
) -> None:
    began = datetime.datetime.fromtimestamp(0, datetime.UTC).isoformat()
    runs = _runs(
        _Ran(
            began=began, ended=began, how="done", at="over"
        ),  # over, so not the one going
        _Ran(began=began, at="going"),
        # The same flow on the same task, going in another workspace: that one's, not this.
        _Ran(began=began, at="elsewhere", workspace="/work/two"),
    )
    running = [] if standing is None else [standing | {"workspace": "/work/one"}]

    held = held_by(runs, running)

    assert set(held) == ({runs[found].at} if found is not None else set())


@pytest.mark.parametrize("turn", ["running", "done", ""])
def test_the_run_going_carries_where_a_chat_is_in_its_turn(turn: str) -> None:
    runs = _runs(_Ran(flow="chat", at="going"))
    standing = {"state": "running", "flow": "chat"} | ({"turn": turn} if turn else {})

    held = held_by(runs, [standing | {"workspace": "/work/one", "slot": "chat:1"}])

    assert held == {"going": {"turn": turn, "slot": "chat:1"}}


def test_the_run_going_is_the_epic_its_host_says_it_writes() -> None:
    runs = _runs(
        _Ran(flow="chat", at="second", name="b"),
        _Ran(flow="chat", at="first", name="a"),
    )
    standing = {"state": "running", "flow": "chat", "workspace": "/work/one"}

    held = held_by(
        runs,
        [
            standing | {"epic": "a", "slot": "chat:1"},
            standing | {"epic": "b", "slot": "chat:2"},
        ],
    )

    assert held == {
        "first": {"turn": "", "slot": "chat:1"},
        "second": {"turn": "", "slot": "chat:2"},
    }


@pytest.mark.parametrize(
    ("said", "status", "named"),
    [
        (
            "20261012T1015Z-ab12 is already here, at /h/epics/-w/20261012T1015Z-ab12",
            409,
            "20261012T1015Z-ab12",
        ),
        ("an epic is already here, at /h/epics/-w/an epic", 409, "an epic"),
        ("a is already here, at /h/epics/-w/b", 400, None),
        ("x.hmzepic is not a bundle Humanize can read: not a gzip file", 400, None),
        ("x.txt is not a .hmzepic file", 400, None),
    ],
)
def test_an_import_refused_is_a_conflict_naming_the_epic_only_where_it_is_here(
    said: str, status: int, named: str | None
) -> None:
    refusal = refused(ValueError(said))

    assert refusal.status == status
    assert str(refusal) == f"{said}."
    assert refusal.said.get("name") == named


@dataclass(frozen=True)
class _Row:
    """As much of a run written down as a row of the list reads."""

    how: str = ""
    name: str = "20261012T135159.936Z-bc3e81"
    workspace: str = "/work/one"
    flow: str = "ralph"
    task: str = "fix it"
    began: str = "2026-10-08T10:00:00+00:00"
    ended: str = ""
    agents: tuple[Any, ...] = ()
    sessions: tuple[Any, ...] = ()
    resumable: bool = False
    spent: dict[str, Any] | None = None
    backup: tuple[str, ...] = ()
    backed: dict[str, Any] | None = None


@pytest.mark.parametrize(
    ("how", "held", "going", "said"),
    [
        ("", True, True, "running"),
        # Held by a process no host speaks for -- `hmz exec` -- and going all the same.
        ("", False, True, "running"),
        ("", False, False, "unfinished"),
        ("done", False, False, "done"),
    ],
)
def test_a_run_is_said_running_while_any_process_holds_it(
    how: str, held: bool, going: bool, said: str
) -> None:
    ran = cast("Ran", _Row(how=how))

    listed = row(ran, held=held, going=going)

    assert listed["how"] == said
    assert listed["held"] is held


@pytest.mark.parametrize(
    ("how", "held", "going", "turn", "said"),
    [
        # The agent is answering.
        ("", True, True, "running", "running"),
        # Between turns: the turn is done, though the chat goes on.
        ("", True, True, "done", "done"),
        # Going where no host says where its turn is.
        ("", False, True, "", "running"),
        # Over: however it was ended but failing, it is done.
        ("", False, False, "", "done"),
        ("stopped", False, False, "", "done"),
        ("done", False, False, "", "done"),
        ("failed", False, False, "", "failed"),
        ("crashed", False, False, "", "crashed"),
    ],
)
def test_a_chat_is_said_running_only_while_its_agent_answers(
    how: str, held: bool, going: bool, turn: str, said: str
) -> None:
    ran = cast("Ran", _Row(flow="chat", how=how))

    assert row(ran, held=held, going=going, turn=turn)["how"] == said


@dataclass(frozen=True)
class _Drove:
    """As much of an agent a run wrote down as a row reads."""

    agent: str
    name: str
    spec: str = "claude/opus"


def test_a_run_lists_each_agent_by_its_own_name_and_the_role_it_filled_beside() -> None:
    # One written before an agent had a name of its own went by its role.
    ran = _Row(agents=(_Drove("builder", "NeiKos496"), _Drove("critic", "")))

    listed = row(cast("Ran", ran), held=False)

    assert [(one["name"], one["role"]) for one in listed["agents"]] == [
        ("NeiKos496", "builder"),
        ("critic", "critic"),
    ]


@pytest.mark.parametrize(
    "said",
    [r"C:\Users\me\x.hmzepic", "c:/Users/me/x.hmzepic", r"\\wsl$\Debian\x.hmzepic"],
)
def test_a_windows_path_is_read_as_wsl_names_it_in_wsl(
    said: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    asked: list[list[str]] = []

    def wslpath(argv: list[str], **_: Any) -> subprocess.CompletedProcess[str]:
        asked.append(argv)
        return subprocess.CompletedProcess(argv, 0, "/mnt/c/Users/me/x.hmzepic\n")

    monkeypatch.setenv("WSL_DISTRO_NAME", "Debian")
    monkeypatch.setattr(subprocess, "run", wslpath)

    assert str(local(said)) == "/mnt/c/Users/me/x.hmzepic"
    assert asked == [["wslpath", "-u", said]]


def test_a_path_is_kept_as_said_outside_wsl_or_where_wsl_cannot_name_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    asked: list[list[str]] = []

    def fails(argv: list[str], **_: Any) -> subprocess.CompletedProcess[str]:
        asked.append(argv)
        raise subprocess.CalledProcessError(1, argv)

    monkeypatch.setattr(subprocess, "run", fails)
    monkeypatch.delenv("WSL_DISTRO_NAME", raising=False)
    assert str(local("/home/me/x.hmzepic")) == "/home/me/x.hmzepic"
    assert not local(r"C:\x.hmzepic").is_absolute()
    assert asked == []

    monkeypatch.setenv("WSL_DISTRO_NAME", "Debian")
    assert str(local("/home/me/x.hmzepic")) == "/home/me/x.hmzepic"
    assert asked == []
    # One wslpath cannot name is refused as a path that is not whole.
    assert not local(r"C:\x.hmzepic").is_absolute()
    assert asked == [["wslpath", "-u", r"C:\x.hmzepic"]]
