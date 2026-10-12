"""A session its CLI logs on another machine, copied into the epic as it goes and whole after.

The stand-in `claude` driven natively through a fake `ssh`, which runs the far side here in a
home of its own; and the copying itself, down the road to a harness's machine whose CLI keeps
its home where that machine's own home says.
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

from hmz.coganchor.agents import ClaudeCodeAgent, ClaudeCodeAgentConfig
from hmz.coganchor.anchor import AnchorConfig
from hmz.coganchor.backends import named
from hmz.coganchor.machines import AnchoredConfig
from hmz.coganchor.tailing import EVERY, Tail, road
from hmz.runtime.epic import Epic, logs, sessions, where
from tests.integration.doubles_anchor import fakes
from tests.integration.doubles_core import MODEL, install

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

    import pytest


def _soon(found: Callable[[], object], within: float = 30.0) -> None:
    """Waits for `found()` to be truthy."""
    deadline = time.monotonic() + within
    while not found():
        assert time.monotonic() < deadline, "never copied"
        time.sleep(0.1)


def test_a_native_session_is_copied_into_the_epic_while_open_and_whole_after(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = install(tmp_path, monkeypatch)
    fakes(tmp_path, monkeypatch)
    monkeypatch.delenv("HUMANIZE_SESSIONS", raising=False)
    anchor = AnchorConfig(
        target=f"ssh://box-{tmp_path.name}", workspace=str(project), native=True
    )
    agent = ClaudeCodeAgent(
        ClaudeCodeAgentConfig(
            model=MODEL, effort="high", machine=AnchoredConfig(anchor=anchor)
        )
    )
    with Epic("f", "t", project) as epic:
        agent.epic = epic
        session = agent.new()
        session("hello")
        ident = session.id
        (far,) = (tmp_path / "claude").glob(f"projects/*/{ident}.jsonl")
        copied = epic.keeps / "claude"
        assert agent.kept() == copied

        _soon(lambda: list(copied.glob(f"projects/*/{ident}.jsonl")))
        session("again")
        session.close()

    (copy,) = copied.glob(f"projects/*/{ident}.jsonl")
    assert copy.read_bytes() == far.read_bytes()
    assert b"again" in copy.read_bytes()
    at = epic.journal.parent
    (one,) = sessions(at)
    assert where(at, one) == copied
    assert list(logs(at, one).values()) == [copy]


def test_what_a_cli_elsewhere_logs_is_copied_from_its_own_home_in_whole_lines(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    far = fakes(tmp_path, monkeypatch)
    monkeypatch.delenv("CLAUDE_CONFIG_DIR", raising=False)
    anchor = AnchorConfig(
        target=f"ssh://work-{tmp_path.name}", harness=f"ssh://gpu-{tmp_path.name}"
    )
    way = road(anchor)
    profile = named("claude")
    assert way is not None
    assert profile is not None
    logged = far.home / ".claude" / "projects" / "-w" / "s1.jsonl"
    logged.parent.mkdir(parents=True)
    logged.write_bytes(b'{"one": 1}\n{"two"')
    copied = tmp_path / "epic" / "sessions" / "claude"
    tail = Tail(way, profile, copied)

    tail.copy(["s1"])
    assert (copied / "projects" / "-w" / "s1.jsonl").read_bytes() == b'{"one": 1}\n'

    with logged.open("ab") as more:
        more.write(b': 2}\n{"three"')
    tail.follow("s1")
    _soon(
        lambda: (
            (copied / "projects" / "-w" / "s1.jsonl").read_bytes()
            == b'{"one": 1}\n{"two": 2}\n'
        ),
        within=EVERY * 10,
    )
    tail.forget("s1")
    assert (copied / "projects" / "-w" / "s1.jsonl").read_bytes() == logged.read_bytes()
    assert not list(copied.glob("projects/*/s2.jsonl"))
