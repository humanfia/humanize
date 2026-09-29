"""Two people at two interfaces on one run, each in a terminal of its own.

A tmux server of the test's own, a pane per person, each running `hmz` as a person types it in
the same directory: the first starts a host and a run, the second reads the same run from the
top as an interface of its own. Keys go in with `send-keys` and what each screen says is read
back with `capture-pane`, which is what makes this the system tier -- a real multiplexer, real
terminals, and a real host forked in the background.

The flow asks two people outside it and drives no agent, so nothing here spends a token but
for the last test, which steers a real Claude from one interface while the other watches, and
is asked for with `--run-agents`.
"""

from __future__ import annotations

import shlex
import shutil
import sys
import time
from typing import TYPE_CHECKING

import pytest

from hmz import daemon
from hmz.runtime import Hmz
from hmz.runtime.kept import Runs
from tests.stubs import written
from tests.tui.panes import ASKS, Panes

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path

pytestmark = pytest.mark.skipif(
    shutil.which("tmux") is None, reason="drives tmux, which is not installed here"
)

#: How long a test waits for something it cannot see yet.
PATIENCE = 60.0

#: What the flow is offered as, being this project's own.
FLOW = "local/asks"


@pytest.fixture
def workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    where = tmp_path / "project"
    where.mkdir()
    written(where / ".humanize" / "flows", "asks", ASKS)
    monkeypatch.chdir(where)
    # Set up the way saving the flow menu would, so that `$` starts it on the spot.
    Hmz(where).settings.remember(FLOW, {}, budget={"cost": 1})
    # Every pane reads as a pipe would, and holds its runs apart, as a person's would.
    monkeypatch.delenv("FORCE_COLOR", raising=False)
    monkeypatch.setenv("NO_COLOR", "1")
    monkeypatch.delenv("HUMANIZE_DAEMON", raising=False)
    return where


@pytest.fixture
def panes(workspace: Path) -> Iterator[Panes]:
    held = Panes(workspace)
    try:
        yield held
    finally:
        held.close()
        found = daemon.running(workspace)
        if found is not None:
            found.kill()


def _hmz(name: str) -> str:
    return f"HUMANIZE_NAME={name} {shlex.join([sys.executable, '-m', 'hmz'])}"


def _gone(workspace: Path) -> bool:
    deadline = time.monotonic() + PATIENCE
    while time.monotonic() < deadline:
        if daemon.running(workspace) is None:
            return True
        time.sleep(0.2)
    return False


@pytest.mark.timeout(240)
def test_two_interfaces_each_answer_for_their_own_part(
    panes: Panes, workspace: Path
) -> None:
    alice = panes.opens(_hmz("alice"))
    panes.waits(alice, "humanize")
    panes.types(alice, f"${FLOW} the parser")
    panes.waits(alice, "what is the plan for the parser?")

    # A second interface of its own, reading the run from the top.
    bob = panes.opens(_hmz("bob"))
    panes.waits(bob, "the parser · by alice@tui")
    panes.waits(bob, "what is the plan for the parser?")
    # Round to the reviewer's transcript -- the shared one, the planner's, the reviewer's --
    # and hold it.
    panes.presses(bob, "BTab")
    panes.presses(bob, "BTab")
    panes.waits(bob, "reading outworlder reviewer")
    panes.types(bob, "/claim")
    panes.waits(bob, "only you can answer for reviewer")
    panes.waits(alice, "reviewer · outworlder · bob@tui's")

    panes.types(alice, "a plan from alice")
    panes.waits(bob, "is 'a plan from alice' good?")
    # The reviewer's question is bob's: alice is told so rather than asked.
    panes.waits(alice, "bob@tui's to answer")
    panes.types(bob, "fine by bob")
    panes.waits(alice, "fine by bob · by bob@tui")

    for one in (alice, bob):
        panes.waits(one, "— the flow is done —")
    # Back on the shared transcript, bob reads what alice answered, and that she did.
    panes.presses(bob, "BTab")
    panes.waits(bob, "a plan from alice · by alice@tui")
    assert (workspace / "result.json").read_text() == (
        '{"plan": "a plan from alice", "review": "fine by bob"}'
    )

    # Leaving with nothing running lets go of each, and the host with the last of them.
    for one in (alice, bob):
        panes.types(one, "/exit")
    assert _gone(workspace)


@pytest.mark.timeout(240)
def test_one_leaves_it_running_comes_back_and_the_other_stops_it(
    panes: Panes, workspace: Path
) -> None:
    alice = panes.opens(_hmz("alice"))
    panes.waits(alice, "humanize")
    panes.types(alice, f"${FLOW} the parser")
    panes.waits(alice, "what is the plan for the parser?")
    bob = panes.opens(_hmz("bob"))
    panes.waits(bob, "what is the plan for the parser?")

    # Alice leaves, and leaves the run running: her interface goes, the run does not.
    panes.types(alice, "/exit")
    panes.waits(alice, "detach and exit")
    panes.presses(alice, "Down")
    panes.presses(alice, "Enter")
    time.sleep(2.0)
    found = daemon.running(workspace)
    assert found is not None
    assert found.status()["state"] == "running"
    assert [one["name"] for one in found.status()["clients"]] == ["bob@tui"]

    # And comes back to it, read from the top.
    again = panes.opens(_hmz("alice"))
    panes.waits(again, "what is the plan for the parser?")
    panes.waits(again, "planner · outworlder")

    # Bob stops it, for everybody.
    panes.types(bob, "/stop")
    panes.waits(bob, "— stopping the flow —")
    panes.waits(again, "— bob@tui is stopping the flow —")
    for one in (again, bob):
        panes.types(one, "/exit")
    assert _gone(workspace)


@pytest.mark.agent
@pytest.mark.timeout(600)
def test_a_real_agent_is_steered_from_one_interface_while_the_other_watches(
    panes: Panes, workspace: Path
) -> None:
    Hmz(workspace).settings.remember(
        "chat", {"assistant": Runs("claude/claude-haiku-4-5-20251001:low")}
    )
    alice = panes.opens(_hmz("alice"))
    panes.waits(alice, "humanize")
    panes.types(alice, "$chat Count from 1 to 60, one number per line. No tools.")
    panes.waits(alice, "assistant is working", seconds=120)

    bob = panes.opens(_hmz("bob"))
    panes.waits(bob, "Count from 1 to 60")
    panes.types(bob, "STOP. Ignore the counting. Reply with exactly: STEERED")

    # Said by bob, on alice's screen as his, and answered on it by the agent he steered.
    panes.waits(alice, "Reply with exactly: STEERED · by bob@tui", seconds=120)
    deadline = time.monotonic() + 300
    while time.monotonic() < deadline:
        lines = panes.screen(alice).splitlines()
        if any("STEERED" in one and "exactly" not in one for one in lines):
            break
        time.sleep(0.5)
    else:
        raise AssertionError(f"the agent never answered:\n{panes.screen(alice)}")
    for one in (alice, bob):
        panes.types(one, "/stop")
        panes.types(one, "/exit")
    found = daemon.running(workspace)
    if found is not None:
        found.stop()
    assert _gone(workspace)
