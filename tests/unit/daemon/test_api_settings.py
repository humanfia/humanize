"""`hmz.daemon.api.settings`: the settings read and written, and nothing signed in coming out."""

from __future__ import annotations

import json
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any, cast

import pytest

from hmz.daemon.api import settings
from hmz.rpc import RpcError

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

    from hmz.rpc import Call

#: A TURN server's credential, which a client must never be handed.
_SECRET = "turn-hunter2"


@pytest.fixture
def held(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """The settings file, as a dict that reads and changes stand in for."""
    from hmz.coganchor import settings as kept

    file: dict[str, Any] = {
        "easytier": {"lab": {"secret": "x" * 16, "nodes": ["tcp://n:1"]}},
        "ice_servers": [
            {"urls": "turn:t:3478", "username": "u", "credential": _SECRET}
        ],
    }

    def changes(change: Callable[[dict[str, Any]], None]) -> dict[str, Any]:
        change(file)
        return file

    monkeypatch.setattr(kept, "read", lambda: json.loads(json.dumps(file)))
    monkeypatch.setattr(kept, "changes", changes)
    return file


class _Settings:
    flow, ai_chan, details, enable_sentry = "ralph", "", False, None
    harness_sessions = False

    def __init__(self) -> None:
        self.forgot = False
        self.chat_agent: Any = None
        self.chat_prefer = "native"

    def flows(self) -> dict[str, Any]:
        return {}

    def detailing(self, *, on: bool) -> None:
        self.details = on

    def forget(self) -> bool:
        self.forgot = True
        return True


def _hmz() -> Any:
    return SimpleNamespace(
        workspace="/w",
        settings=_Settings(),
        verses=SimpleNamespace(plain=str),
        backups=SimpleNamespace(targets=list, defaults=list),
    )


def test_a_credential_is_shown_as_written_and_never_by_its_value(
    held: dict[str, Any],
) -> None:
    said = settings.read(_hmz())

    assert _SECRET not in json.dumps(said)
    assert said["ice_servers"] == [
        {"urls": "turn:t:3478", "username": "u", "credential": True}
    ]
    assert (said["workspace"], said["flow"], said["listen"]) == ("/w", "ralph", [])
    # No chat agent remembered yet, and `$` names going native.
    assert (said["chat"], said["prefer"]) == ("", "native")


def test_the_chat_agent_and_the_preference_are_written_as_settings_keeps_them(
    held: dict[str, Any],
) -> None:
    hmz = _hmz()

    said = settings.write(hmz, {"chat": "claude@work/opus:high", "prefer": "flow"})

    assert (said["chat"], said["prefer"]) == ("claude@work/opus:high", "flow")
    assert (hmz.settings.chat_agent.spec, hmz.settings.chat_agent.provider) == (
        "claude/opus:high",
        "work",
    )


def test_listeners_and_a_credential_sent_back_as_true_are_written(
    held: dict[str, Any],
) -> None:
    listen = [
        "tcp://0.0.0.0:0",
        "ws://127.0.0.1:0",
        "ws://127.0.0.1:8080",
        "easytier:lab",
    ]
    servers = [{"urls": "turn:t:3478", "username": "u", "credential": True}]

    said = settings.write(_hmz(), {"listen": listen, "ice_servers": servers})

    assert said["listen"] == listen
    assert held["listen"] == listen
    assert held["ice_servers"][0]["credential"] == _SECRET


@pytest.mark.parametrize(
    ("sent", "why"),
    [
        ({"listen": ["unix:/x"]}, "unix:/x is not a listener."),
        ({"listen": ["tcp://h"]}, "tcp://h is not a listener."),
        ({"listen": ["ws://h/x"]}, "ws://h/x is not a listener."),
        ({"listen": ["tcp://h:65536"]}, "tcp://h:65536 is not a listener."),
        ({"listen": ["easytier:gone"]}, "There is no EasyTier entry gone."),
        ({"ice_servers": [{"urls": "http://x"}]}, "ice_servers is a list of"),
        ({"ice_servers": [{"urls": "turn:new", "credential": True}]}, "Type the"),
        ({"details": "yes"}, "details is true or false."),
        ({"harness_sessions": 1}, "harness_sessions is true or false."),
        ({"chat": "opus"}, "chat is an agent as -a spells one: "),
        ({"prefer": "both"}, "prefer is native or flow."),
    ],
)
def test_a_value_refused_writes_nothing(
    held: dict[str, Any], sent: dict[str, Any], why: str
) -> None:
    hmz = _hmz()
    before = json.dumps(held)

    with pytest.raises(RpcError) as refused:
        settings.write(hmz, {"details": True, **sent})

    assert (refused.value.code, refused.value.message.startswith(why)) == (400, True)
    assert json.dumps(held) == before
    assert hmz.settings.details is False


def test_listing_harness_sessions_is_off_until_it_is_set(held: dict[str, Any]) -> None:
    del held
    hmz = _hmz()
    assert settings.read(hmz)["harness_sessions"] is False

    assert settings.write(hmz, {"harness_sessions": True})["harness_sessions"] is True

    assert hmz.settings.harness_sessions is True
    assert settings.write(hmz, {"details": True})["harness_sessions"] is True


def test_forgetting_says_whether_there_was_anything(held: dict[str, Any]) -> None:
    hmz = _hmz()

    assert settings.forget(hmz)["forgot"] is True
    assert hmz.settings.forgot


def test_a_workspace_is_a_whole_path_and_one_to_write_is_there(
    held: dict[str, Any], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import hmz.runtime

    made: list[Any] = []

    def built(at: Path) -> Any:
        made.append(at)
        return _hmz()

    monkeypatch.setattr(hmz.runtime, "Hmz", built, raising=False)

    def call(method: str, **params: Any) -> Any:
        return settings.METHODS[method](cast("Call", SimpleNamespace(params=params)))

    with pytest.raises(RpcError) as relative:
        call("settings.get", workspace="here")
    assert relative.value.message == "Say the workspace as a whole path, not here."
    with pytest.raises(RpcError) as missing:
        call("settings.set", workspace=str(tmp_path / "gone"))
    assert missing.value.code == 404
    assert missing.value.message == f"There is no directory {tmp_path / 'gone'}."
    assert call("settings.get", workspace=str(tmp_path / "gone"))["flow"] == "ralph"
    # What a workspace since removed was set up with is still forgotten.
    assert call("settings.forget", workspace=str(tmp_path / "gone"))["forgot"] is True
    assert made == [(tmp_path / "gone").resolve()] * 2
