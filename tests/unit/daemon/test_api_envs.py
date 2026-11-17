"""`hmz.daemon.api.envs`: each `hosts.env.*` carried to the host it names, attaching nobody."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast
from unittest import mock

import pytest

from hmz.daemon import routing, where
from hmz.daemon.api import envs
from hmz.rpc import RpcError

if TYPE_CHECKING:
    from pathlib import Path

    from hmz.rpc import Call


def _call(**params: Any) -> Call:
    return cast("Call", mock.Mock(params=params))


@pytest.fixture
def hosts(monkeypatch: pytest.MonkeyPatch) -> mock.Mock:
    held = mock.Mock()
    monkeypatch.setattr(routing, "serving", mock.Mock(hosts=held))
    return held


def test_every_method_is_named() -> None:
    assert sorted(envs.METHODS) == [
        "hosts.env.exec",
        "hosts.env.grep",
        "hosts.env.list",
        "hosts.env.read",
        "hosts.env.write",
    ]


def test_a_call_is_asked_of_the_host_it_names_less_where_it_is(
    hosts: mock.Mock, tmp_path: Path
) -> None:
    hosted = hosts.get.return_value
    hosted.env.return_value = {"ok": True, "size": 2}

    said = envs.METHODS["hosts.env.write"](
        _call(
            workspace=str(tmp_path),
            slot="chat:0a",
            env="w",
            path="a",
            text="hi",
            idem="i",
        )
    )

    assert said == {"size": 2}
    hosts.get.assert_called_once_with(where.workspace(tmp_path), "chat:0a")
    hosted.env.assert_called_once_with(
        {"do": "hosts.env.write", "env": "w", "path": "a", "text": "hi"}
    )


def test_a_refusal_is_said_with_the_code_the_host_gave(
    hosts: mock.Mock, tmp_path: Path
) -> None:
    hosts.get.return_value.env.return_value = {"ok": False, "why": "gone", "code": 404}

    with pytest.raises(RpcError) as refused:
        envs.METHODS["hosts.env.read"](
            _call(workspace=str(tmp_path), env="w", path="a")
        )

    assert (refused.value.code, refused.value.message) == (404, "gone")


def test_a_workspace_no_host_holds_has_no_env_open(
    hosts: mock.Mock, tmp_path: Path
) -> None:
    hosts.get.return_value = None

    with pytest.raises(RpcError) as refused:
        envs.METHODS["hosts.env.list"](_call(workspace=str(tmp_path)))

    assert (refused.value.code, refused.value.message) == (
        409,
        "no flow is running, so no env is open",
    )
