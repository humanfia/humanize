"""`hmz.daemon.api.runs`: what a call to `runs.*` is refused for before any epic is read."""

from __future__ import annotations

import base64
import threading
from typing import TYPE_CHECKING, Any, cast

import pytest

from hmz.daemon.api import files, runs
from hmz.rpc import RpcError

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator
    from pathlib import Path

    from hmz.rpc import Call


class _Session:
    """A session as a handle reads it: whether it has closed, and waiting for it to."""

    def __init__(self) -> None:
        self._closed = threading.Event()
        self._closing: list[Callable[[], None]] = []

    @property
    def closed(self) -> bool:
        return self._closed.is_set()

    def wait(self, timeout: float | None = None) -> bool:
        return self._closed.wait(timeout)

    def closing(self, told: Callable[[], None]) -> None:
        self._closing.append(told)

    def close(self) -> None:
        self._closed.set()
        for told in self._closing:
            told()


class _Call:
    """A call as a handler reads it."""

    def __init__(self, peer: _Session, method: str, **params: Any) -> None:
        self.peer = peer
        self.method = method
        self.params = params


class _Runs:
    """The runs, as far as an import reads them: what it was handed."""

    def __init__(self) -> None:
        self.archives: list[tuple[str, bytes]] = []

    def imported(self, archive: Path) -> dict[str, Any]:
        self.archives.append((archive.name, archive.read_bytes()))
        return {"name": "e", "workspace": "/w", "resumable": True, "why": ""}


@pytest.fixture
def session() -> Iterator[_Session]:
    one = _Session()
    yield one
    one.close()


@pytest.fixture
def held(monkeypatch: pytest.MonkeyPatch) -> _Runs:
    fake = _Runs()
    monkeypatch.setattr(runs, "RUNS", fake)
    return fake


def _call(session: _Session, method: str, **params: Any) -> Any:
    table = {**runs.METHODS, **files.METHODS}
    return table[method](cast("Call", _Call(session, method, **params)))


def _refused(session: _Session, method: str, **params: Any) -> RpcError:
    with pytest.raises(RpcError) as refused:
        _call(session, method, **params)
    return refused.value


def _sent(session: _Session, name: str, data: bytes) -> str:
    handle = _call(session, "files.create", name=name, size=len(data))["handle"]
    encoded = base64.b64encode(data).decode()
    _call(session, "files.write", handle=handle, offset=0, data=encoded)
    return handle


def test_every_method_of_the_family_is_served() -> None:
    assert set(runs.METHODS) == {
        f"runs.{one}"
        for one in (
            "list",
            "get",
            "trace",
            "timeline",
            "span",
            "bundle",
            "backup",
            "import",
            "usage",
        )
    }


@pytest.mark.parametrize(
    ("method", "params", "message"),
    [
        ("runs.list", {"limit": 0}, "runs.list takes limit as integer from 1 to 200."),
        (
            "runs.list",
            {"limit": 201},
            "runs.list takes limit as integer from 1 to 200.",
        ),
        ("runs.list", {"offset": -1}, "runs.list takes offset as integer from 0."),
        ("runs.usage", {"days": 0}, "runs.usage takes days as integer from 1 to 365."),
        (
            "runs.usage",
            {"days": 366},
            "runs.usage takes days as integer from 1 to 365.",
        ),
        (
            "runs.backup",
            {"name": "e", "to": [1]},
            "runs.backup takes to as array of strings.",
        ),
        ("runs.import", {}, "runs.import takes handle or path, one of them."),
        (
            "runs.import",
            {"handle": "h", "path": "/x"},
            "runs.import takes handle or path, one of them.",
        ),
    ],
)
def test_parameters_out_of_their_range_are_refused(
    session: _Session, method: str, params: dict[str, Any], message: str
) -> None:
    refused = _refused(session, method, **params)

    assert (refused.code, refused.message) == (-32602, message)


@pytest.mark.parametrize(
    ("said", "code", "data"),
    [
        ("an epic is already here, at /h/epics/-w/an epic", 409, {"name": "an epic"}),
        ("x.hmzepic is not a bundle Humanize can read: not a gzip file", 400, None),
    ],
)
def test_an_import_refused_says_why_and_names_the_epic_already_here(
    said: str, code: int, data: dict[str, str] | None
) -> None:
    refused = runs.refused(ValueError(said))

    assert (refused.code, refused.message, refused.data) == (code, f"{said}.", data)


def test_an_archive_sent_is_imported_under_its_name_and_taken(
    session: _Session, held: _Runs
) -> None:
    handle = _sent(session, "e.hmzepic", b"bytes")

    assert _call(session, "runs.import", handle=handle)["name"] == "e"
    assert held.archives == [("e.hmzepic", b"bytes")]
    gone = _refused(session, "files.close", handle=handle)
    assert (gone.code, gone.message) == (404, f"There is no file {handle}.")


@pytest.mark.parametrize("name", ["", "..", "a/b", "a\\b", "a\0b", "x" * 256])
def test_an_archive_sent_under_no_file_name_is_refused_and_taken(
    session: _Session, held: _Runs, name: str
) -> None:
    handle = _sent(session, name, b"x")

    refused = _refused(session, "runs.import", handle=handle)

    assert (refused.code, refused.message) == (400, "That is not a file name.")
    assert not held.archives
    assert _refused(session, "files.close", handle=handle).code == 404


def test_an_archive_named_by_a_path_is_a_whole_one(
    session: _Session, held: _Runs
) -> None:
    refused = _refused(session, "runs.import", path="x.hmzepic")

    assert (refused.code, refused.message) == (
        400,
        "Say path as a whole path on this machine.",
    )
    assert not held.archives


def _ran(flow: str, **said: Any) -> Any:
    """An epic read back, as far as a row reads one."""
    from pathlib import Path
    from types import SimpleNamespace

    return SimpleNamespace(
        name="20260101-abc",
        at=Path("/epics/20260101-abc"),
        workspace="/w",
        flow=flow,
        task="hello",
        began="2026-01-01T00:00:00Z",
        ended="",
        agents=(),
        sessions=(),
        resumable=False,
        spent=None,
        backup=(),
        backed={},
        **said,
        # As `hmz.runtime.epic.read` reads one: of no kind and the flow `chat`, an earlier
        # hmz's chat.
        chat=said.get("kind", "chat" if flow == "chat" else "flow") == "chat",
    )


@pytest.mark.parametrize(
    ("ran", "turn", "ending", "kind", "flow", "how"),
    [
        # A chat says so, and no flow; going while its turn is, and stopped between.
        (_ran("", kind="chat"), "running", "running", "chat", "", "running"),
        (_ran("", kind="chat"), "done", "running", "chat", "", "stopped"),
        (_ran("", kind="chat"), "", "done", "chat", "", "stopped"),
        (_ran("", kind="chat"), "", "failed", "chat", "", "failed"),
        # As an earlier hmz wrote one: the flow `chat`, and no kind.
        (_ran("chat"), "done", "running", "chat", "", "stopped"),
        # A flow named chat now is a flow, said as it went.
        (_ran("chat", kind="flow"), "", "done", "flow", "chat", "done"),
        (_ran("ralph"), "", "running", "flow", "ralph", "running"),
    ],
)
def test_an_epic_row_says_its_kind_and_a_chats_state_by_its_turn(
    ran: Any,
    turn: str,
    ending: str,
    kind: str,
    flow: str,
    how: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import hmz.runtime.epic

    def ends(ran: Any, *, going: bool) -> str:
        del ran, going
        return ending

    monkeypatch.setattr(hmz.runtime.epic, "ending", ends)

    said = runs.row(ran, held=True, turn=turn)

    assert (said["kind"], said["flow"], said["how"]) == (kind, flow, how)


def test_a_host_going_with_a_chat_holds_the_chat_not_a_flow_of_its_name() -> None:
    chat, named = _ran("", kind="chat"), _ran("", kind="flow")
    going = [
        {"workspace": "/w", "kind": "chat", "flow": "", "task": "hello", "turn": "done"}
    ]

    held = runs.held_by([named, chat], going)

    assert list(held) == [chat.at]
    assert held[chat.at]["turn"] == "done"


def test_a_list_leaves_out_every_ai_chan_epic_and_one_her_host_holds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from pathlib import Path
    from types import SimpleNamespace

    import hmz.runtime.epic

    def ends(ran: Any, *, going: bool) -> str:
        del ran, going
        return "running"

    monkeypatch.setattr(hmz.runtime.epic, "ending", ends)

    def named(name: str, task: str) -> Any:
        ran = _ran("", kind="chat")
        ran.name, ran.at, ran.task = name, Path("/epics") / name, task
        return ran

    plain, hers, unnamed = named("a", "mine"), named("b", "hers"), named("c", "new")

    def every(workspace: str) -> list[Any]:
        del workspace
        return [unnamed, hers, plain]

    def goes(ran: Any) -> bool:
        del ran
        return False

    kept = SimpleNamespace(all=every, going=goes)
    # Her newest conversation's host has named its epic, which no file has yet.
    going = [
        {"workspace": "/w", "epic": "c", "slot": "ai:1"},
        {"workspace": "/w", "epic": "a", "slot": ""},
    ]

    said = runs.listed(cast("Any", kept), going, hers={"b"})

    assert [one["name"] for one in said["runs"]] == ["a"]
    assert (said["total"], said["counts"]) == (1, {"running": 1})
    assert said["flows"] == ["chat"]


def test_a_list_asked_for_one_kind_holds_only_that_kind(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from pathlib import Path
    from types import SimpleNamespace

    import hmz.runtime.epic

    def ends(ran: Any, *, going: bool) -> str:
        del ran, going
        return "done"

    monkeypatch.setattr(hmz.runtime.epic, "ending", ends)

    def named(name: str, flow: str, kind: str) -> Any:
        ran = _ran(flow, kind=kind)
        ran.name, ran.at = name, Path("/epics") / name
        return ran

    chat, epic = named("a", "", "chat"), named("b", "ralph", "flow")

    def every(workspace: str) -> list[Any]:
        del workspace
        return [chat, epic]

    def goes(ran: Any) -> bool:
        del ran
        return False

    kept = cast("Any", SimpleNamespace(all=every, going=goes))

    def names(kind: str) -> list[str]:
        return [one["name"] for one in runs.listed(kept, [], what=kind)["runs"]]

    assert names("") == ["a", "b"]
    assert names("chat") == ["a"]
    assert names("flow") == ["b"]
    # What is counted is what is listed: every epic, or those of the kind asked for.
    assert sum(runs.listed(kept, [], what="")["counts"].values()) == 2
    assert sum(runs.listed(kept, [], what="chat")["counts"].values()) == 1
