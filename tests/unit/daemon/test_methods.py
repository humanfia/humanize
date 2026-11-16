"""`hmz.daemon.methods` and `hmz.daemon.listening`: what a call names, and listener specs."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from hmz.daemon import where
from hmz.daemon.listening import spec
from hmz.daemon.methods import EPIC, families, slot, workspace
from hmz.rpc import RpcError

if TYPE_CHECKING:
    from pathlib import Path


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

    (tmp_path / "stubbed.py").write_text('METHODS = {"settings.get": dict}\n')
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


@pytest.mark.parametrize("text", ["unix:", "stdio:local", "nothing", "tcp://h"])
def test_anything_else_is_no_listener(text: str) -> None:
    with pytest.raises(ValueError, match=f"{text} is not a listener."):
        spec(text)
