"""`hmz.runtime.doing.daemons`: the daemons written down, and reaching them over their routes."""

from __future__ import annotations

import base64
import copy
import json
import threading
import time
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any, ClassVar

import pytest

from hmz.runtime import Refused
from hmz.runtime.doing.daemons import (
    ASKING,
    CARRIED,
    FAILED,
    LOCAL,
    UP,
    Daemons,
    Remotes,
    Unreached,
    carried,
    said,
)

if TYPE_CHECKING:
    from collections.abc import Callable

#: Two daemon ids, 52 base32 characters each.
_ID, _OTHER = "a" * 52, "b" * 52


@pytest.fixture
def held(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """The settings file, as a dict that `read` and `changes` read and write."""
    from hmz.coganchor import settings

    file: dict[str, Any] = {"other": {"kept": True}}

    def changes(change: Callable[[dict[str, Any]], None]) -> dict[str, Any]:
        working = copy.deepcopy(file)
        change(working)
        file.clear()
        file.update(working)
        return file

    monkeypatch.setattr(settings, "read", lambda: copy.deepcopy(file))
    monkeypatch.setattr(settings, "changes", changes)
    return file


@pytest.fixture
def config(monkeypatch: pytest.MonkeyPatch) -> None:
    """An ssh config naming `gpu` and `box.one`."""
    from hmz.coganchor.machines import sshconfig

    def aliases(*_: object) -> list[str]:
        return ["gpu", "box.one", "local"]

    monkeypatch.setattr(sshconfig, "aliases", aliases)


def test_a_daemon_is_written_replaced_only_when_asked_and_removed(
    held: dict[str, Any],
) -> None:
    daemons = Daemons()

    written = daemons.write("gpu", {"routes": ["stdio:ssh://gpu"]})
    with pytest.raises(FileExistsError):
        daemons.write("gpu", {"routes": ["stdio:local"]})
    daemons.write(
        "gpu",
        {"id": _ID, "routes": ["tcp://gpu:41817", "stdio:ssh://gpu"]},
        replace=True,
    )

    assert written == {"name": "gpu", "id": "", "routes": ["stdio:ssh://gpu"]}
    assert daemons.find("gpu") == daemons.all()[0]
    assert held["daemons"] == [
        {"name": "gpu", "id": _ID, "routes": ["tcp://gpu:41817", "stdio:ssh://gpu"]}
    ]
    assert held["other"] == {"kept": True}
    with pytest.raises(ValueError, match="Local is always there"):
        daemons.remove(LOCAL)
    with pytest.raises(LookupError):
        daemons.remove("nope")
    daemons.remove("gpu")
    assert daemons.all() == []


@pytest.mark.parametrize(
    ("name", "fields", "says"),
    [
        ("Local", {"routes": ["stdio:local"]}, "cannot be called"),
        ("..", {"routes": ["stdio:local"]}, "cannot be called"),
        ("gpu", {"routes": ["stdio:local"], "host": "a"}, "takes no host"),
        ("gpu", {"id": "nope", "routes": ["stdio:local"]}, "Say id"),
        ("gpu", {"routes": []}, "Say routes"),
        ("gpu", {"routes": "stdio:local"}, "Say routes"),
        ("gpu", {"routes": ["stdio:local", "gopher://x"]}, "is not a route"),
        ("gpu", {"routes": ["tcp://gpu:1", "stdio:local"]}, "needs the id"),
    ],
)
def test_what_cannot_be_a_daemon_is_refused(
    held: dict[str, Any], name: str, fields: dict[str, Any], says: str
) -> None:
    with pytest.raises(ValueError, match=says):
        Daemons().write(name, fields)

    assert "daemons" not in held


def test_hosts_of_the_ssh_config_are_offered_and_brought_in_once(
    held: dict[str, Any], config: None
) -> None:
    daemons = Daemons()

    assert daemons.offered() == {
        "gpu": {"name": "gpu", "id": "", "routes": ["stdio:ssh://gpu"]},
        "box.one": {"name": "box.one", "id": "", "routes": ["stdio:ssh://box.one"]},
    }
    assert daemons.imported(["gpu", "gpu"]) == ["gpu"]
    assert list(daemons.offered()) == ["box.one"]
    with pytest.raises(LookupError):
        daemons.imported(["elsewhere"])
    with pytest.raises(ValueError, match="Say aliases"):
        daemons.imported([])


def test_what_an_earlier_release_wrote_is_read_as_the_route_it_reached(
    held: dict[str, Any],
) -> None:
    secret = "sixteen-bytes-ok"
    held["daemons"] = [
        {"name": "cfg", "via": "ssh", "alias": "gpu", "host": "", "options": []},
        {
            "name": "typed",
            "via": "ssh",
            "host": "box",
            "user": "me",
            "port": 2222,
            "identity_file": "~/.ssh/id",
            "proxy_jump": "",
            "options": [["Compression", "yes"]],
        },
        {
            "name": "far",
            "via": "easytier",
            "secret": secret,
            "peers": ["tcp://node.example:11010"],
        },
        {
            "name": "short",
            "via": "easytier",
            "secret": "short",
            "peers": ["tcp://node.example:11010"],
        },
        {"name": "cfg", "routes": ["stdio:local"], "id": ""},
        {"name": "mixed", "routes": ["stdio:local"], "host": "a"},
    ]
    daemons = Daemons()

    assert daemons.all() == [
        {"name": "cfg", "id": "", "routes": ["stdio:ssh://gpu"]},
        {
            "name": "typed",
            "id": "",
            "routes": [
                "stdio:ssh://me@box:2222?identity=~%2F.ssh%2Fid&option=Compression=yes"
            ],
        },
        {"name": "far", "id": "", "routes": ["easytier:far"]},
    ]
    daemons.remove("cfg")

    assert held["daemons"] == daemons.all()
    assert held["easytier"] == {
        "far": {"secret": secret, "nodes": ["tcp://node.example:11010"]}
    }


def test_local_stands_up_and_nothing_else_is_reached_unasked() -> None:
    remotes = Remotes(version="1.2.3")
    try:
        assert remotes.state(LOCAL)["state"] == UP
        assert remotes.state("gpu") == {"state": "idle", "detail": "", "version": ""}
    finally:
        remotes.close()


def test_an_answer_to_a_daemon_nobody_asked_about_does_nothing() -> None:
    remotes = Remotes(version="1.2.3")
    try:
        idle = {"state": "idle", "detail": "", "version": ""}
        assert remotes.answer("nobody", True) == idle
        assert remotes.answer("nobody", False) == idle
        assert remotes.answer(LOCAL, True)["state"] == UP
    finally:
        remotes.close()


@pytest.mark.parametrize("install", [False, True, None])
def test_what_is_done_where_no_hmz_is_found_is_said_as_remotes_are_made(
    monkeypatch: pytest.MonkeyPatch, install: bool | None
) -> None:
    made: list[tuple[Any, ...]] = []

    class Made:
        def __init__(self, version: str | None = None, **said: Any) -> None:
            made.append((version, said))

    monkeypatch.setattr("hmz.runtime.doing.daemons.Remotes", Made)
    assert ASKING == "asking"
    assert isinstance(Daemons().remotes("1.2.3", install=install), Made)
    assert isinstance(Daemons().remotes(), Made)
    assert made == [("1.2.3", {"install": install}), (None, {"install": False})]


def test_a_probe_is_read_by_what_each_line_says() -> None:
    assert said(
        [
            "Warning: Permanently added 'box' to the list of known hosts.",
            "hmz: 0.5.0rc1",
            "daemon: running",
            "something: else",
        ]
    ) == {"hmz": "0.5.0rc1", "daemon": "running"}
    assert said(["hmz: ", "daemon: none"]) == {"hmz": "", "daemon": "none"}
    assert said([]) == {}


def _plain(url: str) -> str:
    """A URL with nothing signed into it, as the flowverses strike one."""
    return url.replace("me:secret@", "***@")


def test_a_batch_carries_the_pages_asked_for_as_settings_calls() -> None:
    target = SimpleNamespace(
        name="lab",
        url="https://me:secret@example.com/epics.git",
        branch="main",
        policies=("manual",),
        every=30,
    )
    runtime = SimpleNamespace(
        held=lambda: {"backend": "ssh", "name": "gpu", "made": "typed", "host": "g"}
    )

    def _shown(graph: object) -> dict[str, object] | None:
        return None if graph is None else {"start": graph}

    def graph(*names: str) -> SimpleNamespace:
        return SimpleNamespace(
            nodes=tuple(SimpleNamespace(use=name, among=()) for name in names)
        )

    # Written first, but naming `smart` in its `then`: carried after it.
    concrete = SimpleNamespace(
        name="claude/a",
        virtual=False,
        tries=2,
        policy="p",
        timeout=5,
        graph=None,
        then=graph("smart"),
    )
    virtual = SimpleNamespace(
        name="smart",
        virtual=True,
        tries=0,
        policy="q",
        timeout=0,
        graph=graph("codex/b"),
        then=None,
    )
    hmz = SimpleNamespace(
        settings=SimpleNamespace(ai_chan="", details=True, enable_sentry=False),
        nous=SimpleNamespace(
            all=lambda: [concrete, virtual],
            shown=_shown,
        ),
        runtimes=SimpleNamespace(all=lambda: [runtime]),
        backups=SimpleNamespace(targets=lambda: [target], defaults=lambda: ["lab"]),
        verses=SimpleNamespace(plain=_plain),
    )

    sent = carried(hmz, CARRIED)

    assert sent == [
        ("settings.set", {"details": True, "reports": False}),
        (
            "nous.set",
            {
                "name": "smart",
                "tries": 0,
                "policy": "q",
                "timeout": 0,
                "graph": {"start": virtual.graph},
                "then": None,
            },
        ),
        (
            "nous.set",
            {
                "name": "claude/a",
                "tries": 2,
                "policy": "p",
                "timeout": 5,
                "graph": None,
                "then": {"start": concrete.then},
            },
        ),
        (
            "runtimes.set",
            {"backend": "ssh", "name": "gpu", "fields": {"host": "g"}, "replace": True},
        ),
        (
            "settings.set",
            {
                "backup": {
                    "targets": [
                        {
                            "name": "lab",
                            "url": "https://***@example.com/epics.git",
                            "branch": "main",
                            "policies": ["manual"],
                            "every": 30,
                        }
                    ],
                    "defaults": ["lab"],
                }
            },
        ),
    ]
    assert carried(hmz, ["general"]) == sent[:1]


class _Peer:
    """`hmz.rpc.Peer` stood in for: each call answered as `ANSWERS` says."""

    ANSWERS: ClassVar[dict[str, Any]] = {}
    made: ClassVar[list[_Peer]] = []

    def __init__(self, pipe: object, serve: Any = None, **_: object) -> None:
        self.pipe, self.serve = pipe, serve
        self.calls: list[tuple[str, Any]] = []
        self.ended = threading.Event()
        self.told: list[Callable[[], None]] = []
        _Peer.made.append(self)

    @property
    def closed(self) -> bool:
        return self.ended.is_set()

    def closing(self, told: Callable[[], None]) -> None:
        self.told.append(told)

    def wait(self, timeout: float | None = None) -> bool:
        return self.ended.wait(timeout)

    def call(self, method: str, params: Any = None, **_: object) -> Any:
        self.calls.append((method, params))
        answer = _Peer.ANSWERS.get(method, {})
        if isinstance(answer, Exception):
            raise answer
        return answer

    def close(self) -> None:
        self.ended.set()
        for one in self.told:
            one()


@pytest.fixture
def reached(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Every route dialed, a session over each saying hello as the daemon `_ID`."""
    import hmz.reach
    import hmz.rpc
    from hmz.trust import identity, tls

    dialed: list[str] = []

    def dial(route: object, **_: object) -> object:
        dialed.append(str(route))
        return SimpleNamespace(close=lambda: None)

    def hello(*_: object, **__: object) -> dict[str, str]:
        return {"daemon_id": _ID, "version": "9.9.9", "device": "local"}

    def secured(pipe: object, *_: object) -> object:
        return pipe

    _Peer.ANSWERS, _Peer.made = {}, []
    monkeypatch.setattr(hmz.reach, "dial", dial)
    monkeypatch.setattr(hmz.rpc, "Peer", _Peer)
    monkeypatch.setattr(hmz.rpc, "hello", hello)
    monkeypatch.setattr(identity, "host", lambda: "here")
    monkeypatch.setattr(identity, "device", lambda: "me")
    monkeypatch.setattr(tls, "dial", secured)
    return dialed


def _stands(remotes: Remotes, name: str, state: str) -> dict[str, str]:
    """How a daemon stands, once it stands so."""
    ending = time.monotonic() + 5
    while remotes.state(name)["state"] != state:
        assert time.monotonic() < ending, remotes.state(name)
        time.sleep(0.01)
    return remotes.state(name)


def test_a_daemon_is_reached_its_id_pinned_and_its_client_called(
    held: dict[str, Any], reached: list[str]
) -> None:
    from hmz.rpc import RpcError

    Daemons().write("box", {"routes": ["stdio:local"]})
    _Peer.ANSWERS = {
        "settings.set": {"btw": "x"},
        "epic.stop": RpcError(404, "There is no epic e1.", {"epic": "e1"}),
    }
    remotes = Remotes(version="1.2.3")
    try:
        client = remotes.client("box")
        assert remotes.state("box") == {"state": UP, "detail": "", "version": "9.9.9"}
        assert (client.daemon_id, client.version, client.device) == (
            _ID,
            "9.9.9",
            "local",
        )
        assert held["daemons"] == [
            {"name": "box", "id": _ID, "routes": ["stdio:local"]}
        ]
        assert client.call("settings.set", {"btw": "x"}, idem="k") == {"btw": "x"}
        assert _Peer.made[0].calls[-1] == ("settings.set", {"btw": "x", "idem": "k"})
        with pytest.raises(Refused, match=r"There is no epic e1\.") as refused:
            client.call("epic.stop", {})
        assert getattr(refused.value, "code", None) == 404

        heard: list[tuple[str, dict[str, Any]]] = []
        client.heard(lambda method, params: heard.append((method, params)))
        with pytest.raises(RuntimeError):
            client.heard(print)
        _Peer.made[0].serve(
            SimpleNamespace(id=None, method="epic.event", params={"a": 1})
        )
        ending = time.monotonic() + 5
        while not heard:
            assert time.monotonic() < ending
            time.sleep(0.01)
        assert heard == [("epic.event", {"a": 1})]
        client.close()
        with pytest.raises(Refused, match="the daemon went away"):
            client.call("settings.get")
        # Another client of the same session goes on.
        assert remotes.client("box").call("settings.set") == {"btw": "x"}
        assert reached == ["stdio:local"]
    finally:
        remotes.close()
    assert remotes.state("box")["state"] == "idle"
    assert _Peer.made[0].closed


def test_a_daemon_that_answers_as_another_fails(
    held: dict[str, Any], reached: list[str]
) -> None:
    Daemons().write("box", {"id": _OTHER, "routes": ["stdio:local"]})
    remotes = Remotes(version="1.2.3")
    try:
        with pytest.raises(
            Unreached, match=r"box is not the daemon it was paired with\."
        ):
            remotes.client("box")
        assert held["daemons"][0]["id"] == _OTHER
    finally:
        remotes.close()


def test_an_easytier_daemon_never_paired_fails_before_anything_is_fetched(
    held: dict[str, Any], reached: list[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    from hmz.coganchor import easytier

    def binary(*_: object) -> None:
        raise AssertionError("EasyTier is fetched for a daemon that cannot be reached")

    monkeypatch.setattr(easytier, "binary", binary)
    held["daemons"] = [
        {"name": "p2p", "via": "easytier", "secret": "s" * 16, "peers": ["tcp://n:1"]}
    ]
    remotes = Remotes(version="1.2.3")
    try:
        with pytest.raises(
            Unreached, match=r"^easytier:p2p needs the id of the daemon it reaches\.$"
        ):
            remotes.client("p2p")
        assert reached == []
    finally:
        remotes.close()


def test_a_daemon_not_reached_fails_saying_why_and_waits_longer_each_time(
    held: dict[str, Any], reached: list[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    import hmz.reach

    waits: list[float] = []

    class Backoff(hmz.reach.Backoff):
        def next(self) -> float:
            waits.append(super().next())
            return 0.01

    def dial(route: object, **_: object) -> object:
        reached.append(str(route))
        raise ConnectionRefusedError(f"{route} refused")

    monkeypatch.setattr(hmz.reach, "Backoff", Backoff)
    monkeypatch.setattr(hmz.reach, "dial", dial)
    Daemons().write("box", {"id": _ID, "routes": ["tcp://box:1", "tcp://box:2"]})
    remotes = Remotes(version="1.2.3")
    try:
        remotes.connect("box")
        ending = time.monotonic() + 5
        while len(waits) < 3:
            assert time.monotonic() < ending
            time.sleep(0.01)
        assert remotes.state("box")["state"] in (FAILED, "connecting")
        assert waits[:3] == [1.0, 2.0, 4.0]
        with pytest.raises(Unreached, match=r"tcp://box:\d refused") as unreached:
            remotes.client("box")
        assert unreached.value.seen["state"] == FAILED
    finally:
        remotes.close()


def test_an_easytier_daemon_is_installing_while_easytier_downloads(
    held: dict[str, Any], reached: list[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    from hmz.coganchor import easytier

    downloaded = threading.Event()

    def binary(say: Callable[[str], object] | None = None) -> Any:
        assert say is not None
        say("Downloading EasyTier 9.9.9")
        downloaded.wait(5)
        raise OSError("cannot download EasyTier 9.9.9 for this machine")

    monkeypatch.setattr(easytier, "binary", binary)
    Daemons().write("et", {"id": _ID, "routes": ["easytier:et"]})
    remotes = Remotes(version="1.2.3")
    try:
        remotes.connect("et")
        assert _stands(remotes, "et", "installing") == {
            "state": "installing",
            "detail": "Downloading EasyTier 9.9.9",
            "version": "",
        }
        downloaded.set()
        failed = _stands(remotes, "et", FAILED)
        assert failed["detail"] == "cannot download EasyTier 9.9.9 for this machine"
    finally:
        remotes.close()
    assert reached == []


def _code(routes: list[str]) -> str:
    """A pairing code of the daemon `_ID`, as `hmz devices pair` prints one."""
    said = {"v": 1, "id": _ID, "routes": routes, "token": "t0ken", "expires": 1}
    return "hmz-pair:" + base64.urlsafe_b64encode(json.dumps(said).encode()).decode()


def test_a_pairing_code_is_claimed_and_its_daemon_written_down(
    held: dict[str, Any], reached: list[str]
) -> None:
    remotes = Remotes(version="1.2.3")
    try:
        written = remotes.pair("lab", _code(["tcp://lab:41817"]), device="laptop")
    finally:
        remotes.close()

    assert written == {"name": "lab", "id": _ID, "routes": ["tcp://lab:41817"]}
    assert held["daemons"] == [written]
    assert _Peer.made[0].calls == [("pair.claim", {"token": "t0ken", "name": "laptop"})]
    assert _Peer.made[0].closed


def test_a_pairing_code_refused_or_not_one_is_said_so(
    held: dict[str, Any], reached: list[str]
) -> None:
    from hmz.rpc import RpcError

    _Peer.ANSWERS = {"pair.claim": RpcError(403, "That pairing code is not valid.")}
    remotes = Remotes(version="1.2.3")
    try:
        with pytest.raises(Unreached, match="not valid") as unreached:
            remotes.pair("lab", _code(["tcp://lab:41817"]))
        assert unreached.value.status == 403
        with pytest.raises(ValueError, match="not a pairing code"):
            remotes.pair("lab", "hmz-pair:nope")
    finally:
        remotes.close()
    assert "daemons" not in held
    assert _Peer.made[0].calls == [("pair.claim", {"token": "t0ken", "name": "here"})]
