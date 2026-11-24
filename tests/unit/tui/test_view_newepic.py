"""`hmz.tui.views.newepic`: the New epic page, against a daemon that is a table of answers."""

from __future__ import annotations

import asyncio
from typing import Any

from textual.app import App
from textual.widgets import OptionList

from hmz.tui import humanfia
from hmz.tui.views.newepic import VIEWS, Draft, NewEpic

#: The rows the tests read and write, as the page puts them up.
FLOW, TASK, COST, MINUTES = "\x1eflow", "\x1etask", "\x1ecost", "\x1eminutes"
CODER, LAB, ROUNDS = "\x1eagent\x1ecoder", "\x1eenv\x1elab", "\x1eparam\x1erounds"
MIRROR = "\x1ebackup\x1emirror"

REMEMBERED: dict[str, Any] = {
    "agents": {"coder": "claude/opus:high"},
    "envs": {},
    "params": {"rounds": 4},
    "budget": {"cost": 5, "duration": "PT30M", "graceful": {"cost": False}},
    "profile_flow": True,
    "profile_environment": False,
    "backup": None,
}

DECLARED: dict[str, Any] = {
    "name": "ship",
    "description": "Ships it.",
    "resumable": False,
    "agents": [
        {"name": "coder", "required": True, "auto": False, "clis": ["claude"]},
        {"name": "flow", "required": True, "auto": True, "clis": []},
    ],
    "envs": [
        {"name": "lab", "required": False, "auto": False},
        {"name": "workspace", "required": True, "auto": True},
    ],
    "params": {
        "type": "object",
        "properties": {
            "rounds": {"type": "integer", "default": 2, "title": "rounds"},
            "mode": {"enum": ["fast", "careful"], "default": "fast", "title": "mode"},
        },
    },
    "remembered": REMEMBERED,
}

ANSWERS: dict[str, Any] = {
    "flows.list": {
        "flows": [{"whose": "local", "name": "ship", "about": "Ships it."}],
        "flow": "ship",
        "running": [],
    },
    "flows.get": DECLARED,
    "flows.backends": {
        "clis": {
            "claude": {
                "accounts": [
                    {"name": "", "models": [{"name": "opus"}], "asked": "today"}
                ]
            }
        }
    },
    "runtimes.list": {"runtimes": [{"backend": "ssh", "name": "box"}]},
    "settings.get": {
        "backup": {"targets": [{"name": "mirror", "url": "git@x"}], "defaults": []}
    },
    "nous.list": {"nous": [{"name": "smart", "virtual": True}, {"name": "plain"}]},
    "flows.check": {},
}


class Daemon:
    """A daemon that answers from a table, and keeps what it was asked."""

    def __init__(self, **over: Any) -> None:
        self.answers = {**ANSWERS, **over}
        self.asked: list[tuple[str, dict[str, Any]]] = []

    def __call__(self, method: str, params: dict[str, Any], **_: Any) -> Any:
        self.asked.append((method, params))
        answer = self.answers[method]
        if isinstance(answer, Exception):
            raise answer
        return answer

    def of(self, method: str) -> list[dict[str, Any]]:
        return [params for asked, params in self.asked if asked == method]


class _Stands(App[None]):
    """An interface that is the page, and nothing under it."""

    def get_css_variables(self) -> dict[str, str]:
        return {**humanfia.FALLBACK, **super().get_css_variables()}


class Opened:
    """The page opened over a bare interface, with what it starts and what it keeps."""

    def __init__(self, daemon: Daemon, **given: Any) -> None:
        self.daemon = daemon
        self.started: list[tuple[str, dict[str, Any]]] = []
        self.kept: list[Draft | None] = []
        self.page = NewEpic(
            daemon, self._starts, folder="/work", keep=self.kept.append, **given
        )

    async def _starts(self, folder: str, start: dict[str, Any]) -> None:
        self.started.append((folder, start))

    async def ready(self, pilot: Any) -> NewEpic:
        await pilot.app.push_screen(self.page)
        for _ in range(200):
            await pilot.pause()
            if CODER in _rows(self.page):
                return self.page
            await asyncio.sleep(0.01)
        raise AssertionError("the page never read its flow")


def _rows(page: NewEpic) -> list[str]:
    listing = page.query_one("#choices", OptionList)
    return [str(one.id or "").removeprefix("=") for one in listing.options]


def _said(page: NewEpic) -> str:
    listing = page.query_one("#choices", OptionList)
    return "\n".join(str(one.prompt) for one in listing.options)


async def _settled(pilot: Any, ready: Any) -> None:
    for _ in range(200):
        await pilot.pause()
        if ready():
            return
        await asyncio.sleep(0.01)
    raise AssertionError("never settled")


def test_the_page_is_a_view_opened_over_the_screen_by_ctrl_e() -> None:
    (view,) = VIEWS

    assert (view.name, view.zone, view.key) == ("newepic", "page", "ctrl+e")
    assert (view.title, view.hint) == ("New epic", "New epic")


async def test_it_opens_holding_what_the_folder_last_set_the_flow_up_with() -> None:
    opened = Opened(Daemon())
    async with _Stands().run_test(size=(100, 40)) as pilot:
        page = await opened.ready(pilot)

        # One row per thing asked, in reading order, and none for what the flow fills itself.
        assert _rows(page)[:6] == [FLOW, "", "\x1efolder", LAB, TASK, ""]
        assert "\x1eagent\x1eflow" not in _rows(page)
        assert "\x1eenv\x1eworkspace" not in _rows(page)
        held = {one.held: page.shown(one) for one in page.asked()}
        assert held[FLOW] == "ship"
        assert held[CODER] == "claude/opus:high"
        assert held[LAB] == "Folder"
        assert held[ROUNDS] == "4"
        assert held["\x1eparam\x1emode"] == "fast"
        assert (held[COST], held[MINUTES]) == ("5", "30")
        assert held["\x1egrace-cost"] == "off"
        assert held["\x1egrace-time"] == "on"
        assert held["\x1eprofile-flow"] == "on"
        assert held[MIRROR] == "off"
        assert opened.daemon.of("flows.get") == [{"name": "ship", "workspace": "/work"}]
        said = _said(page)
        for heading in ("ENVIRONMENT", "AGENTS", "PARAMETERS", "BUDGET", "BACKUP"):
            assert heading in said


async def test_nothing_starts_on_half_an_answer_and_what_is_missing_is_on_its_row() -> (
    None
):
    opened = Opened(Daemon())
    async with _Stands().run_test(size=(100, 40)) as pilot:
        page = await opened.ready(pilot)

        await pilot.press("ctrl+s")
        await pilot.pause()

        assert page.under() == TASK
        assert "✗ Describe the task" in _said(page)
        assert not opened.daemon.of("flows.check")
        assert not opened.started


async def test_start_has_the_daemon_check_the_set_up_and_then_starts_it() -> None:
    opened = Opened(Daemon())
    app = _Stands()
    async with app.run_test(size=(100, 40)) as pilot:
        page = await opened.ready(pilot)
        assert page.under() == TASK

        await pilot.press(*"ship it", "enter")
        await pilot.press("ctrl+s")
        await _settled(pilot, lambda: bool(opened.started))

        ((folder, start),) = opened.started
        assert folder == "/work"
        assert start == {
            "flow": "ship",
            "task": "ship it",
            "agents": {"coder": "claude/opus:high"},
            "envs": {},
            "params": {"rounds": 4, "mode": "fast"},
            "budget": {
                "cost": 5,
                "duration": 1800,
                "graceful": {"cost": False, "duration": True, "output_tokens": True},
            },
            "profile_flow": True,
            "profile_environment": False,
            "backup": None,
            "resume": False,
        }
        (checked,) = opened.daemon.of("flows.check")
        assert checked == {
            "workspace": "/work",
            **{key: value for key, value in start.items() if key != "task"},
        }
        # Started, there is nothing left to keep, and the page is gone.
        await _settled(pilot, lambda: app.screen is not page)
        assert opened.kept == [None]


async def test_what_the_daemon_refuses_is_said_on_the_row_it_is_about() -> None:
    refusal = OSError("coder: claude runs no model called opus")
    opened = Opened(Daemon(**{"flows.check": refusal}))
    async with _Stands().run_test(size=(100, 40)) as pilot:
        page = await opened.ready(pilot)
        await pilot.press(*"ship it", "enter")

        await pilot.press("ctrl+s")
        await _settled(pilot, lambda: "runs no model" in _said(page))

        assert page.under() == CODER
        assert not opened.started

        # And one that names no row is said under the list, the cursor left where it was.
        page.refused("the daemon is busy")
        await pilot.pause()
        assert page.under() == CODER
        assert "runs no model" not in _said(page)
        assert "the daemon is busy" in str(page.query_one("#tuning").render())


async def test_a_budget_with_no_limit_is_refused_on_its_first_row() -> None:
    unbounded: dict[str, Any] = {**REMEMBERED, "budget": None}
    declared = {**DECLARED, "remembered": unbounded}
    opened = Opened(Daemon(**{"flows.get": declared}))
    async with _Stands().run_test(size=(100, 40)) as pilot:
        page = await opened.ready(pilot)
        await pilot.press(*"ship it", "enter")

        await pilot.press("ctrl+s")
        await pilot.pause()

        assert page.under() == COST
        assert "Set at least one limit of the budget." in _said(page)


async def test_a_role_drops_every_nous_and_model_that_can_fill_it() -> None:
    async def picks(kind: str, flow: str, role: str, now: str) -> str | None:
        return f"{kind}:{flow}:{role}:{now}"

    opened = Opened(Daemon(), picks=picks)
    async with _Stands().run_test(size=(100, 40)) as pilot:
        page = await opened.ready(pilot)

        agents = page.dropping(CODER)
        assert agents.current == "claude/opus:high"
        assert [(one.value, one.group) for one in agents.values] == [
            ("claude/opus:high", ""),
            ("smart", "Virtual"),
            ("claude/opus:auto", "claude"),
            ("\x1emore", ""),
        ]
        places = page.dropping(LAB)
        assert [one.value for one in places.values] == ["", "ssh@box", "\x1emore"]
        assert places.values[0].label == "Folder"

        # More options is the sheet `/flow` picks it on, and what it answers is held.
        page.dropped(CODER, "\x1emore")
        await _settled(
            pilot,
            lambda: (
                page.shown(next(one for one in page.asked() if one.held == CODER))
                == "agent:ship:coder:claude/opus:high"
            ),
        )


async def test_without_a_sheet_to_pick_on_the_lists_offer_what_they_offer() -> None:
    opened = Opened(Daemon())
    async with _Stands().run_test(size=(100, 40)) as pilot:
        page = await opened.ready(pilot)

        assert "\x1emore" not in [one.value for one in page.dropping(CODER).values]


async def test_left_without_starting_it_keeps_what_was_written_and_opens_on_it() -> (
    None
):
    opened = Opened(Daemon())
    app = _Stands()
    async with app.run_test(size=(100, 40)) as pilot:
        page = await opened.ready(pilot)
        await pilot.press(*"half a thought", "enter")

        await pilot.press("escape")
        await _settled(pilot, lambda: app.screen is not page)

        (draft,) = opened.kept
        assert draft is not None
        assert draft.flow == "ship"
        assert draft.typed[TASK] == "half a thought"

        again = Opened(Daemon(), draft=draft)
        page = await again.ready(pilot)
        task = next(one for one in page.asked() if one.held == TASK)
        assert page.shown(task) == "half a thought"


async def test_with_no_flow_installed_it_says_so_and_starts_nothing() -> None:
    daemon = Daemon(**{"flows.list": {"flows": [], "flow": "", "running": []}})
    opened = Opened(daemon)
    async with _Stands().run_test(size=(100, 40)) as pilot:
        await pilot.app.push_screen(opened.page)
        page = opened.page
        await _settled(
            pilot,
            lambda: "No flow installed yet." in str(page.query_one("#tuning").render()),
        )

        await pilot.press("ctrl+s")
        await pilot.pause()

        assert "Install a flow first, from Flows." in _said(page)
        assert not opened.started
