"""The three command-line backends against the real binaries.

The stand-ins elsewhere print a protocol; this is the protocol. What it pins is what only the
real thing can confirm: that pi resumes the session it was pinned to and takes a word put into
a running turn, and that opencode and mimocode carry a conversation across two runs and say
what each of them cost.

Each runs in a directory of its own, so an agent that decides to tidy up tidies up nothing of
this project's.
"""

from __future__ import annotations

import shutil
import subprocess
from typing import TYPE_CHECKING, NoReturn

import pytest

from hmz.coganchor.agents import (
    Event,
    Failed,
    MimoCodeAgent,
    MimoCodeAgentConfig,
    OpencodeAgent,
    OpencodeAgentConfig,
    PiAgent,
    PiAgentConfig,
    SessionBase,
)

if TYPE_CHECKING:
    from pathlib import Path

#: Small and quick: what is being tested is the plumbing, not the model.
PI = PiAgentConfig(model="openai-codex/gpt-5.4-mini", effort="low")
OPENCODE = OpencodeAgentConfig(model="opencode/nemotron-3-ultra-free", effort="low")
MIMO = MimoCodeAgentConfig(model="openai/gpt-5.4-mini", effort="low")


@pytest.fixture
def workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A directory of its own for the turn to work in, which is where it is run from."""
    monkeypatch.chdir(tmp_path)
    return tmp_path


def _refused(cli: str, why: subprocess.CalledProcessError) -> NoReturn:
    """Skips this test with what the CLI said about the turn it would not take.

    Installed is not signed in, and the `which` above each of these only answers the first.
    An account that has lapsed, a free tier that has ended, a model that account does not
    serve -- each of those is this machine rather than this driver, and each of them fails
    on the first turn rather than before it. So it is skipped with what the CLI itself said:
    a suite that reads red for somebody's expired subscription is a suite nobody reads, and
    one that said only `skipped` would leave them guessing which of the five it was.

    The check before the skip is the one `tests/agents/test_every_backend.py` makes of every
    backend installed here, and it is the whole reason a refusal may be skipped rather than
    failed: what humanize owes whoever is at the prompt is not the exit status but the
    sentence, so a failure carrying nothing but a number is this driver's bug after all and
    stays red.

    Args:
      cli: The backend, named as it is on PATH.
      why: What the turn stopped on.

    Raises:
      Skipped: Always -- this machine cannot run that turn, and says why.
    """
    assert isinstance(why, Failed), (
        f"{cli}: a turn that failed must say why, and this said only its exit status"
    )
    told = str(why).partition("status")[2]
    assert told.strip(" .0123456789"), f"{cli}: nothing was said about why it failed"
    pytest.skip(f"{cli} would not take a turn on this machine: {why}")


def _opens(cli: str, session: SessionBase, prompt: str) -> list[Event]:
    """The opening turn of one of these, or a skip saying why it would not take one.

    Args:
      cli: The backend, named as it is on PATH.
      session: The conversation to open, which has run no turn yet.
      prompt: What to open it with.

    Returns:
      Everything the turn said.
    """
    try:
        return list(session.stream(prompt))
    except subprocess.CalledProcessError as why:
        _refused(cli, why)


@pytest.mark.agent
@pytest.mark.timeout(600)
def test_pi_carries_a_conversation_and_says_what_it_cost(workspace: Path) -> None:
    if shutil.which("pi") is None:
        pytest.skip("pi is not installed here")
    session = PiAgent(PI).new()
    said = _opens("pi", session, "Remember the number 4711. Reply with exactly: OK")

    assert said[-1].kind == "result"
    assert "OK" in said[-1].text
    assert sum(said[-1].tokens.values()) > 0  # it says what the turn cost
    assert session.id  # and names the session the turn landed in
    # The same conversation, resumed: the second turn has the first one in context.
    assert "4711" in session("What number did I ask you to remember? Digits only.")


@pytest.mark.agent
@pytest.mark.timeout(600)
def test_pi_takes_a_word_put_into_the_turn_it_is_running(workspace: Path) -> None:
    if shutil.which("pi") is None:
        pytest.skip("pi is not installed here")
    session = PiAgent(PI).new()

    # Put in at the first thing the agent says rather than after a wait: the turn is provably
    # under way by then, however fast the model happens to be today.
    said: list[Event] = []
    try:
        counting = "Count from 1 to 40, one number per line. No tools."
        for event in session.stream(counting):
            if not said:
                session.interject(
                    "STOP. Ignore the counting. Reply with exactly: STEERED"
                )
            said.append(event)
    except subprocess.CalledProcessError as why:
        # The same gate as everywhere else here, opened out because the word put in has to
        # go in while the turn is running and so cannot be said from behind :func:`_opens`.
        _refused("pi", why)

    assert said[-1].kind == "result"
    assert (
        sum(event.kind == "result" for event in said) == 1
    )  # one turn, two things said
    assert "STEERED" in said[-1].text
    # And nothing of it was left behind for the next turn to pick up as its own.
    assert "SECOND" in session("Reply with exactly: SECOND")


@pytest.mark.agent
@pytest.mark.timeout(600)
def test_pi_runs_a_tool_where_the_turn_lands(workspace: Path) -> None:
    if shutil.which("pi") is None:
        pytest.skip("pi is not installed here")
    session = PiAgent(PI).new()
    said = _opens("pi", session, "Use the bash tool to run `echo hi`, then reply: DONE")

    assert any(event.kind == "tool" for event in said)
    assert said[-1].kind == "result"


@pytest.mark.agent
@pytest.mark.timeout(600)
def test_opencode_carries_a_conversation_across_two_runs(workspace: Path) -> None:
    if shutil.which("opencode") is None:
        pytest.skip("opencode is not installed here")
    session = OpencodeAgent(OPENCODE).new()
    said = _opens(
        "opencode", session, "Remember the number 4711. Reply with exactly: OK"
    )

    assert said[-1].kind == "result"
    assert "OK" in said[-1].text
    assert sum(said[-1].tokens.values()) > 0
    assert session.id.startswith("ses_")
    # A run of its own, resuming the session the first one opened.
    assert "4711" in session("What number did I ask you to remember? Digits only.")


@pytest.mark.agent
@pytest.mark.timeout(600)
def test_mimo_is_the_same_program_under_its_own_name(workspace: Path) -> None:
    if shutil.which("mimo") is None:
        pytest.skip("mimocode is not installed here")
    session = MimoCodeAgent(MIMO).new()
    said = _opens("mimo", session, "Reply with exactly: OK")

    assert said[-1].kind == "result"
    assert "OK" in said[-1].text
    assert session.id.startswith("ses_")
