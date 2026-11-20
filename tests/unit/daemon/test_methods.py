"""`hmz.daemon.methods` and `hmz.daemon.listening`: calls, envs, and listener specs."""

from __future__ import annotations

import json
import threading
from pathlib import Path
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any, cast

import pytest

from hmz.daemon import where
from hmz.daemon.listening import Listener, spec
from hmz.daemon.methods import ENV, EPIC, families, methods, slot, workspace
from hmz.rpc import RpcError

if TYPE_CHECKING:
    from hmz.daemon.routing import Router
    from hmz.rpc import Call, Handler

ROOT = Path(__file__).resolve().parents[3]


def test_a_workspace_is_a_whole_path_with_every_link_followed(tmp_path: Path) -> None:
    (tmp_path / "real").mkdir()
    (tmp_path / "link").symlink_to(tmp_path / "real")

    assert workspace(str(tmp_path / "link")) == where.workspace(tmp_path / "real")


def test_a_workspace_that_is_not_a_whole_path_is_refused_400() -> None:
    with pytest.raises(RpcError) as refused:
        workspace("here")
    assert (refused.value.code, refused.value.message) == (
        400,
        "Say the workspace as a whole path, not here.",
    )


def test_a_workspace_naming_no_directory_is_refused_404(tmp_path: Path) -> None:
    with pytest.raises(RpcError) as refused:
        workspace(str(tmp_path / "nowhere"))
    assert refused.value.code == 404
    assert refused.value.message == f"There is no directory {tmp_path / 'nowhere'}."


def test_a_workspace_looked_up_need_not_be_there_any_more(tmp_path: Path) -> None:
    # A host already held is found by its workspace after the directory was removed.
    gone = tmp_path / "nowhere"

    assert workspace(str(gone), made=True) == where.workspace(gone)
    with pytest.raises(RpcError) as refused:
        workspace("here", made=True)
    assert refused.value.code == 400


@pytest.mark.parametrize("said", [None, "", "chat:0a", "exec:1"])
def test_a_slot_is_one_of_the_workspaces_hosts(said: str | None) -> None:
    assert slot(said) == (said or "")


def test_a_new_slot_is_named_by_its_kind_alone_where_one_may_be() -> None:
    assert slot("chat:", new=True) == "chat:"
    with pytest.raises(RpcError, match=r"chat: is not a slot\."):
        slot("chat:")


@pytest.mark.parametrize("said", ["flow", "chat:XY", 3])
def test_anything_else_is_refused_400(said: object) -> None:
    with pytest.raises(RpcError) as refused:
        slot(said)
    assert (refused.value.code, refused.value.message) == (
        400,
        f"{said} is not a slot.",
    )


def test_every_call_to_an_epic_is_served() -> None:
    assert set(EPIC) == {
        "start",
        "say",
        "answer",
        "face",
        "stop",
        "force",
        "afk",
        "claim",
        "release",
        "board",
        "aside",
        "unaside",
        "status",
        "detach",
        "quit",
    }


def test_each_family_names_its_methods(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import hmz.daemon.api

    (tmp_path / "families_u.py").write_text('METHODS = {"settings.get": dict}\n')
    (tmp_path / "broken.py").write_text("raise ImportError('nothing here')\n")
    monkeypatch.setattr(hmz.daemon.api, "__path__", [str(tmp_path)])

    assert families() == {"settings.get": dict}


@pytest.mark.parametrize(
    "text",
    [
        "tcp://0.0.0.0:0",
        "ws://127.0.0.1:8080",
        "relay:wss://relay.example/x",
        "webrtc:ws://relay.example",
        "easytier:home",
    ],
)
def test_a_listener_spec_is_a_route_a_daemon_listens_on(text: str) -> None:
    assert str(spec(text)) == text


@pytest.mark.parametrize(
    "text",
    [
        "unix:",
        "stdio:local",
        "nothing",
        "tcp://h",
        "ws://h",
        "wss://h:1",
        "ws://h:1/x",
        "ws://h:0/x",
        "ws://h:x",
    ],
)
def test_anything_else_is_no_listener(text: str) -> None:
    with pytest.raises(ValueError, match=f"{text} is not a listener."):
        spec(text)


def _nobody(*_: object) -> Any:
    raise AssertionError("no client joins a listener that never opened")


def test_a_listener_still_being_opened_is_not_settled_until_it_could_not_be() -> None:
    # Its identity is the first thing a `relay:` listener asks for, on its own thread.
    asked, let = threading.Event(), threading.Event()

    def identity() -> Any:
        asked.set()
        let.wait(10)
        raise OSError("no identity can be made here")

    one = Listener("relay:ws://relay.invalid/", _nobody, identity, _nobody)
    try:
        assert asked.wait(10)
        assert not one.settled(0.05)
        let.set()
        assert one.settled(10)
        assert one.route == ""
    finally:
        let.set()
        one.close()


def test_a_listener_closed_before_it_opened_is_settled() -> None:
    let = threading.Event()

    def identity() -> Any:
        let.wait(10)
        raise OSError("no identity can be made here")

    one = Listener("relay:ws://relay.invalid/", _nobody, identity, _nobody)
    try:
        one.close()
        assert one.settled(0)
    finally:
        let.set()


class _Hosted:
    """A host that answers every call as told, and keeps what it was asked."""

    def __init__(self, answer: dict[str, Any]) -> None:
        self.answer = answer
        self.asked: list[tuple[str, dict[str, Any]]] = []

    def ask(self, client: str, said: dict[str, Any]) -> dict[str, Any]:
        self.asked.append((client, said))
        return self.answer


class _Sub:
    def __init__(self, hosted: _Hosted) -> None:
        self.hosted = hosted
        self.client = "c1"
        self.gone = False
        self.session: _Session | None = None


class _Session:
    def __init__(self, sub: _Sub, *, trusted: bool) -> None:
        self.trusted = trusted
        self.lock = threading.Lock()
        self.subs = {"s1": sub}
        sub.session = self


class _Router:
    def __init__(self, session: _Session) -> None:
        self._session = session

    def session(self, call: object) -> _Session:
        del call
        return self._session


def _served(
    *, trusted: bool = True, answer: dict[str, Any] | None = None
) -> tuple[dict[str, Handler], _Hosted]:
    hosted = _Hosted({"ok": True} if answer is None else answer)
    router = _Router(_Session(_Sub(hosted), trusted=trusted))
    return methods(cast("Router", router), {}), hosted


def _call(method: str, sub: str = "s1", **params: object) -> Call:
    return cast("Call", SimpleNamespace(method=method, params={"sub": sub, **params}))


@pytest.fixture
def held(monkeypatch: pytest.MonkeyPatch) -> dict[str, object]:
    """The settings file, as the daemon reads it: empty until a test fills it."""
    from hmz.coganchor import settings

    file: dict[str, object] = {}
    monkeypatch.setattr(settings, "read", lambda: file)
    return file


def test_every_call_to_an_environment_of_the_document_is_served() -> None:
    document = json.loads((ROOT / "protocol" / "openrpc.json").read_text("utf-8"))
    listed = {
        str(m["name"]) for m in document["methods"] if m["name"].startswith("env.")
    }
    served, _ = _served()

    assert {f"env.{one}" for one in ENV} == listed
    assert listed <= set(served)


@pytest.mark.parametrize("one", ENV)
def test_a_call_to_an_environment_asks_the_host_by_its_whole_name(one: str) -> None:
    served, hosted = _served(answer={"ok": True, "etag": "e"})

    answered = served[f"env.{one}"](
        _call(f"env.{one}", env="1:work", idem="k", path="a")
    )

    assert answered == {"etag": "e"}
    assert hosted.asked == [("c1", {"do": f"env.{one}", "env": "1:work", "path": "a"})]


def test_a_refusal_of_the_host_is_answered_409_with_its_why() -> None:
    served, _ = _served(answer={"ok": False, "why": "There is no environment 9:x."})

    with pytest.raises(RpcError) as refused:
        served["env.read"](_call("env.read", env="9:x", path="a"))
    assert (refused.value.code, refused.value.message) == (
        409,
        "There is no environment 9:x.",
    )


def test_a_refusal_of_the_host_naming_its_code_is_answered_with_it_and_its_data() -> (
    None
):
    errors = [{"path": ["verdict"], "message": "pick one"}]
    served, hosted = _served(
        answer={
            "ok": False,
            "why": "the answer does not fit: pick one",
            "code": 400,
            "data": {"errors": errors},
        }
    )

    with pytest.raises(RpcError) as refused:
        served["epic.answer"](_call("epic.answer", question="q1", value={}, idem="k"))
    assert (refused.value.code, refused.value.message, refused.value.data) == (
        400,
        "the answer does not fit: pick one",
        {"errors": errors},
    )
    assert hosted.asked == [("c1", {"do": "answer", "question": "q1", "value": {}})]


def test_a_face_is_read_from_the_host() -> None:
    served, hosted = _served(answer={"ok": True, "html": "<p>hi</p>", "title": "Hi"})

    assert served["epic.face"](_call("epic.face", hash="ab")) == {
        "html": "<p>hi</p>",
        "title": "Hi",
    }
    assert hosted.asked == [("c1", {"do": "face", "hash": "ab"})]


def test_a_call_naming_no_subscription_is_refused_410() -> None:
    served, hosted = _served()

    with pytest.raises(RpcError) as refused:
        served["env.list"](_call("env.list", sub="s9", env="1:w", path="."))
    assert refused.value.code == 410
    assert hosted.asked == []


@pytest.mark.parametrize("one", ["env.term.open", "env.term.input"])
@pytest.mark.parametrize(
    "envs", [None, "on", {}, {"paired_terminals": "yes"}, {"paired_terminals": False}]
)
def test_a_paired_device_opens_no_terminal_unless_the_setting_lets_it(
    one: str, envs: object, held: dict[str, object]
) -> None:
    if envs is not None:
        held["envs"] = envs
    served, hosted = _served(trusted=False)

    with pytest.raises(RpcError) as refused:
        served[one](_call(one, env="1:w", term="t1", cols=80, rows=24, data=""))
    assert (refused.value.code, refused.value.message) == (
        409,
        "Terminals are off for paired devices; turn on envs.paired_terminals.",
    )
    assert hosted.asked == []


def test_a_paired_device_naming_no_subscription_is_told_so_first(
    held: dict[str, object],
) -> None:
    del held
    served, _ = _served(trusted=False)

    with pytest.raises(RpcError) as refused:
        served["env.term.input"](_call("env.term.input", sub="s9", term="t1", data=""))
    assert refused.value.code == 410


def test_the_setting_lets_a_paired_device_open_a_terminal(
    held: dict[str, object],
) -> None:
    held["envs"] = {"paired_terminals": True}
    served, hosted = _served(trusted=False, answer={"ok": True, "term": "t1"})

    opened = served["env.term.open"](
        _call("env.term.open", env="1:w", cols=80, rows=24)
    )

    assert opened == {"term": "t1"}
    assert [said["do"] for _, said in hosted.asked] == ["env.term.open"]


def test_a_trusted_session_opens_terminals_without_the_setting(
    held: dict[str, object],
) -> None:
    del held
    served, hosted = _served(trusted=True)

    served["env.term.input"](_call("env.term.input", term="t1", data="bHM="))

    assert hosted.asked == [
        ("c1", {"do": "env.term.input", "term": "t1", "data": "bHM="})
    ]


@pytest.mark.parametrize(
    "one", [one for one in ENV if one not in ("term.open", "term.input")]
)
def test_a_paired_device_still_reaches_everything_else(
    one: str, held: dict[str, object]
) -> None:
    del held
    served, hosted = _served(trusted=False)

    served[f"env.{one}"](_call(f"env.{one}", env="1:w"))

    assert hosted.asked == [("c1", {"do": f"env.{one}", "env": "1:w"})]
