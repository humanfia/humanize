"""A session its CLI logs on another machine, copied into the epic as it goes and whole after.

The stand-in `claude` driven natively through a fake `ssh`, which runs the far side here in a
home of its own; and the copying itself, down the road to a harness's machine whose CLI keeps
its home where that machine's own home says.
"""

from __future__ import annotations

import subprocess
import time
from pathlib import Path
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


#: A turn keeping a session under its home, which a provider moved into its private directory.
_KEEPS_UNDER_ITS_HOME = (
    'mkdir -p "$CLAUDE_CONFIG_DIR/projects/-w" && '
    'echo kept > "$CLAUDE_CONFIG_DIR/projects/-w/s1.jsonl" && echo "$CLAUDE_CONFIG_DIR"'
)


def test_a_session_under_a_projected_home_is_brought_back_before_the_home_goes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fakes(tmp_path, monkeypatch)
    project = tmp_path / "project"
    project.mkdir()
    creds = tmp_path / "creds"
    creds.mkdir()
    (creds / ".credentials.json").write_text("a token\n")
    copied = tmp_path / "epic" / "sessions" / "claude"
    settings = AnchorConfig(
        target=f"ssh://box-{tmp_path.name}",
        workspace=str(project),
        native=True,
        projects=(("CLAUDE_CONFIG_DIR", str(creds)),),
        brings=(("CLAUDE_CONFIG_DIR/projects", str(copied)),),
    )

    done = subprocess.run(
        settings.command(["/bin/sh", "-c", _KEEPS_UNDER_ITS_HOME]),
        capture_output=True,
        timeout=60,
        check=False,
    )

    assert done.returncode == 0, done.stderr
    assert (copied / "projects" / "-w" / "s1.jsonl").read_text() == "kept\n"
    assert not (copied / ".credentials.json").exists()
    assert not Path(done.stdout.decode().strip()).exists()


#: A turn keeping a session under a projected home, a line now and one more once told to go.
_KEEPS_AS_IT_GOES = (
    'mkdir -p "$CLAUDE_CONFIG_DIR/projects/-w" && '
    'echo one > "$CLAUDE_CONFIG_DIR/projects/-w/s1.jsonl" && '
    'while [ ! -e "$1" ]; do sleep 0.1; done && '
    'echo two >> "$CLAUDE_CONFIG_DIR/projects/-w/s1.jsonl"'
)


def test_a_session_under_a_projected_home_is_copied_as_it_goes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fakes(tmp_path, monkeypatch)
    project = tmp_path / "project"
    project.mkdir()
    creds = tmp_path / "creds"
    creds.mkdir()
    (creds / ".credentials.json").write_text("a token\n")
    copied = tmp_path / "epic" / "sessions" / "claude"
    told = tmp_path / "homes"
    told.mkdir()
    go = tmp_path / "go"
    settings = AnchorConfig(
        target=f"ssh://box-{tmp_path.name}",
        workspace=str(project),
        native=True,
        projects=(("CLAUDE_CONFIG_DIR", str(creds)),),
        brings=(("CLAUDE_CONFIG_DIR/projects", str(copied)),),
        tells=str(told),
    )
    way = road(settings)
    profile = named("claude")
    assert way is not None
    assert profile is not None
    tail = Tail(way, profile, copied, told=told)
    copy = copied / "projects" / "-w" / "s1.jsonl"

    turn = subprocess.Popen(
        settings.command(["/bin/sh", "-c", _KEEPS_AS_IT_GOES, "turn", str(go)]),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
    )
    try:
        tail.follow("s1")
        _soon(lambda: copy.is_file() and copy.read_bytes() == b"one\n")
        (telling,) = told.iterdir()
        (landed,) = telling.read_text().splitlines()
        assert landed.startswith("CLAUDE_CONFIG_DIR=/")
    finally:
        go.touch()
        _, said = turn.communicate(timeout=60)
    assert turn.returncode == 0, said
    tail.forget("s1")
    assert copy.read_bytes() == b"one\ntwo\n"
    assert not list(told.iterdir()), "told only while the turn runs"
    assert not (copied / ".credentials.json").exists()
