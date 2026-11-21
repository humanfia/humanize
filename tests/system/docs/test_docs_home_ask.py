"""The home page's Ask scene: a flow asks its person a question, and goes on when answered.

`rlar` has no person in it, so the flow is the scene's own, written into the project as
`@local/rlar`: the loop of `rlar` -- an actor works, a reviewer reads what it did -- with a
person at its end, the `owner`, who is asked whether the change ships before the actor opens
its pull request. Both reels are of the actor's thread, with the question under it, and both
open on the question waiting and rest there:

- `home-ask`, in Humanize Desktop's window: what the actor did stands in its thread, and the
  card under it asks `Ship this change?` with its two answers as buttons; `ship` is picked
  and sent, the card folds to `You answered: ship`, and the thread goes on -- the actor
  pushes the change and opens its pull request;
- `home-ask-phone`, the same thread in the web page on a phone, where the card is left
  little room -- the thread keeps a floor under it -- and not that for the question, the
  name of its field, the two answers and the foot they are sent from.
  There the flow names its one field as its question is, and the card is scrolled, as a
  thumb would, to that field: the question, its two answers and the button that sends.

Run it by naming it: `uv run pytest tests/system/docs/test_docs_home_ask.py`.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from playwright.sync_api import expect

from tests.system.docs import home, shots
from tests.system.web.doubles_browser import go

if TYPE_CHECKING:
    from collections.abc import Callable

    from playwright.sync_api import Locator, Page

    from tests.system.docs.conftest import World

_FLOW = '''"""RLAR, with its person asked before the change ships."""

from typing import Literal

from pydantic import BaseModel, Field

from hmz.flows import (
    Agent,
    AgentCollection,
    EnvCollection,
    FlowContext,
    FlowParams,
    LocalEnv,
    Outworlder,
    ShellEnvMixin,
    flow,
)


class Review(BaseModel):
    done: bool = Field(description="Whether the task is done.")
    notes: str = Field(description="What the actor is told.")


class Release(BaseModel):
    verdict: Literal["ship", "hold"]


class Agents(AgentCollection):
    actor: Agent
    reviewer: Agent
    owner: Outworlder


class Workspace(LocalEnv, ShellEnvMixin): ...


class Envs(EnvCollection):
    workspace: Workspace


@flow(agents=Agents, envs=Envs, params=FlowParams)
async def rlar(
    task: str, *, agents: Agents, envs: Envs, params: FlowParams, ctx: FlowContext
) -> str:
    """An actor works until a reviewer is satisfied, and its person says whether it ships."""
    actor, reviewer, owner = agents["actor"], agents["reviewer"], agents["owner"]
    workspace = envs["workspace"]
    working = await actor.spawn()
    asking = await owner.spawn()
    prompt = task
    while True:
        await actor.run(prompt, session=working, env=workspace)
        review = await reviewer.run(
            "Review the work on: " + task,
            session=await reviewer.spawn(),
            env=workspace,
            output_schema=Review,
        )
        if review.done:
            break
        prompt = review.notes
    release = await owner.run(
        "Ship this change?", session=asking, output_schema=Release
    )
    if release.verdict == "hold":
        return "held"
    await actor.run("Open the pull request.", session=working, env=workspace)
    return await reviewer.run(
        "Read the pull request.", session=await reviewer.spawn(), env=workspace
    )
'''

#: The same flow as a phone is shown it: its one field is named as its question is. A phone's
#: card has not the room for the question over the field's name over the answers, and is
#: scrolled to the field: there the name is what asks.
_TITLED = _FLOW.replace(
    '    verdict: Literal["ship", "hold"]\n',
    '    verdict: Literal["ship", "hold"] = Field(title="Ship this change?")\n',
)

#: How many seconds the actor's first step takes once it is told to ship: long enough for a
#: frame of it to be taken, light and dark, before the next.
_STEP = 10


def _tool(name: str, takes: float, result: str, **said: str) -> dict[str, Any]:
    return {"name": name, "input": said, "result": result, "takes": takes}


def _says(*, short: bool) -> dict[str, Any]:
    """What the flow's agents say: the actor does the task, and ships it when told to.

    The first key found in what an agent is told answers it, so the reviewer's last turn,
    which keeps the epic running once the pull request is open, stands before the actor's.

    Args:
      short: Whether the thread is a phone's, which has the room for fewer lines: one
        that outgrows it scrolls, and every line of it moves at once.
    """
    done = "Checkout takes a coupon now: WELCOME10 is 10% off. All six tests pass."
    opened = "Opened pull request #12: checkout takes a coupon."
    work = [
        _tool("Read", 0.2, "...", file_path="shop/checkout.py"),
        _tool("Edit", 0.2, "edited", file_path="shop/checkout.py"),
        _tool("Read", 0.2, "...", file_path="tests/test_checkout.py"),
        _tool("Edit", 0.2, "edited", file_path="tests/test_checkout.py"),
        _tool("Bash", 0.2, "6 passed in 0.21s", command="pytest -q"),
    ]
    ships = [
        _tool("Bash", _STEP, "1 file changed", command="git commit -am coupon"),
        _tool("Bash", 0.3, "pushed", command="git push -u origin coupon"),
        _tool("Bash", 0.3, "opened", command="gh pr create --fill"),
    ]
    if short:
        done, opened = (
            "WELCOME10 takes 10% off. 6 tests pass.",
            "Opened pull request #12.",
        )
        # Two tools of the desk's five, each long enough that the turn is not said to have
        # taken no time at all.
        work = [{**work[1], "takes": 0.6}, {**work[4], "takes": 0.6}]
        ships = [{**ships[2], "takes": _STEP}]
    return {
        "Read the pull request": {"text": "It reads well.", "after": 60},
        "pull request": {"text": opened, "tools": ships},
        "coupon": {"text": done, "tools": work},
    }


def _corner(button: Locator) -> tuple[float, float]:
    """Where a pointer rests on a button: its lower right corner, clear of what it says."""
    box = button.bounding_box()
    assert box
    return (box["x"] + box["width"] - 9, box["y"] + box["height"] - 4)


def _beside(line: Locator) -> tuple[float, float]:
    """Where a pointer rests by a line of the thread: after its last word, clear of it."""
    end = line.evaluate(
        """(line) => {
            const range = document.createRange();
            range.selectNodeContents(line);
            const rects = range.getClientRects();
            const last = rects[rects.length - 1];
            return [last.right, last.bottom];
        }"""
    )
    return (end[0] + 28, end[1] - 4)


def _scrolled(page: Page) -> None:
    """Scrolls a phone's card, as a thumb would, to its field.

    The field's name is left whole under the card's edge, and its answers whole over the foot.
    """
    card = page.locator('[data-hmz="question"]').first
    field = card.get_by_text("Ship this change?").last.bounding_box()
    frame = card.bounding_box()
    assert field
    assert frame
    card.evaluate("(card, by) => card.scrollBy(0, by)", field["y"] - frame["y"] - 5)


def _asked(world: World, page: Page, *, short: bool) -> str:
    """Leaves the task with the flow, waiting on its question, and opens the actor's thread.

    Returns:
      The epic's name.
    """
    flow = _TITLED if short else _FLOW
    world.committed("Add our rlar", {".hmz/flows/rlar/__init__.py": flow})
    world.says(_says(short=short))
    name = world.epic("@local/rlar", home.TASK, until="asked")
    go(page, f"/epics/{name}")
    expect(page.locator('[data-hmz="question"]').first).to_be_visible(timeout=60_000)
    actor = page.get_by_label("Say it to").locator("option").nth(1)
    go(page, f"/epics/{name}/sessions/{actor.get_attribute('value')}%2F1")
    expect(page.get_by_role("log")).to_contain_text("tests pass")
    return name


def _answered(
    page: Page, reel: shots.Reel, *, first: str, held: Callable[[Page], None]
) -> None:
    """Plays the scene from the question waiting to the pull request opened, and saves it.

    Args:
      page: The page, on the actor's thread as the reel shows it, the question under it.
      reel: What the frames are taken into.
      first: What the actor does first when the change ships, as its thread says it.
      held: Puts the card back where the reel shows it, once an answer is picked: the
        page brings what is picked into view, which on a phone scrolls the card.
    """
    card = page.locator('[data-hmz="question"]').first
    log = page.get_by_role("log")
    ship = card.get_by_role("radio", name="ship")
    send = card.locator('[data-hmz="ask-send"]')
    reel.web(page, hold=3.6, pointer=_corner(ship), click=True, poster=True)
    ship.click()
    expect(send).to_have_text("Send answer")
    # A draft is said to be kept, for a moment: the frame is of the card once it has gone.
    draft = card.locator('[data-hmz="ask-draft"]')
    expect(draft).to_have_text("Draft kept")
    expect(draft).to_have_text("", timeout=10_000)
    held(page)
    reel.web(page, hold=1.2, pointer=_corner(send), click=True)
    send.click()
    expect(page.get_by_text("You answered")).to_be_visible(timeout=60_000)
    expect(log).to_contain_text(first)
    expect(page.get_by_text("Waiting", exact=True)).to_be_hidden()
    # The pointer leaves the strip the card folded to, whose one button dismisses it, for
    # the work that follows the answer.
    reel.web(page, hold=1.3, pointer=_beside(log.get_by_text(first).last))
    opened = log.get_by_text("Opened pull request #12").last
    expect(opened).to_be_visible(timeout=60_000)
    expect(log.get_by_text("Worked for")).to_have_count(2)
    reel.web(page, hold=2.2, pointer=_beside(opened))
    expect(page.get_by_role("button", name="Stop")).to_be_visible()
    reel.save()


def test_a_question_is_answered_at_a_desk(world: World) -> None:
    with home.desk(world) as page:
        name = _asked(world, page, short=False)
        # The thread and the question under it are the picture: the panel beside them is
        # folded, and the sidebar's list of the epic's sessions, which is not what moves.
        page.get_by_role("button", name="Toggle panel").click()
        page.get_by_role("button", name="Collapse", exact=True).click()
        page.mouse.move(160, 480)
        page.evaluate("document.activeElement?.blur()")
        reel = shots.Reel("home-ask", window="desktop")
        _answered(page, reel, first="git commit", held=lambda _: None)
    world.stop(name)


def test_a_question_is_answered_on_a_phone(world: World) -> None:
    with home.phone(world) as page:
        name = _asked(world, page, short=True)
        _scrolled(page)
        reel = shots.Reel("home-ask-phone")
        _answered(page, reel, first="gh pr create", held=_scrolled)
    world.stop(name)
