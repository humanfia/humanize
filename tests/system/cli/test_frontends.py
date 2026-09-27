"""Several frontends on one run, each in a terminal of its own, as people would sit at them.

A tmux server of the test's own, one pane per frontend: a program on the SDK that hosts the
runs and starts one, `hmz attach -c planner` and `hmz attach -c reviewer` for the two people
answering for its two parts, and `hmz attach --json` watching and writing down what it is told.
Answers are typed with `send-keys` and read back off the screen with `capture-pane`, which is
what makes this the system tier: a real terminal multiplexer drawing real processes, rather
than a pipe standing in for one.

The flow asks two people outside it and drives no agent, so nothing here spends a token --
but for the last test, which steers a real Claude from one pane while another watches, and is
asked for with `--run-agents`.
"""

from __future__ import annotations

import contextlib
import json
import os
import shlex
import shutil
import subprocess
import sys
import time
import uuid
from typing import TYPE_CHECKING, Any

import pytest

from hmz import daemon
from tests.stubs import written

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path

pytestmark = pytest.mark.skipif(
    shutil.which("tmux") is None, reason="drives tmux, which is not installed here"
)

#: How long a test waits for a screen to say something.
PATIENCE = 60.0

#: Two people outside the run, asked in turn, and what each said printed and kept.
ASKS = """
import json
from pathlib import Path

from hmz.flows import AgentCollection, EnvCollection, FlowParams, LocalEnv, Outworlder, flow


class Agents(AgentCollection):
    planner: Outworlder
    reviewer: Outworlder


class Envs(EnvCollection):
    workspace: LocalEnv


@flow(agents=Agents, envs=Envs, params=FlowParams, name="asks")
async def asks(task, *, agents, envs, params, ctx):
    here = envs["workspace"]
    planner = await agents["planner"].spawn(env=here)
    reviewer = await agents["reviewer"].spawn(env=here)
    plan = await agents["planner"].run(f"what is the plan for {task}?", session=planner)
    review = await agents["reviewer"].run(f"is {plan!r} good?", session=reviewer)
    print(f"RESULT plan={plan!r} review={review!r}")
    Path("result.json").write_text(json.dumps({"plan": plan, "review": review}))
"""

#: The program on the SDK: hosts the runs, waits for the roles it is told of to be claimed,
#: starts the flow, and says what happens until the run is over -- stopping it once the text
#: it is told of has been answered, where it is told of one.
STARTER = """
import json
import sys

from hmz.sdk import Daemons

flow, task, roles, agents, until = sys.argv[1:6]
wanted = set(filter(None, roles.split(",")))
held = Daemons().here() or Daemons().host()
print("hosting", held.pid, flush=True)
with held.link(name="starter") as link:
    for said in link:
        if said["type"] == "claims" and wanted <= set(said["claims"]):
            break
    print("claimed", flush=True)
    started = link.start(flow, task, agents=json.loads(agents), budget={"cost": 1})
    print("started", started["run"], flush=True)
    for said in link:
        kind = said["type"]
        if kind == "answered":
            print("answered", said["role"], "by", said["by"], said["text"], flush=True)
        elif kind == "printed":
            print("printed", said["text"], flush=True)
        elif kind == "event" and said["kind"] == "result":
            print("result", said["text"], flush=True)
            if until and until in said["text"]:
                link.stop()
        elif kind == "ended":
            print("ended", said["how"], flush=True)
            break
"""


class Panes:
    """A tmux server of this test's own, and the panes on it."""

    def __init__(self, where: Path) -> None:
        self.where = where
        self.server = f"hmz-{uuid.uuid4().hex[:8]}"
        self.panes: list[str] = []
        settings = where / "tmux.conf"
        settings.write_text("set -g remain-on-exit on\nset -g history-limit 50000\n")
        self._settings = str(settings)

    def tmux(self, *argv: str) -> str:
        return subprocess.run(
            ["tmux", "-L", self.server, "-f", self._settings, *argv],
            check=True,
            capture_output=True,
            text=True,
            env=os.environ.copy(),
        ).stdout

    def opens(self, command: str) -> str:
        """One more pane running `command`, in the workspace."""
        if not self.panes:
            said = self.tmux(
                "new-session", "-d", "-s", "frontends", "-x", "240", "-y", "80",
                "-c", str(self.where), "-P", "-F", "#{pane_id}", command,
            )  # fmt: skip
        else:
            said = self.tmux(
                "split-window", "-t", "frontends", "-c", str(self.where),
                "-P", "-F", "#{pane_id}", command,
            )  # fmt: skip
            self.tmux("select-layout", "-t", "frontends", "tiled")
        self.panes.append(said.strip())
        return self.panes[-1]

    def screen(self, pane: str) -> str:
        """What the pane shows, whole lines joined back up, scrollback included."""
        return self.tmux("capture-pane", "-p", "-J", "-S", "-50000", "-t", pane)

    def waits(self, pane: str, text: str, seconds: float = PATIENCE) -> str:
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            shown = self.screen(pane)
            if text in shown:
                return shown
            time.sleep(0.2)
        raise AssertionError(f"{pane} never showed {text!r}:\n{self.screen(pane)}")

    def types(self, pane: str, line: str) -> None:
        self.tmux("send-keys", "-t", pane, "-l", line)
        self.tmux("send-keys", "-t", pane, "Enter")

    def presses(self, pane: str, key: str) -> None:
        self.tmux("send-keys", "-t", pane, key)

    def close(self) -> None:
        with contextlib.suppress(subprocess.CalledProcessError):
            self.tmux("kill-server")


@pytest.fixture
def workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    where = tmp_path / "project"
    where.mkdir()
    written(where, "asks", ASKS)
    (where / "starter.py").write_text(STARTER)
    monkeypatch.chdir(where)
    # Every pane reads as a pipe would, whatever the terminal running the suite asks for.
    monkeypatch.delenv("FORCE_COLOR", raising=False)
    monkeypatch.setenv("NO_COLOR", "1")
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


def _python(*argv: str) -> str:
    return shlex.join([sys.executable, *argv])


def _attach(name: str, *argv: str) -> str:
    return f"HUMANIZE_NAME={name} {_python('-m', 'hmz', 'attach', *argv)}"


def _starter(
    flow: str, task: str, roles: str, agents: str = "{}", until: str = ""
) -> str:
    return _python("starter.py", flow, task, roles, agents, until)


def _records(path: Path) -> list[dict[str, Any]]:
    said = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    return [one for one in said if "seq" in one and one["type"] != "live"]


def _lands(path: Path, kind: str) -> None:
    """Waits for a frontend writing to `path` to have been told a message of `kind`."""
    deadline = time.monotonic() + PATIENCE
    while time.monotonic() < deadline:
        said = path.read_text() if path.exists() else ""
        if f'"type": "{kind}"' in said:
            return
        time.sleep(0.2)
    raise AssertionError(f"{path.name} was never told {kind}")


def _hosted(where: Path) -> daemon.Daemon:
    deadline = time.monotonic() + PATIENCE
    while time.monotonic() < deadline:
        if (found := daemon.running(where)) is not None:
            return found
        time.sleep(0.1)
    raise AssertionError("the starter never hosted the runs")


@pytest.mark.timeout(240)
def test_two_people_each_answer_for_their_own_part_while_a_third_watches(
    panes: Panes, workspace: Path
) -> None:
    starter = panes.opens(_starter("asks", "the parser", "planner,reviewer"))
    _hosted(workspace)
    panes.opens(_attach("watcher", "--json") + " > watcher.jsonl")
    alice = panes.opens(_attach("alice", "-c", "planner"))
    bob = panes.opens(_attach("bob", "-c", "reviewer"))
    panes.waits(starter, "started 1")

    # The planner's question is alice's to answer, and bob is told so rather than asked.
    panes.waits(alice, "planner: what is the plan for the parser? · yours to answer")
    shown = panes.waits(bob, "planner: what is the plan for the parser?")
    assert "planner: what is the plan for the parser? · alice@cli's to answer" in shown
    panes.types(alice, "a plan from alice")
    panes.waits(bob, "reviewer: is 'a plan from alice' good? · yours to answer")
    # Somebody arriving halfway through, who reads what happened before and then the rest.
    panes.opens(_attach("late", "--json") + " > late.jsonl")
    _lands(workspace / "late.jsonl", "live")
    panes.types(bob, "fine by bob")

    panes.waits(starter, "ended done")
    for one in (alice, bob):
        panes.waits(one, "— the flow is done —")
    said = panes.screen(starter)
    assert "answered planner by alice@cli a plan from alice" in said
    assert "answered reviewer by bob@cli fine by bob" in said
    assert "printed RESULT plan='a plan from alice' review='fine by bob'" in said
    assert json.loads((workspace / "result.json").read_text()) == {
        "plan": "a plan from alice",
        "review": "fine by bob",
    }
    # Both transcripts, each with the other's answer in it, said by whoever gave it.
    assert "❯ fine by bob · bob@cli for reviewer" in panes.screen(alice)
    assert "❯ a plan from alice · alice@cli for planner" in panes.screen(bob)

    # The watcher claimed nothing, and was told every question and who answered it.
    _lands(workspace / "watcher.jsonl", "ended")
    records = _records(workspace / "watcher.jsonl")
    assert [
        (one["role"], one["by"]) for one in records if one["type"] == "answered"
    ] == [
        ("planner", "alice@cli"),
        ("reviewer", "bob@cli"),
    ]
    assert [one["role"] for one in records if one["type"] == "asked"] == [
        "planner",
        "reviewer",
    ]
    # And the one who arrived late read the run exactly as the watcher saw it happen.
    _lands(workspace / "late.jsonl", "ended")
    assert _records(workspace / "late.jsonl") == records


@pytest.mark.timeout(240)
def test_a_question_left_by_the_person_who_held_it_is_answered_by_another(
    panes: Panes, workspace: Path
) -> None:
    starter = panes.opens(_starter("asks", "the parser", "planner,reviewer"))
    _hosted(workspace)
    alice = panes.opens(_attach("alice", "-c", "planner"))
    bob = panes.opens(_attach("bob", "-c", "reviewer"))
    panes.waits(alice, "planner: what is the plan for the parser? · yours to answer")

    panes.presses(alice, "C-c")
    panes.waits(alice, "hmz attach: let go")
    panes.types(bob, "/claim planner")
    panes.waits(bob, "hmz attach: planner is yours to answer")
    panes.types(bob, "bob's plan")
    panes.waits(bob, 'reviewer: is "bob\'s plan" good? · yours to answer')
    panes.types(bob, "and fine by bob")

    said = panes.waits(starter, "ended done")
    assert "answered planner by bob@cli bob's plan" in said
    assert "answered reviewer by bob@cli and fine by bob" in said


@pytest.mark.agent
@pytest.mark.timeout(600)
def test_a_real_agent_is_steered_from_one_terminal_while_another_watches(
    panes: Panes, workspace: Path
) -> None:
    starter = panes.opens(
        _starter(
            "chat",
            "Count from 1 to 60, one number per line. No tools.",
            "human",
            json.dumps({"assistant": "claude/claude-haiku-4-5-20251001:low"}),
            "STEERED",
        )
    )
    _hosted(workspace)
    watcher = panes.opens(_attach("watcher"))
    bob = panes.opens(_attach("bob", "-c", "human"))
    panes.waits(starter, "started 1")
    panes.waits(bob, "assistant is working", seconds=120)

    panes.types(bob, "STOP. Ignore the counting. Reply with exactly: STEERED")

    panes.waits(starter, "ended stopped", seconds=300)
    watched = panes.waits(watcher, "STEERED")
    assert "STOP. Ignore the counting" in watched
    assert "bob@cli" in watched
