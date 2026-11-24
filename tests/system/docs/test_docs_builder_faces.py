"""The pictures of `docs/builder/faces.md`: a flow that asks its person in a page of its own.

The flow is the page's own, `gate`, written into the project word for word as the page has
it, beside its face `review.html`: an agent does the task, and the person reviews the change
file by file in the face. It is shown in the app, switched to the plain form and back, given
a face that never listens, asked in the terminal, and run under test with a scripted person.
Run it by naming it: `uv run pytest tests/system/docs/test_docs_builder_faces.py`.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from playwright.sync_api import expect

from hmz.tui.flows import Flows
from hmz.tui.pick import Configures, Confirms
from tests.integration.doubles_tui import on, onto, shows
from tests.system.docs import shots
from tests.system.docs.conftest import MODEL
from tests.system.web.doubles_browser import go

if TYPE_CHECKING:
    from textual.pilot import Pilot

    from tests.system.docs.conftest import World

#: What every picture of the page is named after.
_PAGE = "builder-faces"

_TASK = "Add a discount code to checkout"

#: The flow, as the page prints it.
_FLOW = '''"""Gate: an agent does the task, and you review the change in a face."""

from typing import Literal

from pydantic import BaseModel, Field

from hmz.flows import (
    Agent,
    AgentCollection,
    Diff,
    EnvCollection,
    Face,
    FlowContext,
    FlowParams,
    LocalEnv,
    Outworlder,
    ShellEnvMixin,
    flow,
)

REVIEW = Face.file("review.html", title="Review")


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
async def gate(
    task: str, *, agents: Agents, envs: Envs, params: FlowParams, ctx: FlowContext
) -> str:
    """An agent does the task, and you review the change in a face."""
    coder, reviewer = agents["coder"], agents["reviewer"]
    workspace = envs["workspace"]
    working = await coder.spawn()
    reviewing = await reviewer.spawn(face=REVIEW)
    notes = task
    for _ in range(3):
        await coder.run(notes, session=working, env=workspace)
        _, patch, _ = await workspace.exec(["git", "diff"])
        review = await reviewer.run(
            "Ship this change?",
            session=reviewing,
            output_schema=Review,
            context=[Diff(patch=patch)],
        )
        if review.verdict == "approve":
            return "approved"
        notes = review.notes
    return "not approved"
'''

#: The face, as the page prints it, beside the flow.
_FACE = r"""<!doctype html>
<meta charset="utf-8" />
<style>
  body { margin: 0; padding: 12px; font: 14px/1.5 var(--sans); color: var(--ink); }
  details { border: 1px solid var(--line); margin-bottom: 8px; }
  summary { padding: 4px 8px; font-family: var(--mono); }
  pre { margin: 0; padding: 4px 8px; font: 12px/1.5 var(--mono); overflow-x: auto; }
  .add { color: var(--done); }
  .del { color: var(--fail); }
  textarea { width: 100%; box-sizing: border-box; }
  #error { color: var(--fail); }
</style>
<div id="files"></div>
<label for="notes">Notes for the coder</label>
<textarea id="notes" rows="2"></textarea>
<p id="error" role="alert"></p>
<button data-verdict="approve">Approve</button>
<button data-verdict="request changes">Request changes</button>
<script>
  const $ = (id) => document.getElementById(id);
  hmz.on("ask", ({ context, errors }) => {
    const patch = context.find((block) => block.kind === "diff")?.patch ?? "";
    $("files").replaceChildren();
    for (const part of patch.split(/^(?=diff --git )/m).filter(Boolean)) {
      const file = $("files").appendChild(document.createElement("details"));
      const name = file.appendChild(document.createElement("summary"));
      const lines = file.appendChild(document.createElement("pre"));
      const body = part.slice(part.indexOf("\n@@") + 1).split("\n");
      const count = (sign) => body.filter((line) => line.startsWith(sign)).length;
      const path = part.match(/^diff --git a\/(\S+)/)?.[1] ?? "the change";
      name.textContent = `${path}  +${count("+")} -${count("-")}`;
      for (const line of body) {
        const row = lines.appendChild(document.createElement("div"));
        row.textContent = line;
        row.className = line.startsWith("+") ? "add" : line.startsWith("-") ? "del" : "";
      }
      file.open = file === $("files").firstChild;
    }
    $("notes").value = "";
    $("error").textContent = errors.map((error) => error.message).join("; ");
  });
  for (const button of document.querySelectorAll("[data-verdict]")) {
    button.onclick = async () => {
      const value = { verdict: button.dataset.verdict, notes: $("notes").value };
      const said = await hmz.submit(value);
      if (!said.ok) $("error").textContent = said.errors[0].message;
    };
  }
</script>
"""

#: A face that never calls `hmz.on("ask", ...)`: the page gives up on it and asks the form.
_DEAF = """<!doctype html>
<meta charset="utf-8" />
<p>Review</p>
"""

#: The test, as the page prints it.
_TEST = """import asyncio

from hmz.flows import Face
from hmz.sdk import fakes


def test_asked_in_the_face_and_sent_back_once() -> None:
    you = fakes.FakeOutworlder(
        reply=[
            {"verdict": "request changes", "notes": "add a test"},
            {"verdict": "approve"},
        ]
    )
    coder = fakes.FakeAgentDriver(reply=["done", "added a test"])
    result = asyncio.run(
        fakes.run_fake(
            "gate", "add a discount code", agents={"coder": coder}, outworlder=you
        )
    )
    assert result == "approved"
    assert coder.prompts == ["add a discount code", "add a test"]
    face = Face.file("../.hmz/flows/gate/review.html")
    assert [ask.face for ask in you.asks] == [face.hash, face.hash]
    assert you.asks[0].context[0]["kind"] == "diff"
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

#: What the agent does when told the task.
_WORK = {
    "discount": {
        "text": (
            "Checkout takes a discount code now: charge() looks the code up and takes"
            " its discount off the total. WELCOME10 is 10% off, and there is a test."
        ),
        "writes": {"shop/checkout.py": _CHECKOUT, "tests/test_cart.py": _TESTED},
    },
}

#: The same with one file changed, where the question and its diff are to fit one screen.
_SMALL = {"discount": {**_WORK["discount"], "writes": {"shop/checkout.py": _CHECKOUT}}}


def _own(world: World, face: str = _FACE) -> None:
    """Commits the page's flow and its face to the project, as `@local/gate`.

    Committed, so that the diff the person is shown is of what the agent changed alone.
    """
    world.committed(
        "Add the gate flow",
        {
            ".hmz/flows/gate/__init__.py": _FLOW,
            ".hmz/flows/gate/review.html": face,
        },
    )


async def _settled(pilot: Pilot[None], seconds: float = 0.4) -> None:
    await pilot.pause(seconds)
    await pilot.pause()


async def _budgeted(pilot: Pilot[None]) -> None:
    """Gives `gate` ten minutes on its page of `/flow`, and saves it."""
    await pilot.press(*"/flow gate", "enter")
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
    await shows(pilot, "set up: /flow gate <task> starts it")


def test_the_face_asks_in_the_app(world: World) -> None:
    _own(world)
    world.says(_WORK)
    name = world.epic("@local/gate", _TASK, until="asked")
    with world.page(desktop=True, height=1060) as page:
        go(page, f"/epics/{name}")
        card = page.locator('[data-hmz="question"]').first
        frame = card.frame_locator("iframe")
        expect(frame.get_by_role("button", name="Approve")).to_be_visible()
        expect(frame.get_by_text("WELCOME10").first).to_be_visible()
        expect(frame.get_by_text("tests/test_cart.py")).to_be_visible()
        page.wait_for_timeout(800)
        shots.web(page, f"{_PAGE}-app", window="desktop", most=shots.REEL)
    world.stop(name)


def test_the_person_switches_to_the_plain_form_and_back(world: World) -> None:
    _own(world)
    world.says(_SMALL)
    name = world.epic("@local/gate", _TASK, until="asked")
    # As tall as the card is at its tallest, the plain form under the whole diff: the card
    # grows upward from the message box, so the column it stands in is what holds still.
    with world.page(desktop=True, height=1340) as page:
        go(page, f"/epics/{name}")
        card = page.locator('[data-hmz="question"]').first
        frame = card.frame_locator("iframe")
        expect(frame.get_by_role("button", name="Approve")).to_be_visible()
        # The list of sessions in place of the graph, which is what a reel of it weighs.
        page.get_by_role("button", name="List", exact=True).click()
        page.wait_for_timeout(800)
        switch = card.get_by_role("button", name="Plain form")
        reel = shots.Reel(f"{_PAGE}-switch", clip=page.locator(".work"), pad=0)
        reel.web(page, hold=2.4, pointer=switch, click=True, poster=True)
        switch.click()
        expect(card.get_by_role("radio", name="approve")).to_be_visible()
        back = card.get_by_role("button", name="Back to Review")
        expect(back).to_be_visible()
        page.wait_for_timeout(600)
        reel.web(page, hold=3.0, pointer=back, click=True)
        back.click()
        expect(frame.get_by_role("button", name="Approve")).to_be_visible()
        page.wait_for_timeout(600)
        reel.web(page, hold=1.8)
        reel.save()
    world.stop(name)


def test_a_face_that_never_listens_gives_way_to_the_form(world: World) -> None:
    _own(world, _DEAF)
    world.says(_SMALL)
    name = world.epic("@local/gate", _TASK, until="asked")
    with world.page(desktop=True, height=1300) as page:
        go(page, f"/epics/{name}")
        card = page.locator('[data-hmz="question"]').first
        expect(card.get_by_text("took too long to open")).to_be_visible(timeout=30_000)
        expect(card.get_by_role("button", name="Try again")).to_be_visible()
        expect(card.get_by_role("radio", name="approve")).to_be_visible()
        page.wait_for_timeout(500)
        shots.web(page, f"{_PAGE}-fallback", clip=card, pad=0)
    world.stop(name)


async def test_the_terminal_asks_the_form(world: World) -> None:
    _own(world)
    world.says(_SMALL)
    async with world.tui(size=(100, 40)) as (app, pilot):
        await shows(pilot, MODEL)
        await _budgeted(pilot)
        await pilot.press(*f"/flow gate {_TASK}", "enter")
        await shows(pilot, "Ship this change?", "The custom view is in the web page")
        await _settled(pilot, 1.0)
        shots.tui(app, f"{_PAGE}-terminal")


def test_the_flow_is_tested_with_a_scripted_person(world: World) -> None:
    _own(world)
    (world.workspace / "tests" / "test_gate.py").write_text(_TEST)
    shots.cli(["pytest", "-q", "tests/test_gate.py"], f"{_PAGE}-test", columns=72)
