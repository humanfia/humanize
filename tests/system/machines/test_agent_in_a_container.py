"""A real coding agent whose every file and command lands in a container of its own.

The agent -- `claude`, as whoever is signed in here -- runs on this machine, under the
supervisor, and nothing of it is installed in the image. The image is `python:3.12-slim`, which
has no sshd and no Claude in it: what the agent writes lands in the mounted workspace, and what
it runs is run inside the container, reached through `docker exec`. So a pass is the whole
container machine working for the thing it is for.

What is asked is checked where only the container could have answered it: the release the
image is (Debian, while this host need not be), and `/.dockerenv`, which docker puts in every
container and on no host.

Spends real tokens, on the cheapest model this machine's Claude offers, so it only runs with
`pytest --run-agents`.
"""

from __future__ import annotations

import contextlib
import shutil
import sys
from pathlib import Path

import pytest

from hmz.coganchor import prices, providers
from hmz.coganchor.agents import ClaudeCodeAgent, ClaudeCodeAgentConfig
from hmz.coganchor.machines import DockerConfig
from tests.machines.fixtures import IMAGE

pytestmark = pytest.mark.agent

#: The cheapest Claude there is, at the least effort it takes: the turn is two commands long.
_MODEL = "claude-haiku-4-5-20251001"

_ASKED = (
    "Do exactly these three things with your tools, then answer. "
    "1. Create a file named hello.txt whose entire contents are: made in a container "
    "2. Run this shell command: cat /etc/os-release > os-release.txt "
    "3. Run this shell command: test -f /.dockerenv && echo inside > where.txt "
    "Then reply with the PRETTY_NAME line from os-release.txt, and nothing else."
)


@pytest.mark.timeout(600)
def test_claude_works_inside_a_container_of_its_own(
    daemon: None, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    if shutil.which("claude") is None:
        pytest.skip("claude is not installed here")
    # A host that is itself a container, or is Debian, would answer both questions for the
    # container: neither answer would say where the command ran.
    if Path("/.dockerenv").exists():
        pytest.skip("this machine is a container itself")
    released_here = Path("/etc/os-release")
    if released_here.exists() and "Debian" in released_here.read_text():
        pytest.skip("this machine is Debian, as the image is")
    agent = ClaudeCodeAgent(
        ClaudeCodeAgentConfig(
            model=_MODEL,
            effort="low",
            permission="bypass",
            provider=providers.LOCAL,
            machine=DockerConfig(image=IMAGE, workspace=str(tmp_path)),
        )
    )
    with contextlib.ExitStack() as holding:
        holding.callback(agent.stop)
        session = agent.new()
        holding.callback(session.close)

        answer = session(_ASKED)
        spent = session.spent()

    # What it cost, for whoever runs this by hand: `-s` shows it.
    dollars = prices.cost(spent, _MODEL)
    with capsys.disabled():
        sys.stdout.write(
            f"\n{_MODEL} in a container: {dict(spent)} tokens, "
            f"{prices.money(dollars) if dollars is not None else 'no price known'}\n"
        )
    assert (tmp_path / "hello.txt").read_text().strip() == "made in a container"
    released = (tmp_path / "os-release.txt").read_text()
    assert "Debian" in released
    assert "Debian" in answer
    assert (tmp_path / "where.txt").read_text().strip() == "inside"
