"""The environment a command is run with here, and a fenced one this machine refuses."""

from __future__ import annotations

import errno
import os

import pytest

from hmz.coganchor import fence
from hmz.coganchor.proto import Kind
from hmz.coganchor.serve.exports import ExportTable
from hmz.coganchor.serve.sessions import (
    HOST_SPECIFIC_ENV,
    HOST_SPECIFIC_PREFIXES,
    ExecSession,
    compose_env,
)
from tests.unit.coganchor.doubles_u8 import frames, wire


def test_this_machines_environment_is_the_base(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HERE_ONLY", "kept")
    env = compose_env({}, "/w", tty=False)
    assert env["HERE_ONLY"] == "kept"
    assert env["PWD"] == "/w"
    assert env.get("PATH") == os.environ.get("PATH")


@pytest.mark.parametrize("name", sorted(HOST_SPECIFIC_ENV - {"PWD"}))
def test_what_describes_the_clients_machine_is_left_there(
    name: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(name, "here")
    assert compose_env({name: "there"}, "/w", tty=False)[name] == "here"


@pytest.mark.parametrize("prefix", HOST_SPECIFIC_PREFIXES)
def test_what_is_prefixed_as_the_clients_is_left_there(prefix: str) -> None:
    assert f"{prefix}THING" not in compose_env({f"{prefix}THING": "x"}, "/w", tty=False)


def test_what_the_agent_set_crosses(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GIT_AUTHOR_NAME", "here")
    env = compose_env({"GIT_AUTHOR_NAME": "agent", "API_KEY": "k"}, "/w", tty=False)
    assert (env["GIT_AUTHOR_NAME"], env["API_KEY"]) == ("agent", "k")


@pytest.mark.parametrize(
    ("tty", "given", "term"),
    [(True, None, "xterm-256color"), (True, "vt100", "vt100"), (False, None, None)],
)
def test_a_terminal_gets_a_term(
    tty: bool, given: str | None, term: str | None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("TERM", raising=False)
    asked = {"TERM": given} if given else {}
    assert compose_env(asked, "/w", tty=tty).get("TERM") == term


def test_a_fenced_command_this_machine_cannot_fence_is_refused(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def enforceable(*, net: bool) -> bool:
        return False

    monkeypatch.setattr(fence, "enforceable", enforceable)
    channel, sent = wire()
    session = ExecSession(
        3,
        channel,
        ExportTable.parse(["/w"], insensitive=False),
        {"argv": ["ls"], "cwd": "/w", "fence": {"online": True}},
    )
    session.start()
    session.join(5)
    (said,) = frames(sent.getvalue())
    assert (said.kind, said.msg_id) == (Kind.ERR, 3)
    assert said.meta["errno"] == errno.EPERM
    assert "cannot fence" in said.meta["strerror"]
