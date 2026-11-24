"""The world the docs' pictures are taken in: a made-up person, machine and project.

Never in CI, and no real agent runs here: like `tests/system/web`, every agent is a stand-in
and nothing is fetched. Run a file by naming it: `uv run pytest
tests/system/docs/test_docs_<page>.py`. `shots.py` beside this says how a picture is taken
-- every one twice, light and dark, from the one run of a scene -- and this says what there is
to take one of.

A scene asks for `world`, and has:

- a person `alex` on a machine `studio`, whose home holds a project `shop` -- a small git
  repository, which is the working directory and what the interfaces open on -- and Humanize's
  own directories where a person's are (`~/.config/humanize`, `~/.local/share/humanize`,
  `~/.local/state/humanize`, `~/.cache/humanize`), all under a temporary directory with no
  name of this machine's in it;
- this machine's daemon, held in the test's process (the `daemon` fixture);
- a stand-in `claude` as the only coding agent, serving `claude-haiku-4-5` and
  `claude-opus-4-1`, which answers what `World.says` scripts for it;
- the stand-in loops installed as flows (`goal`, `ralph_loop`, `rlar`, `stateful_ralph`,
  `flame_chase`, `continue_loop`), and `sign_off`, a flow of the project's own that asks its
  person to approve what its agent did.

and stages the rest by calling it:

==========================================  ===============================================
a chat with a transcript                    `world.says(...)`, then `world.chat(...)`
a flow's epic, running or finished          `world.epic("rlar", ...)`
a question waiting for the person           `world.asks(...)`
accounts, runtimes and other settings       `world.account(...)`, `world.call("runtimes.set")`
an environment with files and changes       `world.changed({...})`, a chat left going
a collected trace                           `world.epic(...)`, then `/epics/<name>/exomyth`
the web page, or the desktop app's window   `with world.page() as page:`
the terminal interface                      `async with world.tui() as (app, pilot):`
==========================================  ===============================================

Everything a picture shows is made up here: add only made-up names to it.
"""

from __future__ import annotations

import contextlib
import dataclasses
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import uuid
from collections.abc import Mapping
from pathlib import Path
from typing import TYPE_CHECKING, Any

import psutil
import pytest

import hmz
from hmz.runtime import telemetry
from tests.conftest import hide_agents, own
from tests.integration.conftest import FLOWS
from tests.integration.doubles_core import AGENT, CLAUDE, MODEL
from tests.integration.doubles_web import PATIENCE, Browser, served
from tests.system.docs import shots
from tests.system.web.doubles_browser import Wire, opened

if TYPE_CHECKING:
    from collections.abc import (
        AsyncGenerator,
        Callable,
        Generator,
        Iterator,
        Sequence,
    )

    from playwright.sync_api import Page
    from textual.pilot import Pilot

    from hmz.daemon.private import Private
    from hmz.tui import Humanize
    from hmz.web.site import Site
    from tests.integration.doubles_web import Session

__all__ = ["AGENT", "HOST", "MODEL", "PROJECT", "USER", "World"]

#: Who the pictures are of: the person, their machine and their project.
USER = "alex"
HOST = "studio"
PROJECT = "shop"

#: What the machine is said to have: its CPUs, and its memory in bytes.
_CPUS = 8
_MEMORY = 16 * 1024**3

#: What the stand-in agent answers where nothing is scripted for what it was told.
_DONE = "Done."

#: The project: a small shop, as it is first committed.
_SHOP = {
    "README.md": "# shop\n\nA small storefront: a catalogue, a cart and a checkout.\n",
    "pyproject.toml": '[project]\nname = "shop"\nversion = "0.3.0"\n',
    "shop/__init__.py": '"""A small storefront."""\n',
    "shop/catalogue.py": (
        '"""What the shop sells."""\n\n'
        "PRICES = {\n"
        '    "mug": 1200,\n'
        '    "tote": 1800,\n'
        '    "poster": 900,\n'
        "}\n"
    ),
    "shop/cart.py": (
        '"""A cart: what somebody means to buy."""\n\n'
        "from shop.catalogue import PRICES\n\n\n"
        "def total(items: dict[str, int]) -> int:\n"
        '    """What a cart comes to, in cents."""\n'
        "    return sum(PRICES[name] * count for name, count in items.items())\n"
    ),
    "shop/checkout.py": (
        '"""Paying for a cart."""\n\n'
        "from shop.cart import total\n\n\n"
        "def charge(items: dict[str, int]) -> int:\n"
        '    """What is charged for a cart, in cents."""\n'
        "    return total(items)\n"
    ),
    "tests/test_cart.py": (
        "from shop.cart import total\n\n\n"
        "def test_total() -> None:\n"
        '    assert total({"mug": 2}) == 2400\n'
    ),
}

#: A flow of the project's own with a person in it: its agent does the task, and its person
#: is shown what changed and asked to sign it off, as one form.
_SIGN_OFF = '''
"""Sign-off -- an agent does the task, and a person approves what it did.

    hmz exec -f @local/sign_off -a coder=claude/claude-opus-4-1 -p budget.cost=5 "the task"
"""

import enum

import pydantic

from hmz.flows import (
    Agent, AgentCollection, Diff, EnvCollection, FlowContext, FlowParams, LocalEnv,
    Markdown, Outworlder, ShellEnvMixin, flow,
)


class Verdict(enum.StrEnum):
    APPROVE = "approve"
    CHANGES = "request changes"
    REJECT = "reject"


class Review(pydantic.BaseModel):
    """What the person decides."""

    verdict: Verdict = pydantic.Field(description="What to do with the change.")
    notes: str = pydantic.Field("", description="What to change, if anything.")


class Agents(AgentCollection):
    """The agent that does the work, and the person who signs it off."""

    coder: Agent
    reviewer: Outworlder


class Workspace(LocalEnv, ShellEnvMixin):
    """The project, and a shell in it."""


class Envs(EnvCollection):
    """Where it works."""

    workspace: Workspace


@flow(agents=Agents, envs=Envs, params=FlowParams)
async def sign_off(
    task: str, *, agents: Agents, envs: Envs, params: FlowParams, ctx: FlowContext
) -> None:
    """An agent does the task, and a person approves what it did."""
    coder, reviewer = agents["coder"], agents["reviewer"]
    session, person = await coder.spawn(), await reviewer.spawn()
    said = await coder.run(task, session=session, env=envs["workspace"])
    while True:
        _, patch, _ = await envs["workspace"].exec(["git", "diff"])
        review = await reviewer.run(
            "Sign off this change?",
            session=person,
            output_schema=Review,
            context=(Markdown(title="What the agent says", text=said), Diff(patch=patch)),
        )
        if review.verdict is not Verdict.CHANGES:
            return
        said = await coder.run(review.notes, session=session, env=envs["workspace"])
'''

#: What a scripted line may say besides its `text`.
type Line = str | Sequence[str] | Mapping[str, Any]

# The stand-in `claude` of the core tests, taught to say what a scene scripts for it: found
# by what it was told, said after the tools the line names, at a believable length and cost.
_SCRIPTED = r"""
import time

LINES = pathlib.Path(sys.argv[0]).with_name("lines.json")


def record(kind, content):
    with transcript.open("a") as kept:
        kept.write(json.dumps({
            "type": kind, "sessionId": session, "cwd": os.getcwd(),
            "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "requestId": str(uuid.uuid4()),
            "message": {"id": str(uuid.uuid4()), "model": model, "role": kind,
                        "content": content,
                        "usage": {"input_tokens": 900, "output_tokens": 60}}}) + "\n")


def scripted(said):
    try:
        lines = json.loads(LINES.read_text())
    except OSError:
        lines = []
    line = next((line for key, line in lines if key in said), None)
    if line is None or (schema and "json" not in line):
        return answer(said)
    text = json.dumps(line["json"]) if schema else line.get("text", "")
    if isinstance(text, list):
        # Each time it is told this, the next of what it says, the last from then on.
        counts = own / "standin-said.json"
        try:
            told = json.loads(counts.read_text())
        except (OSError, ValueError):
            told = {}
        key = next(key for key, one in lines if one is line)
        at = told.get(key, 0)
        told[key] = at + 1
        counts.write_text(json.dumps(told))
        text = text[min(at, len(text) - 1)]
    for name, content in line.get("writes", {}).items():
        at = pathlib.Path(name)
        at.parent.mkdir(parents=True, exist_ok=True)
        at.write_text(content)
    for number, tool in enumerate(line.get("tools", [])):
        ident = f"toolu_{uuid.uuid4().hex[:12]}"
        used = [{"type": "tool_use", "id": ident, "name": tool["name"],
                 "input": tool.get("input", {})}]
        out({"type": "assistant", "message": {"id": str(uuid.uuid4()), "model": model,
             "content": used, "usage": {"input_tokens": 900, "output_tokens": 60}}})
        record("assistant", used)
        time.sleep(tool.get("takes", 0))
        result = [{"type": "tool_result", "tool_use_id": ident,
                   "content": tool.get("result", "")}]
        out({"type": "user", "message": {"role": "user", "content": result}})
        record("user", result)
    time.sleep(line.get("after", 0))
    if "fail" in line:
        out({"type": "result", "subtype": "error_during_execution", "is_error": True,
             "session_id": session, "result": line["fail"]})
        sys.exit(1)
    return text


"""


def _stand_in() -> str:
    """The stand-in `claude`: the core tests' own, scripted, believable in what it spends."""
    source = CLAUDE

    def patched(was: str, now: str, times: int = 1) -> None:
        nonlocal source
        assert source.count(was) == times, f"the stand-in claude no longer says {was!r}"
        source = source.replace(was, now)

    patched("\nfor line in sys.stdin:\n", f"\n{_SCRIPTED}for line in sys.stdin:\n")
    patched("    answered = answer(text)\n", "    answered = scripted(text)\n")
    patched(
        '    if "Write" not in flags.get("--disallowedTools", "").split(","):\n'
        '        with pathlib.Path("landed.txt").open("a") as landed:\n'
        '            landed.write(said + "\\n")\n'
        '    return "did: " + said\n',
        f"    return {_DONE!r}\n",
    )
    # What a turn spends: by how much was said, not ten tokens in and seven out.
    patched('spent["in"] += 10', 'spent["in"] += 2400 + 3 * len(text)')
    patched('spent["out"] += 7', 'spent["out"] += 60 + len(answered or "") // 3')
    patched(
        '"usage": {"input_tokens": 10, "output_tokens": 7}',
        '"usage": {"input_tokens": 2400 + 3 * len(text),'
        ' "output_tokens": 60 + len(answered or "") // 3}',
        2,
    )
    return source


@dataclasses.dataclass(frozen=True)
class _Stage:
    """Where the world stands: the person's home, and what is in it."""

    base: Path
    home: Path
    workspace: Path
    bin: Path


@pytest.fixture
def _stage(monkeypatch: pytest.MonkeyPatch) -> Iterator[_Stage]:
    """A home, a project and a `bin/` under a temporary directory with no name of ours in it.

    Not pytest's `tmp_path`, which is named after whoever runs the suite: a path a picture
    shows is `/private/tmp/hmz-<random>/alex/shop`, or `~/shop`.
    """
    base = Path(tempfile.mkdtemp(prefix="hmz-", dir="/private/tmp"))
    stage = _Stage(base, base / USER, base / USER / PROJECT, base / "bin")
    for one in (stage.workspace, stage.bin, base / "site"):
        one.mkdir(parents=True)
    # Every Python started from here -- `hmz`, a stand-in, a daemon -- is on this machine
    # too, and says so by its name: told the made-up one as this process is.
    (base / "site" / "sitecustomize.py").write_text(
        f"import os, socket\nsocket.gethostname = lambda: {HOST!r}\n"
        f"os.cpu_count = lambda: {_CPUS}\n"
    )
    monkeypatch.setattr(socket, "gethostname", lambda: HOST)
    # And what the machine is made of, which an environment says of itself.
    memory = psutil.virtual_memory()
    monkeypatch.setattr(os, "cpu_count", lambda: _CPUS)
    monkeypatch.setattr(
        psutil, "virtual_memory", lambda: memory._replace(total=_MEMORY)
    )
    monkeypatch.setenv("PYTHONPATH", str(base / "site"))
    for name in ("USER", "LOGNAME"):
        monkeypatch.setenv(name, USER)
    try:
        yield stage
    finally:
        shutil.rmtree(base, ignore_errors=True)


@pytest.fixture(autouse=True)
def _no_real_agents(
    _temporary: Path, _stage: _Stage, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Overrides `tests/system`'s: the agents here are stand-ins, in the made-up home."""
    hide_agents(_temporary, monkeypatch)
    monkeypatch.setenv("HOME", str(_stage.home))


@pytest.fixture(autouse=True)
def _humanize_home(
    _humanize_home: None, _stage: _Stage, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The root's, moved to where the person's own would be: under `~`."""
    for name, value in own(_stage.home).items():
        monkeypatch.setenv(name, value)
    telemetry.again()


@pytest.fixture(autouse=True)
def _asks_its_cli() -> None:
    """Overrides `tests/system`'s: `world` asks for `asking` itself."""


@pytest.fixture(autouse=True)
def _priced() -> None:
    """Overrides `tests/system`'s: no price list is fetched."""


@pytest.fixture(autouse=True)
def _loops_installed(_humanize_home: None) -> None:
    """Overrides `tests/system`'s: the stand-in loops, where an install would keep them.

    Humanize ships no flow, and nothing is fetched here: the loops are the ones the
    integration tests run, written in the shape of the ones the official index lists.
    """
    from hmz.runtime.flowing.index import kept
    from hmz.runtime.flowing.verses import OFFICIAL

    shutil.copytree(
        FLOWS,
        kept(OFFICIAL),
        ignore=shutil.ignore_patterns("__pycache__"),
        dirs_exist_ok=True,
    )


@pytest.fixture(autouse=True, scope="session")
def _studio() -> Iterator[None]:
    """Shuts the pictures' own browser after the last scene."""
    yield
    shots.shut()


def _git(at: Path, *argv: str) -> None:
    subprocess.run(
        [
            "git",
            "-c",
            "user.name=Alex Kim",
            "-c",
            "user.email=alex@example.com",
            *argv,
        ],
        cwd=at,
        check=True,
        capture_output=True,
    )


def _record(sub: str, kind: str) -> Callable[[str, dict[str, Any]], bool]:
    """Whether a notification is a record of one kind, of one subscription."""

    def wanted(method: str, said: dict[str, Any]) -> bool:
        return (
            method == "epic.event"
            and said["sub"] == sub
            and said["message"].get("type") == kind
        )

    return wanted


@dataclasses.dataclass
class World:
    """The made-up world a scene is set in, and what stages the rest of it.

    Attributes:
      home: The person's home, `~`.
      workspace: Their project, `~/shop`: a git repository, and the working directory.
      site: The web interface, served for as long as the scene runs.
    """

    home: Path
    workspace: Path
    site: Site
    _bin: Path
    _lines: list[tuple[str, dict[str, Any]]] = dataclasses.field(
        default_factory=list[tuple[str, dict[str, Any]]]
    )

    @property
    def data(self) -> Path:
        """Where Humanize keeps the person's epics and chats: `~/.local/share/humanize`."""
        return hmz.data()

    @property
    def state(self) -> Path:
        """Where it keeps what environments derive: `~/.local/state/humanize`."""
        return hmz.state()

    # -- the interfaces -----------------------------------------------------------------

    @contextlib.contextmanager
    def page(
        self,
        *,
        desktop: bool = False,
        width: int = 1280,
        height: int | None = None,
        dark: bool = False,
        locale: str = "en-US",
        wire: Wire | None = None,
    ) -> Generator[Page]:
        """The web page, open in Chromium on the project, until the block ends.

        Go to a view of it with `go(page, "/new/chat")` (`tests.system.web.doubles_browser`),
        drive it with Playwright as a person would, wait with `expect(...)`, and take
        pictures with `shots.web(page, ...)`. Find things as a person does -- by what they
        say and what they are (`page.get_by_role("button", name="Changes")`,
        `page.get_by_text("WELCOME10")`) -- before by a `data-hmz` name, which the page
        changes as it is worked on. Its views: `/new/chat`, `/new` (a new epic),
        `/chats/<id>`, `/epics/<name>`, `/epics/<name>/exomyth`, `/settings/<page>`
        (`general`, `themes`, `language`, `accounts`, `nous`, `runtimes`, `backup`,
        `workspace`, `usage`, `daemons`). A page that throws, or logs an error, fails the
        scene as the block ends.

        Args:
          desktop: Whether it is the page as Humanize Desktop's window draws it -- its top
            row keeping room for the traffic lights -- at the size that window opens. Take
            its pictures with `window="desktop"`.
          width: How wide the window is, in CSS pixels; under 860 the page is a phone's.
          height: How tall it is: 820 where not said, which is the app's.
          dark: Whether the system asks for dark colours while the scene drives the page.
            No scene needs it for its pictures: `shots` takes every one both light and dark,
            whichever the page is opened in.
          locale: The language the browser asks for.
          wire: A `Wire` (`tests.system.web.doubles_browser`) to carry the page's calls of
            the daemon, where a scene must answer one itself: what no stand-in can stage.

        Yields:
          The page, drawn, its sidebar up.
        """
        with opened(
            self.site,
            width=shots.DESKTOP[0] if desktop else width,
            height=height or shots.DESKTOP[1],
            dark=dark,
            locale=locale,
            user_agent=shots.APP if desktop else None,
            # What lets a picture's light and dark side be taken at one instant.
            init=shots.GATE,
            routed=wire.routes if wire else None,
        ) as page:
            # Its sidebar has read what the project holds: no picture is of it loading.
            page.get_by_text(PROJECT, exact=True).first.wait_for()
            # Nor of its composer still asking which models there are, where it is told.
            with contextlib.suppress(Exception):
                page.get_by_text("Asking…", exact=True).first.wait_for(
                    state="hidden", timeout=3000
                )
            yield page

    @contextlib.asynccontextmanager
    async def tui(
        self, size: tuple[int, int] = (100, 30)
    ) -> AsyncGenerator[tuple[Humanize, Pilot[None]]]:
        """The terminal interface, running in a terminal of a size, until the block ends.

        The scene is an `async def` test. Drive it with the pilot's keys and wait for the
        screen with the helpers of `tests.integration.doubles_tui` (`shows(pilot, "text")`,
        `typed(pilot, "/flow")`, `until(...)`), then take pictures with `shots.tui(app,
        ...)` or `reel.tui(app, ...)`::

            async with world.tui() as (app, pilot):
                await shows(pilot, MODEL)        # set up on the stand-in's model
                shots.tui(app, "tui-home")

        Args:
          size: The terminal's columns and rows.

        Yields:
          The app and its pilot.
        """
        from hmz.tui import Humanize

        app = Humanize()
        async with app.run_test(size=size) as pilot:
            yield app, pilot

    @contextlib.contextmanager
    def session(self) -> Generator[Session]:
        """A JSON-RPC session with the daemon, as the page holds one, until the block ends."""
        browser = Browser(self.site)
        browser.signs_in()
        with browser.session() as session:
            yield session

    def call(self, method: str, **params: Any) -> Any:
        """Calls one method of the daemon, as the page would, and answers its result.

        Whatever a settings page writes is a call (protocol/daemon.md): `world.call(
        "runtimes.set", backend="ssh", name="gpu", fields={"host": "gpu.example"})`,
        `world.call("nous.set", name="claude/claude-opus-4-1", then=[AGENT])`,
        `world.call("settings.set", workspace=str(world.workspace), chat=AGENT)`.
        """
        with self.session() as session:
            return session.call(method, **params)

    # -- what the agent says ------------------------------------------------------------

    def says(self, lines: Mapping[str, Line]) -> None:
        """Scripts the stand-in agent: what it answers when told something.

        Each key is a piece of what it is told -- a chat's message, a flow's task -- and the
        first key found in a prompt answers it; a prompt no key is found in is answered
        `Done.` (and `/goal <task>`, which the `goal` flow says, `goal met: <task>`). An
        answer is Markdown, as an agent writes: say what a real one would. A value is:

        - a string: the answer;
        - a list of strings: the answer the first time, the next the second, and so on;
        - a mapping, for more than words: `text` (a string or such a list), and any of

          - `tools`: what it does first, each `{"name": "Bash", "input": {"command":
            "pytest -q"}, "result": "4 passed", "takes": 0.5}` -- drawn in the transcript as
            a tool call, and in a trace as a span `takes` seconds long;
          - `writes`: files it writes in the project, `{"shop/checkout.py": "<the whole
            file>"}`, so that the environment's Changes show a real diff;
          - `after`: seconds it thinks before answering, so that a scene can take a picture
            of a turn under way;
          - `fail`: the words its turn fails with, in place of an answer;
          - `json`: what it answers a turn that asks for a schema -- `rlar`'s reviewer is
            asked for `{"done": bool, "notes": str}` -- which no line without it answers:
            such a turn is answered `{"done": true, "notes": "reviewed"}` otherwise.

        Lines add up over calls; a key said again replaces what it said before.
        """
        for key, line in lines.items():
            said: dict[str, Any]
            if isinstance(line, str):
                said = {"text": line}
            elif isinstance(line, Mapping):
                said = dict(line)
            else:
                said = {"text": list(line)}
            self._lines = [one for one in self._lines if one[0] != key] + [(key, said)]
        (self._bin / "lines.json").write_text(json.dumps(self._lines))

    # -- chats --------------------------------------------------------------------------

    def chat(self, *messages: str, going: bool = False) -> str:
        """Holds a chat in the project: each message said, and answered, in turn.

        The agent answers what `says` scripted. The chat is then in the sidebar, and its
        transcript at `/chats/<id>`::

            world.says({"coupon": "Added `coupon` to `charge()`; the tests pass."})
            chat = world.chat("Add a coupon code to checkout")
            with world.page() as page:
                go(page, f"/chats/{chat}")

        Args:
          messages: What the person says, one turn each.
          going: Whether its host is left running, as a chat somebody has open is: its
            environment -- Files, Changes, a terminal -- is there only while it is. A chat
            not left going rests, as one closed does.

        Returns:
          The chat's id.
        """
        assert messages, "a chat starts with a message"
        here = str(self.workspace)
        with self.session() as session:
            started = session.call(
                "chat.start",
                workspace=here,
                slot="chat:",
                agent=AGENT,
                task=messages[0],
                idem=uuid.uuid4().hex,
            )
            slot = started["slot"]
            sub = session.call("epic.attach", workspace=here, slot=slot)["sub"]
            for turn, message in enumerate(messages, 1):
                if turn > 1:
                    session.call("chat.say", workspace=here, slot=slot, text=message)
                self._until(
                    session, lambda turn=turn: _heard(session, sub, "asked") >= turn
                )
            session.call("epic.detach", sub=sub)
            chat = str(started["chat"])
            if not going:
                session.call(
                    "hosts.stop", workspace=here, slot=slot, idem=uuid.uuid4().hex
                )
                self._until(
                    session, lambda: not session.call("chat.get", chat=chat)["slot"]
                )
        return chat

    # -- epics --------------------------------------------------------------------------

    def epic(
        self,
        flow: str,
        task: str,
        *,
        agents: Mapping[str, str] | None = None,
        budget: Mapping[str, float] | None = None,
        until: str | None = "ended",
        failing: bool = False,
    ) -> str:
        """Starts a flow on a task in the project, as the page's New epic does.

        The flows installed are the stand-in loops: `goal` (one agent, `worker`, one turn),
        `rlar` (an `actor` and a `reviewer` taking turns until the reviewer is satisfied),
        `ralph_loop` and `stateful_ralph` (an `agent`, round after round until the budget is
        spent), and the project's own `@local/sign_off` (`World.asks`). The epic is then in
        the sidebar, at `/epics/<name>`, and its trace -- every turn and tool call on a
        timeline -- at `/epics/<name>/exomyth`::

            world.says({"coupon": {"text": "Added it.", "after": 1.5, "tools": [...]}})
            name = world.epic("goal", "Add a coupon code to checkout")

        Args:
          flow: The flow, as `-f` names it.
          task: What it is set to do.
          agents: What runs each of its roles, `{"worker": AGENT}`: the stand-in's
            `claude-haiku-4-5` for every role where not said.
          budget: What it may spend: five dollars where not said. `{"output_tokens": 600}`
            is what ends a loop that only its budget ends.
          until: What is waited for before answering: `"ended"`, the epic over; `"asked"`,
            a question put to its person, the epic waiting on it; or None, the epic just
            started and still running -- script its agent with an `after` to keep it so.
          failing: Whether the epic is meant to fail, as one whose agent is scripted to
            `fail` does: one that fails otherwise fails the scene, saying why.

        Returns:
          The epic's name.
        """
        here = str(self.workspace)
        with self.session() as session:
            sub = session.call("epic.attach", workspace=here)["sub"]
            roles = _roles(session, flow, here)
            session.call(
                "epic.start",
                sub=sub,
                flow=flow,
                task=task,
                budget=dict(budget or {"cost": 5}),
                agents=dict.fromkeys(roles, AGENT) | dict(agents or {}),
                idem=uuid.uuid4().hex,
            )
            self._until(session, lambda: _heard(session, sub, "started") >= 1)
            if until:
                self._until(session, lambda: _heard(session, sub, until) >= 1)
            failed = [
                said["message"].get("why")
                for method, said in session.told
                if _record(sub, "ended")(method, said)
                and said["message"].get("how") == "failed"
            ]
            assert not failed or failing, f"the epic failed: {failed}"
            # An epic that has only just started is not always listed yet: asked until it is.
            deadline = time.monotonic() + PATIENCE
            while True:
                listed = [
                    str(one["name"])
                    for one in session.call("runs.list", workspace=here)["runs"]
                    if one["task"] == task
                ]
                if listed:
                    name = listed[0]
                    break
                assert time.monotonic() < deadline, (
                    "the epic started and was never listed"
                )
                time.sleep(0.2)
            session.call("epic.detach", sub=sub)
        return name

    def asks(self, task: str, *, wrote: Mapping[str, str] | None = None) -> str:
        """Leaves a question waiting for the person: an epic of `sign_off`, at its form.

        The project's own flow `sign_off` has its agent do the task, then shows its person
        what the agent said and the diff of what it changed, and asks for a review -- a
        verdict of three, and notes -- as one form. Open it at `/epics/<name>`, where the
        question waits under the graph; the sidebar marks the epic as waiting too.

        Args:
          task: What the agent is set to do. Script what it answers with `says`.
          wrote: Files the agent is to have changed, `{"shop/checkout.py": "<the whole
            file>"}`, where `says` did not script it to write any: the diff the person is
            shown.

        Returns:
          The epic's name.
        """
        if wrote:
            self.changed(wrote)
        return self.epic("@local/sign_off", task, until="asked")

    def stop(self, name: str) -> None:
        """Stops an epic left running or waiting, as its Stop button does, until it ended."""
        here = str(self.workspace)
        with self.session() as session:
            epic = session.call("runs.get", name=name)
            sub = session.call(
                "epic.attach", workspace=here, slot=epic.get("slot", ""), replay=False
            )["sub"]
            session.call("epic.stop", sub=sub, idem=uuid.uuid4().hex)
            self._until(session, lambda: _heard(session, sub, "ended") >= 1)

    # -- settings -----------------------------------------------------------------------

    def account(
        self, name: str, *, cli: str = "claude", key: str = "not-a-real-key"
    ) -> None:
        """Adds an account of a coding agent, as the Accounts settings do: by an API key.

        It is then listed at `/settings/accounts`. The key is never shown, and is made up:
        give it no real one.

        Args:
          name: What the account is called: `work`, `personal`.
          cli: The coding agent it is an account of.
          key: What every secret the way asks for is answered with.
        """
        backends = self.call("accounts.list")["backends"]
        backend = next(one for one in backends if one["cli"] == cli)
        way = next(
            one for one in backend["ways"] if not one["terminal"] and one["asks"]
        )
        answers = {one["env"]: key for one in way["asks"] if not one["fixed"]}
        self.call(
            "accounts.create", cli=cli, name=name, way=way["name"], answers=answers
        )

    # -- the project --------------------------------------------------------------------

    def changed(self, files: Mapping[str, str | None]) -> None:
        """Changes files of the project without committing them: what Changes then shows.

        Args:
          files: Each path under the project and the whole of what it now holds, or None
            for a file deleted.
        """
        for name, content in files.items():
            at = self.workspace / name
            if content is None:
                at.unlink()
            else:
                at.parent.mkdir(parents=True, exist_ok=True)
                at.write_text(content)

    def committed(self, message: str, files: Mapping[str, str | None]) -> None:
        """Changes files of the project and commits them, as its person would have."""
        self.changed(files)
        _git(self.workspace, "add", "-A")
        _git(self.workspace, "commit", "-q", "-m", message)

    def _until(self, session: Session, ready: Callable[[], object]) -> None:
        deadline = time.monotonic() + PATIENCE
        while not ready():
            assert time.monotonic() < deadline, (
                f"the stand-in world never got there; the daemon said {session.told}"
            )
            with session.heard:
                session.heard.wait(0.1)


def _heard(session: Session, sub: str, kind: str) -> int:
    """How many records of a kind a subscription has been told."""
    wanted = _record(sub, kind)
    with session.heard:
        return sum(1 for method, said in session.told if wanted(method, said))


def _roles(session: Session, flow: str, workspace: str) -> list[str]:
    """The roles of a flow that an agent must be named for: every one but its people."""
    said = session.call("flows.get", name=flow, workspace=workspace)
    return [str(role["name"]) for role in said["agents"] if not role["auto"]]


@pytest.fixture
def world(
    _stage: _Stage,
    daemon: Private,
    asking: None,
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[World]:
    """The made-up world, staged: see this module's docstring, and `World`."""
    from hmz.coganchor import binary

    # Without it no agent is fenced, and every turn fails saying something else.
    assert binary.found() is not None, (
        "no coganchor is built for this checkout: run `cargo build` in crates/coganchor,"
        " or name a build of another checkout in HUMANIZE_COGANCHOR"
    )
    claude = _stage.bin / "claude"
    claude.write_text(f"#!{sys.executable}\n{_stand_in()}")
    claude.chmod(0o755)
    monkeypatch.setenv(
        "PATH",
        os.pathsep.join(
            (str(_stage.bin), str(Path(sys.executable).parent), "/usr/bin", "/bin")
        ),
    )
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(_stage.home / ".claude"))
    for name, content in _SHOP.items():
        at = _stage.workspace / name
        at.parent.mkdir(parents=True, exist_ok=True)
        at.write_text(content)
    flow = _stage.workspace / ".hmz" / "flows" / "sign_off"
    flow.mkdir(parents=True)
    (flow / "__init__.py").write_text(_SIGN_OFF)
    _git(_stage.workspace, "init", "-q", "-b", "main")
    _git(_stage.workspace, "add", "-A")
    _git(_stage.workspace, "commit", "-q", "-m", "Start the shop")
    monkeypatch.chdir(_stage.workspace)
    with served() as site:
        yield World(_stage.home, _stage.workspace, site, _stage.bin)
