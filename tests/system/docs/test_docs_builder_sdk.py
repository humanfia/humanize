"""The pictures of `docs/builder/sdk.md`: programs that reach Humanize through `hmz.sdk`.

Run it by naming it: `uv run pytest tests/system/docs/test_docs_builder_sdk.py`.

Every script here is the page's own, character for character: what the page prints is what
ran here, and the ones no picture is taken of are run all the same, so that the page's code
is known to work.
"""

from __future__ import annotations

import subprocess
import sys
import time
from typing import TYPE_CHECKING

from playwright.sync_api import expect

from tests.system.docs import shots
from tests.system.web.doubles_browser import go

if TYPE_CHECKING:
    from tests.system.docs.conftest import World

_TASK = "Add a coupon code to checkout"

#: "Run a flow": the shortest program that runs one, and the same as one `hmz exec` line.
_SHORT = """
from hmz.sdk import Hmz

hmz = Hmz()
result = hmz.run(
    "goal",
    "Add a coupon code to checkout",
    agents={"worker": "claude/claude-haiku-4-5"},
    budget={"output_tokens": 20000},
).run()
"""

_EXEC = """
hmz.exec(
    ["-f", "goal", "-a", "worker=claude/claude-haiku-4-5",
     "-p", "budget.output_tokens=20000", "Add a coupon code to checkout"]
)
"""

#: "Follow and control a run": one epic started, followed and read, `run.py`.
_RUN = """
from hmz.sdk import Hmz

hmz = Hmz()
run = hmz.run(
    "goal",
    "Add a coupon code to checkout",
    agents={"worker": "claude/claude-haiku-4-5"},
    budget={"output_tokens": 20000},
)
run.opened(lambda role, session: print(f"[{role}] {session.cli} {session.model}"))
run.watch(lambda agent, key, event: print(f"  {event['kind']}: {event['text'][:60]}"))
run.start()
run.wait()
print("raised:", run.raised)
print("spent:", run.usage.output_tokens, "output tokens")
print("epic:", run.epic.name)
"""

#: "Answer the person's questions": a driver for a flow's `Outworlder` role, `answer.py`.
_ANSWER = """
from hmz.sdk import Ask, Hmz


class Reviewer:
    def away_for(self, role: str) -> bool:
        return False

    async def run(self, ask: Ask, role: str):
        print(f"[{role}] {ask.prompt}")
        if ask.schema is None:
            return "yes"
        return {"verdict": "approve"}


run = Hmz().run(
    "@local/sign_off",
    "Add a coupon code to checkout",
    agents={"coder": "claude/claude-haiku-4-5"},
    budget={"output_tokens": 20000},
    outworlder=Reviewer(),
)
run.run()
"""

#: "Look up flows, accounts and nous": the catalog and the two stores, `setup.py`.
_SETUP = """
from hmz.sdk import Hmz

hmz = Hmz()
for offer in hmz.flows.all():
    print(f"{offer.name:16} {offer.about}")
print([role.name for role in hmz.flows.declared("goal").agents])

key = hmz.accounts.way("claude", "key")
hmz.accounts.make("claude", "work", key, {"ANTHROPIC_API_KEY": "not-a-real-key"})
hmz.nous.write(
    "careful", graph=["claude/claude-opus-4-1", "claude/claude-haiku-4-5"], tries=2
)
print([one.name for one in hmz.accounts.all("claude")])
print([one.name for one in hmz.nous.all()])
"""

#: "Read epics back": every epic of the project, and the last one's sessions, `read.py`.
_READ = """
from hmz.sdk import Hmz

epics = Hmz().epics
for path in epics.all():
    ran = epics.read(path)
    print(ran.began[:19], ran.flow, epics.ending(ran), ran.task)

last = epics.all()[-1]
for session in epics.transcripts(last):
    for action in session["actions"]:
        print(" ", action["category"], action["name"][:56])
where, trace = epics.traced(last)
print("trace:", where.name, trace["otherData"]["slices"], "slices")
archive, manifest = epics.bundled(last, output=".")
print("archive:", archive.name)
"""

#: "Talk to the daemon yourself": one session, then one link, `daemon.py`.
_DAEMON = """
from pathlib import Path

from hmz.sdk import Client, Daemons

with Client.local(name="ci") as client:
    print("protocol", client.protocol, "as", client.device)
    listed = client.call("runs.list", {"workspace": str(Path.cwd())})
    for one in listed["runs"]:
        print(one["name"], one["flow"], one["how"])

with Daemons().host().link(name="ci", replay=False) as link:
    link.start(
        "goal",
        "Add a coupon code to checkout",
        agents={"worker": "claude/claude-haiku-4-5"},
        budget={"output_tokens": 20000},
    )
    for said in link:
        if said["type"] == "event":
            print(said["kind"], said["text"][:50])
        if said["type"] == "ended":
            print("ended:", said["how"])
            break
"""

#: "Run on objects of your own": a scripted agent, held by a private daemon, `fake.py`.
_FAKE = """
from hmz.sdk import Hmz, fakes

worker = fakes.FakeAgentDriver(reply="Added WELCOME10.")
run = Hmz().run(
    "tidy", "Add a coupon code to checkout", agents={"worker": worker}, budget={"cost": 1}
)
print(run.run())
print(worker.sessions[0].prompts)
"""

#: The project's own flow `fake.py` runs, `.hmz/flows/tidy.py`: one worker, one turn.
_TIDY = """
from hmz.flows import (
    Agent,
    AgentCollection,
    EnvCollection,
    FlowContext,
    FlowParams,
    LocalEnv,
    flow,
)


class Agents(AgentCollection):
    worker: Agent


class Envs(EnvCollection):
    workspace: LocalEnv


@flow(agents=Agents, envs=Envs, params=FlowParams)
async def tidy(
    task: str, *, agents: Agents, envs: Envs, params: FlowParams, ctx: FlowContext
) -> str:
    \"\"\"One worker does the task and says what it did.\"\"\"
    worker = agents["worker"]
    return await worker.run(task, session=await worker.spawn(), env=envs["workspace"])
"""

#: What the worker does when told the task.
_WORK = {
    "text": "Checkout takes a coupon now: WELCOME10 is 10% off. The tests pass.",
    "tools": [
        {
            "name": "Edit",
            "input": {"file_path": "shop/checkout.py"},
            "result": "edited",
            "takes": 0.5,
        },
        {
            "name": "Bash",
            "input": {"command": "pytest -q"},
            "result": "5 passed in 0.18s",
            "takes": 0.7,
        },
    ],
    "after": 0.4,
}


def _ran(world: World, name: str, script: str) -> str:
    """Runs one of the page's scripts in the project, and answers what it printed."""
    (world.workspace / name).write_text(script)
    done = subprocess.run(
        [sys.executable, name],
        cwd=world.workspace,
        capture_output=True,
        text=True,
        timeout=300,
        check=False,
    )
    assert done.returncode == 0, done.stdout + done.stderr
    return done.stdout


def _over(world: World, name: str) -> None:
    """Waits until an epic has ended, as its own record says it.

    `World.epic` started on a workspace that has run an epic before is replayed that epic's
    end, and answers while the new one is still going: this asks the daemon instead.
    """
    until = time.monotonic() + 60
    while not world.call("runs.get", name=name)["ended"]:
        assert time.monotonic() < until, f"{name} never ended"
        time.sleep(0.2)


def test_a_script_runs_a_flow_follows_it_and_the_app_shows_the_epic(
    world: World,
) -> None:
    world.says({"coupon": _WORK})
    (world.workspace / "run.py").write_text(_RUN)
    shots.cli(["python", "run.py"], "builder-sdk-run")
    with world.page(desktop=True) as page:
        name = world.call("runs.list", workspace=str(world.workspace))["runs"][0][
            "name"
        ]
        go(page, f"/epics/{name}")
        expect(page.get_by_text("output tokens", exact=True)).to_be_visible()
        expect(page.get_by_text("1 turn", exact=True)).to_be_visible()
        shots.web(page, "builder-sdk-app", window="desktop", most=shots.REEL)


def test_a_script_reads_epics_back(world: World) -> None:
    world.says({"coupon": _WORK, "receipt": "Receipts are emailed after payment now."})
    world.epic("rlar", "Email a receipt after payment")
    _over(world, world.epic("goal", _TASK))
    (world.workspace / "read.py").write_text(_READ)
    shots.cli(["python", "read.py"], "builder-sdk-read")


def test_a_script_talks_to_the_daemon_itself(world: World) -> None:
    world.says({"coupon": _WORK, "receipt": "Receipts are emailed after payment now."})
    world.epic("rlar", "Email a receipt after payment")
    (world.workspace / "daemon.py").write_text(_DAEMON)
    shots.cli(["python", "daemon.py"], "builder-sdk-daemon")


def test_the_scripts_no_picture_is_taken_of_work(world: World) -> None:
    world.says({"coupon": _WORK})
    _ran(world, "short.py", _SHORT + _EXEC)
    assert len(world.call("runs.list", workspace=str(world.workspace))["runs"]) == 2
    said = _ran(world, "answer.py", _ANSWER)
    assert "[reviewer] Sign off this change?" in said, said
    said = _ran(world, "setup.py", _SETUP)
    for printed in ("['worker']", "['work']", "['careful']"):
        assert printed in said, said
    (world.workspace / ".hmz" / "flows" / "tidy.py").write_text(_TIDY)
    said = _ran(world, "fake.py", _FAKE)
    assert said == "Added WELCOME10.\n['Add a coupon code to checkout']\n", said
