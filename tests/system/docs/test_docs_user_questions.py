"""The pictures of `docs/user/questions.md`: answering what a flow asks its person.

The flow is the scene's own, `ship_it`, written into the project: an agent does the task,
and the person is shown what it said, what it changed and what was checked, and asked
whether to ship it -- one form -- and then, in words, what the changelog is to call it. It
is answered in the app and in the terminal, given a face, held and left on the People tab
and with `/claim` and `/afk`, and run from a command line where nobody is there. Run it by
naming it: `uv run pytest tests/system/docs/test_docs_user_questions.py`.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from playwright.sync_api import expect

from tests.integration.doubles_tui import shows
from tests.system.docs import shots
from tests.system.docs.conftest import AGENT
from tests.system.web.doubles_browser import go

if TYPE_CHECKING:
    from textual.pilot import Pilot

    from tests.system.docs.conftest import World

#: What every picture of the page is named after.
_PAGE = "user-questions"

_TASK = "Add a discount code to checkout"

_FLOW = '''"""Ship it: an agent does the task, and you decide whether it ships."""

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
    OutworlderAway,
    ShellEnvMixin,
    Table,
    flow,
)


class Release(BaseModel):
    verdict: Literal["ship", "hold"] = Field(description="What to do with the change.")
    announce: bool = Field(True, description="Post it to the changelog.")


class Agents(AgentCollection):
    coder: Agent
    reviewer: Outworlder


class Workspace(LocalEnv, ShellEnvMixin): ...


class Envs(EnvCollection):
    workspace: Workspace


@flow(agents=Agents, envs=Envs, params=FlowParams)
async def ship_it(
    task: str, *, agents: Agents, envs: Envs, params: FlowParams, ctx: FlowContext
) -> str:
    """An agent does the task, and you decide whether it ships."""
    coder, reviewer = agents["coder"], agents["reviewer"]
    workspace = envs["workspace"]
    working = await coder.spawn()
    asking = await reviewer.spawn()
    said = await coder.run(task, session=working, env=workspace)
    _, patch, _ = await workspace.exec(["git", "diff"])
    checks = Table(
        title="Checks",
        columns=("check", "result"),
        rows=(("pytest", "2 passed"), ("ruff", "clean"), ("pyright", "0 errors")),
    )
    try:
        release = await reviewer.run(
            "Ship this change?",
            session=asking,
            output_schema=Release,
            context=(Markdown(title="What the agent says", text=said), Diff(patch=patch), checks),
        )
    except OutworlderAway:
        return "nobody was there: left for review"
    if release.verdict == "hold":
        return "held"
    title = await reviewer.run("What should the changelog call it?", session=asking)
    return f"shipped: {title or task}"
'''

#: The same flow with a page of its own to ask in.
_FACED = _FLOW.replace(
    "    EnvCollection,\n", "    EnvCollection,\n    Face,\n"
).replace(
    "    asking = await reviewer.spawn()\n",
    '    asking = await reviewer.spawn(face=Face.file("release.html", title="Release"))\n',
)

_FACE = """<!doctype html>
<meta charset="utf-8" />
<style>
  body { margin: 0; padding: 12px; font: 14px/1.5 var(--sans); color: var(--ink); }
  pre { font: 12px/1.5 var(--mono); border: 1px solid var(--line); padding: 8px;
        max-height: 200px; overflow: auto; }
  .add { color: var(--done); }
  .del { color: var(--fail); }
  #error { color: var(--fail); }
</style>
<pre id="diff"></pre>
<p id="error" role="alert"></p>
<button data-verdict="ship">Ship it</button>
<button data-verdict="hold">Hold it</button>
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
      const said = await hmz.submit({ verdict: button.dataset.verdict });
      if (!said.ok) document.getElementById("error").textContent = said.errors[0].message;
    };
  }
</script>
"""

_CHECKOUT = '''"""Paying for a cart."""

from shop.cart import total

CODES = {"WELCOME10": 10}


def charge(items: dict[str, int], code: str = "") -> int:
    """What is charged for a cart, in cents, less what a code takes off."""
    owed = total(items)
    return owed - owed * CODES.get(code, 0) // 100
'''

#: What the agent does when told the task.
_WORK = {
    "discount": {
        "text": (
            "Checkout takes a discount code now: charge() looks the code up and takes"
            " its discount off the total. WELCOME10 is 10% off."
        ),
        "writes": {"shop/checkout.py": _CHECKOUT},
    },
}


def _own(world: World, *, face: bool = False) -> None:
    """Commits the scene's flow into the project, as `@local/ship_it`."""
    files = {".hmz/flows/ship_it/__init__.py": _FACED if face else _FLOW}
    if face:
        files[".hmz/flows/ship_it/release.html"] = _FACE
    world.committed("Add the ship_it flow", files)
    world.says(_WORK)


def _asked(world: World, *, face: bool = False) -> str:
    """Leaves an epic of `ship_it` waiting at its form, and answers its name."""
    _own(world, face=face)
    return world.epic("@local/ship_it", _TASK, until="asked")


async def _settled(pilot: Pilot[None], seconds: float = 0.4) -> None:
    await pilot.pause(seconds)
    await pilot.pause()


# -- in the app -----------------------------------------------------------------------


def test_a_question_waits_in_the_app(world: World) -> None:
    name = _asked(world)
    with world.page(desktop=True, height=1040) as page:
        go(page, f"/epics/{name}")
        card = page.locator('[data-hmz="question"]').first
        expect(card.get_by_role("radio", name="ship")).to_be_visible(timeout=60_000)
        expect(card.get_by_text("in 1 file")).to_be_visible()
        page.wait_for_timeout(800)
        shots.web(page, f"{_PAGE}-asked", window="desktop", most=shots.REEL)
        shots.web(page, f"{_PAGE}-card", clip=card, pad=0)
    world.stop(name)


def test_a_form_and_a_line_are_answered_in_the_app(world: World) -> None:
    name = _asked(world)
    with world.page(desktop=True, height=1040) as page:
        go(page, f"/epics/{name}")
        card = page.locator('[data-hmz="question"]').first
        ship = card.get_by_role("radio", name="ship")
        expect(ship).to_be_visible(timeout=60_000)
        # The panel beside the epic is put away: the reel is of the questions alone.
        page.get_by_role("button", name="Toggle panel").click()
        expect(page.get_by_role("tab", name="People")).to_have_count(0)
        # And the epic is read as a list: its graph is a picture's weight by itself.
        page.get_by_role("button", name="List", exact=True).click()
        page.wait_for_timeout(2600)
        send = card.locator('[data-hmz="ask-send"]')
        reel = shots.Reel(f"{_PAGE}-answer", clip=page.get_by_role("main"), pad=0)
        reel.web(page, hold=1.8, pointer=ship, click=True)
        ship.click()
        expect(send).to_have_text("Send answer")
        reel.web(page, hold=1.2, pointer=send, click=True)
        send.click()
        line = page.get_by_role("textbox", name="Answer")
        expect(line).to_be_visible(timeout=60_000)
        expect(page.get_by_text("You answered")).to_be_visible()
        page.wait_for_timeout(2600)
        reel.web(page, hold=1.8, pointer=line, click=True)
        line.click()
        line.press_sequentially("Discount codes at checkout")
        answer = page.get_by_role("button", name="Answer", exact=True)
        reel.web(page, hold=1.2, pointer=answer, click=True)
        answer.click()
        expect(page.get_by_text("You answered")).to_have_count(2, timeout=60_000)
        page.wait_for_timeout(800)
        reel.web(page, hold=3.5, poster=True)
        reel.save()


def test_a_face_asks_in_the_app(world: World) -> None:
    name = _asked(world, face=True)
    with world.page(desktop=True, height=1040) as page:
        go(page, f"/epics/{name}")
        card = page.locator('[data-hmz="question"]').first
        frame = card.frame_locator("iframe")
        expect(frame.get_by_role("button", name="Ship it")).to_be_visible(
            timeout=60_000
        )
        expect(frame.get_by_text("WELCOME10").first).to_be_visible()
        expect(card.get_by_role("button", name="Plain form")).to_be_visible()
        page.wait_for_timeout(800)
        shots.web(page, f"{_PAGE}-face", clip=card, pad=0)
    world.stop(name)


def test_a_role_is_claimed_and_left_in_the_app(world: World) -> None:
    name = _asked(world)
    with world.page(desktop=True, height=330) as page:
        go(page, f"/epics/{name}")
        page.get_by_role("tab", name="People").click()
        claim = page.get_by_role("button", name="Claim")
        expect(claim).to_be_visible(timeout=60_000)
        claim.click()
        expect(page.get_by_role("button", name="Release")).to_be_visible()
        page.wait_for_timeout(800)
        shots.web(
            page,
            f"{_PAGE}-people",
            clip=page.get_by_role("complementary", name="the epic"),
            pad=0,
        )
    with world.page(desktop=True, height=1040) as page:
        go(page, f"/epics/{name}")
        page.get_by_role("tab", name="People").click()
        away = page.get_by_role("button", name="Away for all")
        expect(away).to_be_visible(timeout=60_000)
        away.click()
        page.get_by_role("button", name="List", exact=True).click()
        gone = page.get_by_role("region", name="Answered")
        expect(gone.get_by_text("Withdrawn")).to_be_visible(timeout=60_000)
        page.wait_for_timeout(800)
        shots.web(page, f"{_PAGE}-away", clip=gone, pad=12)


# -- in the terminal ------------------------------------------------------------------


async def test_a_question_is_answered_in_the_terminal(world: World) -> None:
    _asked(world)
    async with world.tui(size=(100, 43)) as (app, pilot):
        await shows(pilot, "Enter opens it")
        await _settled(pilot, 1.0)
        shots.tui(app, f"{_PAGE}-terminal")
        reel = shots.Reel(f"{_PAGE}-terminal-form")
        reel.tui(app, hold=2.0)
        await pilot.press("enter")
        await shows(pilot, "1 required left")
        await _settled(pilot)
        reel.tui(app, hold=2.0, keys="enter", caption="opens the form")
        await pilot.press("1")
        await _settled(pilot)
        reel.tui(app, hold=1.4, keys="1", caption="ship")
        await pilot.press("tab")
        await _settled(pilot)
        reel.tui(app, hold=1.0, keys="tab", caption="to answer")
        await pilot.press("enter")
        await shows(pilot, "What should the changelog call it?")
        await _settled(pilot, 1.0)
        reel.tui(app, hold=2.4, keys="enter", caption="the next question, in words")
        await pilot.press(*"Discount codes at checkout")
        await _settled(pilot)
        reel.tui(app, hold=1.4, caption="typed at the prompt")
        await pilot.press("enter")
        await shows(pilot, "ctrl+c Exit")
        await _settled(pilot, 1.0)
        reel.tui(app, hold=3.5, keys="enter", poster=True)
        reel.save()


async def test_a_role_is_claimed_and_left_in_the_terminal(world: World) -> None:
    _asked(world)
    async with world.tui(size=(100, 30)) as (app, pilot):
        await shows(pilot, "Enter opens it")
        await _settled(pilot, 1.0)
        for _ in range(4):
            await pilot.press("shift+tab")
            await _settled(pilot)
            await pilot.press(*"/claim", "enter")
            await _settled(pilot, 0.6)
            if "Only you can answer for reviewer" in _screen(app):
                break
        await shows(pilot, "Only you can answer for reviewer")
        await pilot.press(*"/afk", "enter")
        await shows(pilot, "away as reviewer")
        await _settled(pilot, 1.5)
        shots.tui(app, f"{_PAGE}-terminal-away")


def _screen(app: object) -> str:
    from tests.integration.doubles_tui import screen

    return screen(app)  # pyright: ignore[reportArgumentType]


# -- from the command line ------------------------------------------------------------


def test_nobody_is_there_from_the_command_line(world: World) -> None:
    _own(world)
    shots.cli(
        [
            "hmz",
            "exec",
            "-f",
            "ship_it",
            "-a",
            f"coder={AGENT}",
            "-p",
            "budget.duration=10m",
            "Add a discount code",
        ],
        f"{_PAGE}-exec",
        columns=104,
    )
