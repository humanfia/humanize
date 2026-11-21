"""The home page's Steer scene: a person says a line to an agent at work, and it takes it up.

Two reels of one story (`home.py`): `home-steer`, the actor's thread in Humanize Desktop's
window, and `home-steer-phone`, the same thread in the web page on a phone. The flow is the
stand-in `rlar` on the home page's task: its actor has worked twice and been sent back twice,
and is on its third turn, running the tests, when the reel opens. The person writes a line in
the box under its thread and sends it; the line lands in the thread, in the turn under way,
and the actor goes on from it: it edits the checkout, runs the tests again and answers the
line. Run it by naming it: `uv run pytest tests/system/docs/test_docs_home_steer.py`.

Three things are staged here, the world coming with none of them:

- a stand-in `claude` that says it has taken a word put into a turn under way, as Claude
  Code does (`command_lifecycle`), and then does what is scripted for that word before it
  answers: the conftest's reads nothing until its turn is over, and the page draws a line
  only once its agent says it has it (`_hears`);
- turns as long as a person would believe: a quarter of a minute each for the two that are
  over, so the scene is most of a minute old before its first frame;
- the page's clock, which a frame taken twice over, light and dark, would run several times
  too fast for a reel: it is set at each frame to when in the reel the frame is shown
  (`page.clock`), so the header counts the seconds the reel plays. What the turns say they
  took is the daemon's own count and is left as it is. The header says when the epic began
  once, as it is drawn, so the thread is opened anew under that clock: "began" and "took"
  are then of one moment.

Before each frame the thread is moved up by the few pixels that bring the row cut by its
top edge wholly into view (`_WHOLE`): a phone's thread is short, and read from its end it
would open on half a line.

The header's rate ("41 out/s") is left as the page draws it. It is the live readout every
scene of the home page has, of stand-in agents no price list is fetched for
(`conftest._priced`), and no result of anything: dropping it here alone would make this
scene the odd one of six.
"""

from __future__ import annotations

import datetime
import shutil
from pathlib import Path
from typing import TYPE_CHECKING, Any

from playwright.sync_api import expect

from tests.system.docs import home, shots
from tests.system.web.doubles_browser import go

if TYPE_CHECKING:
    from playwright.sync_api import Page

    from tests.system.docs.conftest import World

#: What the person says to the actor while it works.
_LINE = "Also refuse expired codes"

#: How much of the line is in the box at each frame of its being written.
_TYPED = (6, 13, 21, len(_LINE))

#: How many seconds each frame is shown: the actor at work and the line begun, two more
#: pieces of the line, the whole of it and the click that sends it, the line in the thread,
#: what the actor does about it, and its answer, which the reel rests on.
_HOLDS = (1.3, 0.6, 0.6, 1.1, 1.6, 1.2, 2.8)

#: How many seconds the actor runs the tests for unless it is told something more: longer
#: than the line takes to be written and sent, frames and all.
_RUNNING = 240

#: How many seconds the scene may take to come to its first frame: the two turns that are
#: over, their reviews, and the start of the third.
_HISTORY = 120

#: How many seconds each thing the actor does about the line takes: long enough for a frame
#: of it to be taken, light and dark, before the next.
_STEP = 9

#: How many seconds the reel's frames take to be taken, less the seconds they are shown for:
#: the page's clock is set that far ahead at the first, to be about right by the last.
_AHEAD = 22

#: Brings the row the thread's top edge cuts wholly into view, a little air over it: the
#: thread is moved up by as much of the row as was hidden, and again while that uncovers
#: another, never so far that the thread stops following what is said (60 pixels of its end).
#: Answers how far it was moved, and how far the last row now reaches under the bottom edge.
_WHOLE = """(log) => {
  let scroller = log
  const scrolls = (one) =>
    one.scrollHeight > one.clientHeight && /auto|scroll/.test(getComputedStyle(one).overflowY)
  while (scroller && !scrolls(scroller)) scroller = scroller.parentElement
  if (!scroller) return [0, 0]
  const edge = scroller.getBoundingClientRect()
  const range = document.createRange()
  const rows = () => {
    const found = []
    const walker = document.createTreeWalker(log, NodeFilter.SHOW_TEXT)
    for (let node; (node = walker.nextNode()); ) {
      range.selectNodeContents(node)
      found.push(...[...range.getClientRects()].filter((rect) => rect.height))
    }
    return found
  }
  let moved = 0
  for (let turn = 0; turn < 8; turn++) {
    const cut = rows().filter((rect) => rect.top < edge.top + 4 && rect.bottom > edge.top)
    if (!cut.length) break
    const by = Math.ceil(edge.top + 4 - Math.min(...cut.map((rect) => rect.top)))
    if (moved + by >= 56) break
    scroller.scrollTop -= by
    moved += by
  }
  return [moved, Math.max(0, ...rows().map((rect) => rect.bottom)) - edge.bottom]
}"""

#: What the stand-in `claude` reads its stream with, in place of the loop that reads a line
#: only once the turn before it is over: a thread reads, so that a turn under way can be told
#: something more. `working` is how a tool takes its time: until the time is up or a word
#: arrives, which it says it has taken, as Claude Code does, by the `uuid` the word came
#: under. A turn's own prompt is said to be taken the same way.
_HEARS = """
import queue, threading

INBOX = queue.Queue()
TAKEN = []


def reads():
    for line in sys.stdin:
        INBOX.put(line)
    INBOX.put(None)


def working(seconds):
    until = time.monotonic() + seconds
    while (left := until - time.monotonic()) > 0:
        try:
            line = INBOX.get(timeout=left)
        except queue.Empty:
            return
        if line is None:
            os._exit(0)
        more = json.loads(line)
        if more.get("type") != "user":
            continue
        out({"type": "command_lifecycle", "state": "started",
             "command_uuid": more.get("uuid", "")})
        TAKEN.append(more["message"]["content"][0]["text"])
        return


threading.Thread(target=reads, daemon=True).start()
for line in iter(INBOX.get, None):
    said = json.loads(line)
    if said.get("type") != "user":
        continue
    if said.get("uuid"):
        out({"type": "command_lifecycle", "state": "started", "command_uuid": said["uuid"]})
"""

#: And how it goes through a line's tools: when they are done, or one was cut short, it does
#: what is scripted for each word it took meanwhile, and answers with what that says.
_TAKES = """    todo = list(line.get("tools", []))
    while todo or TAKEN:
        if not todo:
            word = TAKEN.pop(0)
            more = next((one for key, one in lines if key in word), {})
            todo = list(more.get("tools", []))
            text = more.get("text", text)
            continue
        tool = todo.pop(0)
"""


def _hears() -> None:
    """Teaches the stand-in `claude` to take a word put into a turn under way.

    Claude Code reads its stream while it works, and answers a word written to it mid-turn
    with a `command_lifecycle` line once the word is in front of the model; it then goes on
    with that word in mind. The daemon writes a line said to a session into its open turn,
    and says it in the thread when the agent says it has it. The conftest's stand-in reads
    nothing until its turn is over and never says so: this one does both, and a word it takes
    is answered by what `World.says` scripts for that word, done within the same turn.
    """
    found = shutil.which("claude")
    assert found is not None
    claude = Path(found)
    source = claude.read_text()
    for was, now in (
        (
            (
                "\nfor line in sys.stdin:\n    said = json.loads(line)\n"
                '    if said.get("type") != "user":\n        continue\n'
            ),
            _HEARS,
        ),
        ('    for number, tool in enumerate(line.get("tools", [])):\n', _TAKES),
        (
            '        time.sleep(tool.get("takes", 0))\n',
            '        working(tool.get("takes", 0))\n',
        ),
    ):
        assert source.count(was) == 1, f"the stand-in claude no longer says {was!r}"
        source = source.replace(was, now)
    claude.write_text(source)


def _tool(
    name: str, given: dict[str, str], result: str, takes: float
) -> dict[str, Any]:
    """One thing the agent does before it answers."""
    return {"name": name, "input": given, "result": result, "takes": takes}


def _says() -> dict[str, Any]:
    """What `rlar`'s agents say: the actor is sent back twice, and told the line in its third.

    The first key found in what an agent is told answers it, so the reviewer's lines stand
    before the actor's: each review is told what the actor said last. The line itself is a
    key too: what the actor does, and answers, once it has taken it.
    """
    checkout, tests = "shop/checkout.py", "tests/test_checkout.py"
    return {
        "ExpiredCode": {
            "json": {"done": True, "notes": "Coupons work; expired codes are refused."},
            "after": 60,
        },
        "Seven tests": {
            "json": {"done": False, "notes": "Round the discount to whole cents."},
            "after": 2,
        },
        "meticulous reviewer": {
            "json": {"done": False, "notes": "Add a test for a code used twice."},
            "after": 2,
        },
        "expired codes": {
            "text": "Expired codes are refused now: charge() raises ExpiredCode. "
            "Nine tests pass.",
            "tools": [
                _tool("Edit", {"file_path": checkout}, "edited", _STEP),
                _tool("Bash", {"command": "pytest -q"}, "9 passed in 0.24s", _STEP),
            ],
        },
        "whole cents": {
            "text": "The discount is rounded to whole cents. Eight tests pass.",
            "tools": [
                _tool("Read", {"file_path": checkout}, "def charge(): ...", 2),
                _tool("Edit", {"file_path": checkout}, "edited", 3),
                _tool("Edit", {"file_path": tests}, "edited", 2),
                _tool("Bash", {"command": "pytest -q"}, "8 passed in 0.23s", _RUNNING),
            ],
        },
        "used twice": {
            "text": "A code used twice is refused. Seven tests pass.",
            "tools": [
                _tool("Read", {"file_path": tests}, "...", 2),
                _tool("Edit", {"file_path": tests}, "edited", 5),
                _tool("Bash", {"command": "pytest -q"}, "7 passed in 0.22s", 6),
            ],
            "after": 2,
        },
        "coupon": {
            "text": "Checkout takes a coupon now: WELCOME10 is 10% off. Six tests pass.",
            "tools": [
                _tool("Read", {"file_path": checkout}, "def charge(): ...", 2),
                _tool("Edit", {"file_path": checkout}, "edited", 3),
                _tool("Edit", {"file_path": tests}, "edited", 2),
                _tool("Bash", {"command": "pytest -q"}, "6 passed in 0.21s", 3),
            ],
            "after": 1,
        },
    }


def _epic(world: World) -> str:
    """Starts the flow on the task and answers the epic's name, left running."""
    return world.epic(home.FLOW, home.TASK, until=None)


def _steered(world: World, page: Page, reel: shots.Reel, *, folded: bool) -> None:
    """Plays the scene in a page, a frame at a time, and writes the reel.

    Args:
      world: Where the flow runs.
      page: The page, at a desk's size or a phone's.
      reel: What the frames are taken into.
      folded: Whether the panel beside the thread is folded first: at a desk it stands open,
        and the thread is what the picture is of.
    """
    _hears()
    world.says(_says())
    name = _epic(world)
    go(page, f"/epics/{name}")
    expect(page.get_by_role("button", name="Stop")).to_be_visible()
    to = page.get_by_label("Say it to")
    actor = to.locator("option").nth(1).get_attribute("value")
    assert actor
    thread = f"/epics/{name}/sessions/{actor}%2F1"
    go(page, thread)
    log = page.get_by_role("log")
    box = page.get_by_role("textbox", name="What to say")
    send = page.get_by_role("button", name="Send")
    size = page.viewport_size
    assert size is not None
    holds = iter(_HOLDS)
    shown = 0.0

    def frame(**how: Any) -> None:
        """Takes the next frame, the page's clock at when in the reel it is shown."""
        nonlocal shown
        moved, under = log.evaluate(_WHOLE)
        assert under <= 0, f"the thread's last row is cut by {under}px, moved {moved}px"
        page.clock.set_fixed_time(began + datetime.timedelta(seconds=shown))
        # The header says how long the epic has taken once a second.
        page.wait_for_timeout(1100)
        hold = next(holds)
        reel.web(page, hold=hold, **how)
        shown += hold

    def written(upto: int, since: int) -> None:
        box.press_sequentially(_LINE[since:upto])

    # Two turns are over, and the actor's third is under way: it is running the tests. It
    # goes on running them for as long as the line takes to be written.
    patience = _HISTORY * 1000
    expect(log.get_by_text("is working")).to_have_count(3, timeout=patience)
    expect(log.get_by_text("pytest -q")).to_have_count(3, timeout=patience)
    # The thread is opened again under the reel's clock: the header says when the epic began
    # as it is drawn, and never again, so one drawn as the epic started says "just now" still.
    began = datetime.datetime.now(datetime.UTC) + datetime.timedelta(seconds=_AHEAD)
    page.clock.set_fixed_time(began)
    go(page, f"/epics/{name}")
    go(page, thread)
    if folded:
        page.get_by_role("button", name="Toggle panel").click()
    expect(box).to_have_attribute("placeholder", f"Message {actor}/1")
    expect(log.get_by_text("pytest -q")).to_have_count(3)
    expect(page.get_by_text("began just now")).to_have_count(0)
    box.click()
    written(_TYPED[0], 0)
    frame(pointer=box)
    written(_TYPED[1], _TYPED[0])
    frame(cut=True)
    written(_TYPED[2], _TYPED[1])
    frame(cut=True)
    written(_TYPED[3], _TYPED[2])
    frame(pointer=send, click=True, cut=True)
    # Sent into the turn under way: the actor says it has it, and the thread says the line.
    expect(log).not_to_contain_text("Eight tests")
    place = send.bounding_box()
    assert place is not None
    send.click()
    expect(box).to_have_value("")
    expect(page.get_by_text("alex@web said")).to_be_visible()
    expect(log.get_by_text("Edit shop/checkout.py")).to_have_count(3)
    # The person has said it, and the hand leaves the window.
    frame(pointer=(place["x"] + place["width"] / 2, size["height"] + 140.0))
    # Each of the two was taken before the actor went on: no frame is of a later moment.
    assert log.get_by_text("pytest -q").count() == 3, "the frame of the line was late"
    expect(log.get_by_text("pytest -q")).to_have_count(4)
    frame()
    assert "Nine tests" not in log.inner_text(), "the frame of the tests was late"
    expect(log).to_contain_text("Nine tests pass")
    expect(log.get_by_text("Worked for")).to_have_count(3)
    frame(poster=True)
    expect(log).not_to_contain_text("Eight tests")
    expect(page.get_by_role("button", name="Stop")).to_be_visible()
    reel.save()


def test_a_line_is_said_to_an_agent_at_work_at_a_desk(world: World) -> None:
    with home.desk(world) as page:
        _steered(world, page, shots.Reel("home-steer", window="desktop"), folded=True)


def test_a_line_is_said_to_an_agent_at_work_on_a_phone(world: World) -> None:
    with home.phone(world) as page:
        _steered(world, page, shots.Reel("home-steer-phone"), folded=False)
