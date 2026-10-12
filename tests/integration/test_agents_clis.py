"""A flow's own command lines, run by stand-in agent CLIs from their own shells.

Each stand-in takes the prompt as a shell line, runs it with the environment the driver started
it with -- which is what a real CLI's shell inherits -- and answers with what the line printed
and exited with. So what is checked is the whole road: the shelf's script on the PATH the
driver handed down, `hmz internal cli` started by it, the socket, the parser and the flow's
function, and the status and the streams carried back.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from pydantic import BaseModel, Field

from hmz.coganchor.agents import (
    AgentBase,
    ClaudeCodeAgent,
    ClaudeCodeAgentConfig,
    CursorAgent,
    CursorAgentConfig,
    FakeCli,
    FakeCommand,
    SessionBase,
)
from tests.integration.doubles_agents import standins

if TYPE_CHECKING:
    from collections.abc import Callable

#: What every stand-in does with a prompt: runs it, and says how that went as JSON.
_RUNS = r"""
import subprocess


def ran(line):
    done = subprocess.run(line, shell=True, capture_output=True, text=True)
    return json.dumps({"code": done.returncode, "out": done.stdout, "err": done.stderr})
"""

CLAUDE = (
    _RUNS
    + r"""
note()
session = flags.get("--session-id") or flags.get("--resume") or "s-none"
out({"type": "system", "subtype": "init", "session_id": session, "model": "m"})
for line in sys.stdin:
    said = json.loads(line)["message"]["content"][0]["text"]
    note(said)
    out({"type": "result", "subtype": "success", "is_error": False, "session_id": session,
         "result": ran(said), "usage": {"input_tokens": 1, "output_tokens": 1}})
"""
)

CURSOR = (
    _RUNS
    + r"""
note(argv[-1])
chat = next((one for one in argv if one.startswith("--resume=")), "=chat-1").partition("=")[2]
out({"type": "system", "subtype": "init", "session_id": chat, "model": "m"})
out({"type": "result", "subtype": "success", "is_error": False, "session_id": chat,
     "result": ran(argv[-1]), "usage": {"inputTokens": 1, "outputTokens": 1}})
"""
)


CLAUDED = ClaudeCodeAgentConfig(model="m", effort="high")
CURSORED = CursorAgentConfig(model="m", effort="high")


class File(BaseModel):
    title: str = Field(description="what the ticket says")
    points: int = Field(3, description="how big it is")


def _tickets(filed: list[File]) -> FakeCli:
    """A command line whose `file` command keeps what it was given in `filed`."""

    def files(ticket: File) -> str:
        filed.append(ticket)
        return f"filed #{len(filed)}"

    def full() -> None:
        raise SystemExit(4)

    return FakeCli(
        "tix",
        "Track the tickets of this flow.",
        (
            FakeCommand("file", "File a ticket.", files, File),
            FakeCommand("full", "Say the queue is full.", full),
        ),
    )


def _ran(session: SessionBase, line: str) -> dict[str, object]:
    return json.loads(session(line))


@pytest.mark.parametrize(
    ("cli", "body", "make"),
    [
        ("claude", CLAUDE, lambda: ClaudeCodeAgent(CLAUDED)),
        ("cursor-agent", CURSOR, lambda: CursorAgent(CURSORED)),
    ],
    ids=["claude", "cursor"],
)
def test_an_agents_shell_runs_the_flows_command_line(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    cli: str,
    body: str,
    make: Callable[[], AgentBase],
) -> None:
    held = standins(tmp_path, monkeypatch)
    held.install(cli, body)
    filed: list[File] = []
    session = make().new()
    session.shelves([_tickets(filed)])

    helped = _ran(session, "tix --help")
    assert helped["code"] == 0
    assert "Track the tickets of this flow." in str(helped["out"])
    assert "file" in str(helped["out"])
    assert "full" in str(helped["out"])

    told = _ran(session, "tix file --help")
    assert told["code"] == 0
    assert "--title TITLE" in str(told["out"])
    assert "what the ticket says" in str(told["out"])

    assert _ran(session, "tix file --title 'the build is red' --points 5") == {
        "code": 0,
        "out": "filed #1\n",
        "err": "",
    }
    assert filed == [File(title="the build is red", points=5)]

    wrong = _ran(session, "tix file --points many")
    assert wrong["code"] == 2
    assert "usage: tix file" in str(wrong["err"])
    assert "--title" in str(wrong["err"])

    assert _ran(session, "tix full")["code"] == 4
    assert len(filed) == 1


def test_a_held_process_started_before_anything_was_shelved_is_started_again(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    held = standins(tmp_path, monkeypatch)
    held.install("claude", CLAUDE)
    session = ClaudeCodeAgent(CLAUDED).new()

    assert _ran(session, "tix --help")["code"] == 127
    session.shelves([_tickets([])])
    assert _ran(session, "tix --help")["code"] == 0

    launches = [one.pid for one in held.calls("claude") if not one.stdin]
    assert len(set(launches)) == 2


def test_a_command_line_taken_back_is_not_found_and_the_shelf_goes_with_the_agent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    held = standins(tmp_path, monkeypatch)
    held.install("cursor-agent", CURSOR)
    agent = CursorAgent(CURSORED)
    session = agent.new()
    session.shelves([_tickets([])])
    assert _ran(session, "tix full")["code"] == 4

    session.shelves(None)
    assert _ran(session, "tix full")["code"] == 127
    where = agent.shelf.where()
    assert where
    session.close()
    agent.shelf.close()
    assert not Path(where).exists()
    assert agent.shelf.empty()


class Helpless(BaseModel):
    help: str


def test_a_command_line_no_parser_can_be_built_for_fails_rather_than_hangs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    held = standins(tmp_path, monkeypatch)
    held.install("cursor-agent", CURSOR)
    session = CursorAgent(CURSORED).new()
    session.shelves(
        [FakeCli("odd", "Odd.", (FakeCommand("go", "Go.", print, Helpless),))]
    )

    ran = _ran(session, "odd go --help")
    assert ran["code"] == 1
    assert "odd: ArgumentError" in str(ran["err"])
