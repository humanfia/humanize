"""`hmz.coganchor.agents.preload`: what a Node CLI's own runtime says it did."""

from __future__ import annotations

import gc
import socket
import tempfile
from pathlib import Path
from typing import NoReturn

import pytest

from hmz.coganchor.agents.hooks import Hooks, Moment, Occasion, Verdict
from hmz.coganchor.agents.preload import RUNTIME, Watch, preloaded, reported, runtime
from tests.unit.coganchor.agents.doubles_core import Scripted


class _Socket:
    """A listening socket that is never listened on: bound, and closed when asked."""

    def __init__(self, *_: object) -> None:
        self.bound = ""

    def bind(self, at: str) -> None:
        self.bound = at

    def listen(self, _: int) -> None:
        pass

    def settimeout(self, _: float) -> None:
        pass

    def accept(self) -> NoReturn:
        raise OSError("closed")

    def close(self) -> None:
        pass


@pytest.fixture
def no_socket(monkeypatch: pytest.MonkeyPatch) -> None:
    """Sockets that bind nothing, so a listener can be started without one."""
    monkeypatch.setattr(socket, "socket", _Socket)


@pytest.fixture
def no_room(monkeypatch: pytest.MonkeyPatch) -> None:
    """A machine with no directory to spare for a socket."""

    def refuse(*_: object, **__: object) -> NoReturn:
        raise OSError("no room")

    monkeypatch.setattr(tempfile, "TemporaryDirectory", refuse)


def test_runtime_is_the_shipped_file() -> None:
    at = Path(runtime())
    assert at.name == RUNTIME
    assert at.is_absolute()
    assert at.is_file()


@pytest.mark.parametrize(
    ("line", "said"),
    [
        ('{"did": "spawn", "what": "ls -la"}', ("spawn", "ls -la")),
        ('{"did": "quiet"}', ("quiet", "")),
        ('{"did": "read", "what": 3}', ("read", "")),
        ('{"did": ""}', None),
        ('{"what": "x"}', None),
        ('["spawn"]', None),
        ("not json", None),
    ],
)
def test_reported(line: str, said: tuple[str, str] | None) -> None:
    assert reported(line) == said


def test_nothing_is_added_where_nothing_is_listening() -> None:
    agent = Scripted()
    assert preloaded(agent, {"A": "1"}) == {"A": "1"}


def test_nothing_is_added_where_no_socket_can_be_made(no_room: None) -> None:
    agent = Scripted()
    agent.hooks.on(Moment.PRE_TOOL_USE, lambda _: None)
    assert preloaded(agent, {"A": "1"}) == {"A": "1"}


def test_the_preload_goes_on_the_end_of_node_options(
    no_socket: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("NODE_OPTIONS", "--max-old-space-size=4096")
    agent = Scripted()
    agent.hooks.on(Moment.PRE_TOOL_USE, lambda _: None)
    held = preloaded(agent, {"A": "1"})
    assert held["A"] == "1"
    assert held["NODE_OPTIONS"].startswith("--max-old-space-size=4096 --require ")
    assert held["NODE_OPTIONS"].endswith(runtime()) or held["NODE_OPTIONS"].endswith(
        f'"{runtime()}"'
    )
    assert held["HMZ_PRELOAD_AT"].endswith("said.sock")
    again = preloaded(agent, {"NODE_OPTIONS": "--mine"})
    assert again["NODE_OPTIONS"].startswith("--mine --require ")
    assert again["HMZ_PRELOAD_AT"] == held["HMZ_PRELOAD_AT"]  # one listener per agent


def test_a_watch_tells_the_hooks_what_the_runtime_did() -> None:
    hooks = Hooks(frozenset(Moment), "agent-1")
    told: list[Occasion] = []
    hooks.on(Moment.PRE_TOOL_USE, told.append)

    def raises(_: Occasion) -> NoReturn:
        raise RuntimeError

    hooks.on(Moment.PRE_TOOL_USE, raises)
    hooks.on(Moment.PRE_TOOL_USE, lambda _: Verdict(refused=True))  # told, not asked
    watch = Watch(hooks)
    watch.tells('{"did": "spawn", "what": "git status"}')
    watch.tells("garbage")
    assert told == [
        Occasion(
            moment=Moment.PRE_TOOL_USE,
            agent="agent-1",
            tool="spawn",
            about="git status",
        )
    ]


def test_a_watch_whose_agent_has_gone_tells_nobody() -> None:
    told: list[Occasion] = []
    hooks = Hooks(frozenset(Moment), "gone")
    hooks.on(Moment.PRE_TOOL_USE, told.append)
    watch = Watch(hooks)
    del hooks
    gc.collect()
    watch.tells('{"did": "spawn"}')
    assert told == []


def test_a_watch_that_cannot_listen_says_so(no_room: None) -> None:
    watch = Watch(Hooks(frozenset(Moment), "a"))
    assert watch.address() == ""
    watch.close()
    watch.close()


def test_a_watch_listens_once_until_closed(no_socket: None) -> None:
    watch = Watch(Hooks(frozenset(Moment), "a"))
    at = watch.address()
    assert at.endswith("said.sock")
    assert watch.address() == at
    watch.close()
    assert not Path(at).parent.exists()
