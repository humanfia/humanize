"""`/ai`: Ai-chan's conversations, made, followed as a chat, carried on and forgotten.

`aichan.*` is answered here by a daemon of the test's own, which makes a conversation as the
daemon does -- a host of its own slot, `ai:<hex>`, its task the first message -- but runs a
flow of the stand-in talking to the person on that host in place of the flow `ai_chan`: what is
under test is the interface, which reads her conversation as it reads any chat.
"""

from __future__ import annotations

import itertools
import threading
import uuid
from typing import TYPE_CHECKING, Any

import pytest

from hmz import daemon as daemons
from hmz.rpc import Code, RpcError
from hmz.runtime.settings import Settings
from hmz.tui import Humanize
from hmz.tui.pick import Acts, AiChanNew, AiChans, AiForgets
from tests.integration.doubles_tui import (
    RUNS,
    SIZE,
    TALKS,
    heard,
    on,
    onto,
    opened,
    picks,
    screen,
    shows,
    stand_in,
    typed,
    until,
)

if TYPE_CHECKING:
    from pathlib import Path

    from textual.pilot import Pilot

    from hmz.daemon.private import Private
    from hmz.rpc import Call


class _Conversations:
    """`aichan.list`, `aichan.create` and `aichan.forget`, as a daemon answers them."""

    def __init__(self, scratch: Path) -> None:
        self.held: list[dict[str, Any]] = []
        self.made: list[dict[str, Any]] = []
        self._scratch = scratch
        self._ids = itertools.count(1)
        self._lock = threading.Lock()

    def serves(self, served: Private) -> None:
        """Answers the three methods on the test's daemon."""
        served.dispatcher.register("aichan.list", self.listed)
        served.dispatcher.register("aichan.create", self.create)
        served.dispatcher.register("aichan.forget", self.forget)

    def listed(self, call: Call) -> dict[str, Any]:
        del call
        with self._lock:
            return {"conversations": [dict(one) for one in self.held]}

    def create(self, call: Call) -> dict[str, Any]:
        said = {key: value for key, value in call.params.items() if key != "idem"}
        self.made.append(said)
        # A scope of the whole daemon is held in a workspace of its own.
        workspace = str(said.get("workspace") or self._scratch)
        slot = f"ai:{uuid.uuid4().hex[:12]}"
        with daemons.attach("sdk", workspace=workspace, slot=slot) as link:
            link.start(
                TALKS,
                said["task"],
                agents={"assistant": RUNS},
                budget={"cost": 100.0},
            )
        one = {
            "id": next(self._ids),
            "title": said["task"][:80],
            "scope": said["scope"],
            "workspace": workspace,
            "epic": said.get("epic", ""),
            "nous": said["nous"],
            "preset": said["preset"],
            "network": said["network"],
            "slot": slot,
            "state": "waiting",
            "created": "2026-11-17T00:00:00Z",
        }
        with self._lock:
            self.held.insert(0, one)
        return {"id": one["id"], "workspace": workspace, "slot": slot}

    def forget(self, call: Call) -> dict[str, Any]:
        number = call.params["id"]
        with self._lock:
            if not any(one["id"] == number for one in self.held):
                raise RpcError(Code.NOT_FOUND, f"There is no Ai-chan #{number}.")
            self.held = [one for one in self.held if one["id"] != number]
        return {}


@pytest.fixture
def workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, asking: None) -> Path:
    """The stand-in `claude` on `PATH`, and the `ai_chan` setting naming it."""
    del asking
    here = stand_in(tmp_path, monkeypatch)
    Settings().ai_chan = RUNS
    return here


@pytest.fixture
def conversations(daemon: Private, tmp_path: Path) -> _Conversations:
    """Ai-chan's conversations, as the test's daemon answers for them."""
    scratch = tmp_path / "ai"
    scratch.mkdir()
    held = _Conversations(scratch)
    held.serves(daemon)
    return held


async def _new(pilot: Pilot[None]) -> AiChanNew:
    """Opens `/ai` and its New form."""
    await typed(pilot, "/ai")
    await on(pilot, AiChans)
    await shows(pilot, "New")
    await onto(pilot, "new")
    await pilot.press("enter")
    return await on(pilot, AiChanNew)


async def _done(pilot: Pilot[None]) -> None:
    """Answers the form on the screen, leaving the log screen waiting on the conversation."""
    app = pilot.app
    await pilot.click("#act-done")
    await until(pilot, lambda: len(app.screen_stack) == 1, "the log screen")


async def test_new_asks_the_scope_nous_and_permission_and_the_first_line_makes_it(
    workspace: Path, conversations: _Conversations
) -> None:
    app = Humanize()
    async with app.run_test(size=SIZE) as pilot:
        await opened(pilot)
        await _new(pilot)
        # Nothing has been run here, so the scope is this directory; the nous the setting.
        await shows(pilot, "scope", "workspace", "nous", RUNS, "read-only", "off")
        await _done(pilot)
        await shows(pilot, "Ai-chan · new · workspace", "Ai-chan: the next line")
        assert conversations.made == []

        await typed(pilot, "hello there")

        await shows(pilot, "heard hello there", "Ai-chan#1 · workspace")
        await typed(pilot, "go on")
        await shows(pilot, "heard go on", "◉ done")

    (made,) = conversations.made
    assert made == {
        "scope": "workspace",
        "workspace": str(app.hmz.workspace),
        "nous": RUNS,
        "preset": "read-only",
        "network": False,
        "task": "hello there",
    }
    assert heard(workspace) == ["hello there", "go on"]


async def test_the_scope_defaults_to_the_epic_last_on_the_host_and_takes_the_daemon(
    workspace: Path, conversations: _Conversations
) -> None:
    app = Humanize()
    async with app.run_test(size=SIZE) as pilot:
        await opened(pilot)
        await typed(pilot, "hello")
        await shows(pilot, "heard hello")

        form = await _new(pilot)
        # The chat just had is the epic last on the host followed.
        assert form.shown(form.asked()[0]) == "epic"
        await shows(pilot, "the epic ")
        await picks(pilot, "scope", "daemon")
        await picks(pilot, "preset", "danger-full-access")
        await picks(pilot, "network", "on")
        await shows(pilot, "every workspace and epic of this daemon")
        await _done(pilot)
        await typed(pilot, "look around")
        await shows(pilot, "heard look around", "Ai-chan#1 · daemon")

    (made,) = conversations.made
    assert made == {
        "scope": "daemon",
        "nous": RUNS,
        "preset": "danger-full-access",
        "network": True,
        "task": "look around",
    }


async def test_her_tools_are_shown_and_btw_and_stop_are_hers(
    workspace: Path, conversations: _Conversations
) -> None:
    del conversations
    app = Humanize()
    async with app.run_test(size=SIZE) as pilot:
        await opened(pilot)
        await _new(pilot)
        await _done(pilot)
        # Details are off, and every tool she calls is still shown.
        await typed(pilot, "tools")
        await shows(pilot, "Bash(foo\\ bar)", "heard tools", "◉ done")

        await typed(pilot, "/btw what is she doing")
        await shows(pilot, "not on Ai-chan's", "/ai asks Ai-chan")
        await typed(pilot, "/stop")
        await shows(pilot, "Ai-chan is not answering, so there is nothing to stop")

        # And /clear leaves her to her host, for this directory's own.
        await typed(pilot, "/clear")
        await until(pilot, lambda: "Ai-chan#1" not in screen(app), "her to be left")


async def test_a_conversation_is_carried_on_from_the_list_and_forgotten_there(
    workspace: Path, conversations: _Conversations
) -> None:
    app = Humanize()
    async with app.run_test(size=SIZE) as pilot:
        await opened(pilot)
        await _new(pilot)
        await _done(pilot)
        await typed(pilot, "hello there")
        await shows(pilot, "heard hello there")
        await typed(pilot, "/clear")
        await until(pilot, lambda: "Ai-chan#1" not in screen(app), "her to be left")

        await typed(pilot, "/ai")
        await on(pilot, AiChans)
        await shows(pilot, "Ai-chan#1 · hello there", "between turns")
        await onto(pilot, "1")
        await pilot.press("enter")
        await shows(pilot, "heard hello there", "Ai-chan#1 · workspace")
        await typed(pilot, "and again")
        await shows(pilot, "heard and again")

        await typed(pilot, "/ai")
        await on(pilot, AiChans)
        await onto(pilot, "1")
        await pilot.press("m")
        await on(pilot, Acts)
        await pilot.press("enter")
        await on(pilot, AiForgets)
        await shows(pilot, "Forget Ai-chan#1?")
        await pilot.press("enter")
        await on(pilot, AiChans)
        await shows(pilot, "no conversation yet")
    assert conversations.held == []
    assert heard(workspace)[-1] == "and again"
