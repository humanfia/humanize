"""The pictures of `docs/tutorials/ask-the-person.md`: a flow that asks its person.

The flow is the page's own, `sign_off`, written into the project word for word as the page
has it: an agent does the task, and the person is shown what changed and asked to sign it
off. It is answered in the app and in the terminal, given a face, run under test with a
scripted person, and run from a command line where nobody is there. Run it by naming it:
`uv run pytest tests/system/docs/test_docs_tutorials_ask_the_person.py`.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from playwright.sync_api import expect

from hmz.tui.flows import Flows
from hmz.tui.pick import Configures, Confirms
from tests.integration.doubles_tui import on, onto, shows
from tests.system.docs import shots
from tests.system.docs.conftest import AGENT, MODEL
from tests.system.web.doubles_browser import go

if TYPE_CHECKING:
    from textual.pilot import Pilot

    from tests.system.docs.conftest import World

#: What every picture of the page is named after.
_PAGE = "tutorials-ask-the-person"

_TASK = "Add a discount code to checkout"

#: Step 1 of the page: the flow, as the page prints it.
_FLOW = '''"""Sign-off: an agent does the task, and you approve what it did."""

from typing import Literal

from pydantic import BaseModel, Field

from hmz.flows import (
    Agent,
    AgentCollection,
    Diff,
    EnvCollection,
    FlowContext,
    FlowParams,
    LocalEnv,
    Markdown,
    Outworlder,
    ShellEnvMixin,
    flow,
)


class Review(BaseModel):
    verdict: Literal["approve", "request changes"] = Field(
        description="What to do with the change."
    )
    notes: str = Field("", description="What to change, if anything.")


class Agents(AgentCollection):
    coder: Agent
    reviewer: Outworlder


class Workspace(LocalEnv, ShellEnvMixin): ...


class Envs(EnvCollection):
    workspace: Workspace


@flow(agents=Agents, envs=Envs, params=FlowParams)
async def sign_off(
    task: str, *, agents: Agents, envs: Envs, params: FlowParams, ctx: FlowContext
) -> str:
    """An agent does the task, and you approve what it did."""
    coder, reviewer = agents["coder"], agents["reviewer"]
    workspace = envs["workspace"]
    working = await coder.spawn()
    asking = await reviewer.spawn()
    said = await coder.run(task, session=working, env=workspace)
    while True:
        _, patch, _ = await workspace.exec(["git", "diff"])
        review = await reviewer.run(
            "Sign off this change?",
            session=asking,
            output_schema=Review,
            context=(Markdown(title="What the agent says", text=said), Diff(patch=patch)),
        )
        if review.verdict == "approve":
            return "approved"
        said = await coder.run(review.notes, session=working, env=workspace)
'''

#: Step 4 of the page: the face, beside the flow.
_FACE = """<!doctype html>
<meta charset="utf-8" />
<style>
  body { margin: 0; padding: 12px; font: 14px/1.5 var(--sans); color: var(--ink); }
  pre { font: 12px/1.5 var(--mono); border: 1px solid var(--line); padding: 8px;
        max-height: 220px; overflow: auto; }
  .add { color: var(--done); }
  .del { color: var(--fail); }
  textarea { width: 100%; box-sizing: border-box; }
  #error { color: var(--fail); }
</style>
<pre id="diff"></pre>
<label for="notes">Notes for the agent</label>
<textarea id="notes" rows="2"></textarea>
<p id="error" role="alert"></p>
<button data-verdict="approve">Approve</button>
<button data-verdict="request changes">Request changes</button>
<script>
  hmz.on("ask", ({ context, errors }) => {
    const diff = document.getElementById("diff");
    diff.replaceChildren();
    const patch = context.find((block) => block.kind === "diff")?.patch ?? "";
    for (const line of patch.split("\\n")) {
      const row = document.createElement("div");
      row.textContent = line;
      row.className = line.startsWith("+") ? "add" : line.startsWith("-") ? "del" : "";
      diff.append(row);
    }
    document.getElementById("error").textContent = errors.map((e) => e.message).join("; ");
    hmz.resize(document.body.scrollHeight);
  });
  for (const button of document.querySelectorAll("[data-verdict]")) {
    button.onclick = async () => {
      const notes = document.getElementById("notes").value;
      const said = await hmz.submit({ verdict: button.dataset.verdict, notes });
      if (!said.ok) document.getElementById("error").textContent = said.errors[0].message;
    };
  }
</script>
"""

#: Step 5 of the page: the test, with a scripted person.
_TEST = """import asyncio

from hmz.sdk import fakes


def test_changes_then_approve() -> None:
    you = fakes.FakeOutworlder(
        reply=[
            {"verdict": "request changes", "notes": "add a test"},
            {"verdict": "approve"},
        ]
    )
    coder = fakes.FakeAgentDriver(reply=["done", "added a test"])
    result = asyncio.run(
        fakes.run_fake(
            "sign_off", "add a discount code", agents={"coder": coder}, outworlder=you
        )
    )
    assert result == "approved"
    assert you.asked == ["Sign off this change?", "Sign off this change?"]
    assert coder.prompts == ["add a discount code", "add a test"]
"""

_CHECKOUT = '''"""Paying for a cart."""

from shop.cart import total

CODES = {"WELCOME10": 10}


def charge(items: dict[str, int], code: str = "") -> int:
    """What is charged for a cart, in cents, less what a code takes off."""
    owed = total(items)
    return owed - owed * CODES.get(code, 0) // 100
'''

_TESTED = """from shop.cart import total
from shop.checkout import charge


def test_total() -> None:
    assert total({"mug": 2}) == 2400


def test_a_code_takes_its_discount_off() -> None:
    assert charge({"mug": 1}, "WELCOME10") == 1080
"""

#: What the agent does when told the task, and when sent back to add a test.
_WORK = {
    "discount": {
        "text": (
            "Checkout takes a discount code now: charge() looks the code up and takes"
            " its discount off the total. WELCOME10 is 10% off. An unknown code changes"
            " nothing, and what is charged is still in cents."
        ),
        "writes": {"shop/checkout.py": _CHECKOUT},
    },
    "test": {
        "text": "Added a test for the discount code. 2 passed.",
        "writes": {"tests/test_cart.py": _TESTED},
    },
}


def _faced(source: str) -> str:
    """The flow as steps 4 and 6 of the page leave it: with its face, and not asking nobody."""

    def patched(text: str, was: str, now: str) -> str:
        assert text.count(was) == 1, was
        return text.replace(was, now)

    source = patched(source, "    EnvCollection,\n", "    EnvCollection,\n    Face,\n")
    source = patched(
        source,
        "    asking = await reviewer.spawn()\n",
        '    asking = await reviewer.spawn(face=Face.file("review.html", title="Review"))\n',
    )
    return patched(
        source,
        "    while True:\n",
        '    if reviewer.away:\n        return "left for review"\n    while True:\n',
    )


def _own(world: World, source: str, *, face: bool = False) -> None:
    """Commits the page's flow over the project's `sign_off`, as `@local/sign_off`.

    Committed only to keep the staged tree clean: `git diff` leaves untracked files out, so
    the diff the person is shown is of what the agent changed alone either way.
    """
    files = {".hmz/flows/sign_off/__init__.py": source}
    if face:
        files[".hmz/flows/sign_off/review.html"] = _FACE
    world.committed("Add the sign_off flow", files)


async def _settled(pilot: Pilot[None], seconds: float = 0.4) -> None:
    await pilot.pause(seconds)
    await pilot.pause()


async def _budgeted(pilot: Pilot[None]) -> None:
    """Gives `sign_off` ten minutes on its page of `/flow`, and saves it, as the page says."""
    await pilot.press(*"/flow sign_off", "enter")
    await on(pilot, Flows)
    await shows(pilot, "an epic needs one")
    await onto(pilot, "\x1ebudget")
    await pilot.press("enter")
    await on(pilot, Configures)
    await pilot.press("enter")
    await pilot.pause(0.3)
    await pilot.press(*"10m")
    await pilot.press("enter")
    await pilot.pause(0.3)
    await pilot.press("tab")
    await shows(pilot, "enter Set")
    await pilot.press("enter")
    await on(pilot, Flows)
    await shows(pilot, "stops at 10m")
    await pilot.press("escape")
    await on(pilot, Confirms)
    await pilot.press("enter")
    await shows(pilot, "Flow set up; `/flow sign_off <task>` starts it.")


def test_the_question_is_asked_and_answered_in_the_app(world: World) -> None:
    _own(world, _FLOW)
    world.says(_WORK)
    with world.page(desktop=True) as page:
        # Started as the page says: New epic, the flow, one limit, the task, Send.
        go(page, "/new")
        page.get_by_role("button", name=re.compile("^flow ")).click()
        page.get_by_role("menuitem", name=re.compile("sign_off")).click()
        expect(page.get_by_role("button", name="flow @local/sign_off")).to_be_visible()
        expect(page.get_by_role("textbox", name="Task")).to_have_attribute(
            "placeholder", re.compile("sign_off")
        )
        expect(page.get_by_role("button", name=re.compile("Nous: "))).to_be_visible()
        page.wait_for_timeout(800)
        page.get_by_role("spinbutton", name="Longest it may take, in minutes").fill(
            "10"
        )
        page.get_by_role("textbox", name="Task").fill(_TASK)
        page.get_by_role("button", name="Send").click()
        card = page.locator('[data-hmz="question"]').first
        approve = card.get_by_role("radio", name="approve")
        expect(approve).to_be_visible(timeout=60_000)
        expect(card.get_by_text("in 1 file")).to_be_visible()
        expect(
            page.get_by_role("link", name=re.compile(f"{_TASK} Waiting"))
        ).to_be_visible()
        shots.web(page, f"{_PAGE}-asked", window="desktop", most=shots.REEL)

    with world.page(desktop=True, height=1040) as page:
        page.get_by_text(_TASK).first.click()
        card = page.locator('[data-hmz="question"]').first
        changes = card.get_by_role("radio", name="request changes")
        expect(changes).to_be_visible()
        send = card.locator('[data-hmz="ask-send"]')
        reel = shots.Reel(f"{_PAGE}-answer", clip=card, pad=0)
        reel.web(page, hold=1.6, pointer=changes, click=True)
        changes.click()
        notes = card.get_by_role("textbox").first
        reel.web(page, hold=0.7, pointer=notes, click=True)
        notes.click()
        notes.press_sequentially("add a test")
        reel.web(page, hold=1.0, pointer=send, click=True)
        send.click()
        expect(page.get_by_text("in 2 files")).to_be_visible(timeout=60_000)
        page.wait_for_timeout(600)
        reel.web(page, hold=3.0, poster=True)
        reel.save()
        card = page.locator('[data-hmz="question"]').first
        card.get_by_role("radio", name="approve").click()
        card.locator('[data-hmz="ask-send"]').click()
        expect(
            page.get_by_role("link", name=re.compile(f"{_TASK} Done"))
        ).to_be_visible(timeout=60_000)


def test_the_face_asks_in_the_app(world: World) -> None:
    _own(world, _faced(_FLOW), face=True)
    world.says(_WORK)
    name = world.asks(_TASK)
    with world.page(desktop=True, height=1040) as page:
        go(page, f"/epics/{name}")
        card = page.locator('[data-hmz="question"]').first
        frame = card.frame_locator("iframe")
        expect(frame.get_by_role("button", name="Approve")).to_be_visible()
        expect(frame.get_by_text("WELCOME10").first).to_be_visible()
        page.wait_for_timeout(600)
        shots.web(page, f"{_PAGE}-face", clip=card, pad=0)
    world.stop(name)


async def test_the_question_is_answered_in_the_terminal(world: World) -> None:
    _own(world, _FLOW)
    world.says(_WORK)
    async with world.tui(size=(100, 34)) as (app, pilot):
        await shows(pilot, MODEL)
        await _budgeted(pilot)
        await pilot.press(*f"/flow sign_off {_TASK}", "enter")
        await shows(pilot, "Sign off this change?", "Enter opens it")
        await _settled(pilot, 1.0)
        reel = shots.Reel(f"{_PAGE}-terminal")
        reel.tui(app, hold=2.4)
        await pilot.press("enter")
        await shows(pilot, "1 required left")
        await _settled(pilot)
        reel.tui(app, hold=1.8, keys="enter", caption="opens the form")
        await pilot.press("1")
        await _settled(pilot)
        reel.tui(app, hold=1.4, keys="1", caption="approve")
        await pilot.press("tab")
        await _settled(pilot)
        reel.tui(app, hold=1.0, keys="tab", caption="to Answer")
        await pilot.press("enter")
        await _settled(pilot, 2.0)
        reel.tui(app, hold=3.5, keys="enter", poster=True)
        reel.save()


def test_the_flow_is_tested_with_a_scripted_person(world: World) -> None:
    _own(world, _faced(_FLOW), face=True)
    (world.workspace / "tests" / "test_sign_off.py").write_text(_TEST)
    shots.cli(["pytest", "-q", "tests/test_sign_off.py"], f"{_PAGE}-test", columns=72)


def _exec(name: str) -> None:
    shots.cli(
        [
            "hmz",
            "exec",
            "-f",
            "sign_off",
            "-a",
            f"coder={AGENT}",
            "-p",
            "budget.duration=10m",
            "Add a discount code",
        ],
        name,
        columns=100,
    )


def test_nobody_is_there_from_the_command_line(world: World) -> None:
    _own(world, _FLOW)
    world.says(_WORK)
    _exec(f"{_PAGE}-exec-away")


def test_a_flow_that_checks_first_ends_without_asking(world: World) -> None:
    _own(world, _faced(_FLOW), face=True)
    world.says(_WORK)
    _exec(f"{_PAGE}-exec")
