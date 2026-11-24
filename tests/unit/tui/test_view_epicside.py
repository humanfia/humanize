"""`hmz.tui.views.epicside`: the epic's four tabs, against runs and a daemon that are tables."""

from __future__ import annotations

import asyncio
from typing import Any

from textual.app import App, ComposeResult
from textual.widgets import OptionList, Static

from hmz.tui import humanfia
from hmz.tui.monitoring import BoardSeen, Entry
from hmz.tui.shell import Hints
from hmz.tui.views.epicside import TABS, VIEWS, Epic, Kept, People, Side

DETAILS = [
    ("Figures", [("time", "3s elapsed"), ("spent", "$0.10")]),
    (
        "Set up",
        [("flow", "ship"), ("task", "ship it"), ("agents", "coder=claude/opus")],
    ),
]


class World:
    """An epic that is tables: what is read of it, and everything it was asked."""

    def __init__(self) -> None:
        self.details: list[Any] = list(DETAILS)
        self.lines: list[dict[str, Any]] | None = [
            {"key": "plan", "value": "ship it", "by": "you"},
            {"key": "round", "value": "2", "whose": "flow"},
        ]
        self.people = People(
            ["reviewer", "owner"], {"owner": "c2"}, "c1", {"c2": "web"}, away=False
        )
        self.sessions = ["Ada/1", "Ada/2"]
        self.asides: list[dict[str, Any]] = []
        self.asked: list[tuple[str, dict[str, Any]]] = []
        self.boarded: list[tuple[str, str]] = []
        self.called: list[tuple[str, dict[str, Any]]] = []

    def _board(self) -> BoardSeen | None:
        if self.lines is None:
            return None
        return BoardSeen(
            self.lines, lambda key, value: self.boarded.append((key, value))
        )

    def _asks(self, do: str, **said: Any) -> None:
        self.asked.append((do, said))

    def _daemon(self, method: str, params: Any) -> Any:
        self.called.append((method, dict(params)))
        if method == "btw.ask":
            said = {"question": params["question"], "answer": "It is going well."}
            self.asides.append(
                {"aside": params["aside"], "to": params["to"], "said": [said]}
            )
            return said
        if method == "btw.leave":
            self.asides = [
                one for one in self.asides if one["aside"] != params["aside"]
            ]
            return {}
        return {"asides": list(self.asides)}

    def epic(self) -> Epic:
        return Epic(
            details=lambda: self.details,
            state=lambda: "running",
            named=lambda: "20260101-ship",
            board=self._board,
            people=lambda: self.people,
            sessions=lambda: self.sessions,
            asks=self._asks,
            daemon=self._daemon,
            workspace=lambda: "/work",
        )


class _Stands(App[None]):
    """An interface that is the view and the hint line."""

    def __init__(self, side: Side) -> None:
        super().__init__()
        self._side = side

    def get_css_variables(self) -> dict[str, str]:
        return {**humanfia.FALLBACK, **super().get_css_variables()}

    def compose(self) -> ComposeResult:
        yield self._side
        yield Hints(id="hints")

    def on_mount(self) -> None:
        self._side.focus()


def _said(side: Side) -> str:
    listing = side.query_one(OptionList)
    return "\n".join(str(one.prompt) for one in listing.options)


def _hinted(app: App[None]) -> str:
    return str(app.query_one(Hints).render())


async def _settled(pilot: Any, ready: Any) -> None:
    for _ in range(300):
        await pilot.pause()
        if ready():
            return
        await asyncio.sleep(0.01)
    raise AssertionError("never settled")


def test_the_view_opens_in_the_context_by_ctrl_o() -> None:
    (view,) = VIEWS

    assert (view.name, view.zone, view.key) == ("epic", "context", "ctrl+o")
    assert (view.title, view.hint) == ("Epic", "epic panel")
    assert TABS == ("Details", "Board", "People", "Side questions")


async def test_details_say_how_the_epic_stands_under_the_pages_headings() -> None:
    side = Side(World().epic())
    app = _Stands(side)
    async with app.run_test(size=(60, 30)) as pilot:
        await pilot.pause()

        said = _said(side)
        assert "Running" in said
        assert "20260101-ship" in said
        assert "FIGURES" in said
        assert "SETUP" in said
        assert "ship it" in said
        assert "1\xa0DETAILS" in str(side.query_one("_Tabs", Static).render())
        await _settled(pilot, lambda: "←/→ tab" in _hinted(app))
        assert "esc Back" in _hinted(app)


async def test_with_no_epic_open_every_tab_says_so() -> None:
    world = World()
    world.details = []
    side = Side(world.epic())
    async with _Stands(side).run_test(size=(60, 30)) as pilot:
        for key in ("1", "2", "3", "4"):
            await pilot.press(key)
            await pilot.pause()
            assert "No epic is going here." in _said(side)


async def test_the_arrows_and_the_digits_turn_the_tabs_round_the_ends() -> None:
    side = Side(World().epic())
    async with _Stands(side).run_test(size=(60, 30)) as pilot:
        await pilot.press("right")
        assert side.tab == 1
        await pilot.press("left", "left")
        assert side.tab == 3
        await pilot.press("3")
        assert side.tab == 2
        await pilot.press("right", "right")
        assert side.tab == 0


async def test_left_and_come_back_to_it_is_on_the_tab_and_the_row_it_was_left_on() -> (
    None
):
    world, kept = World(), Kept()
    side = Side(world.epic(), kept)
    async with _Stands(side).run_test(size=(60, 30)) as pilot:
        await pilot.press("3", "down")
        await pilot.pause()
        assert (kept.tab, kept.cursors[2]) == (2, "owner")

        # Turned away from and back to, a tab is on the row it was left on too.
        await pilot.press("1", "3")
        await pilot.pause()
        assert side.query_one(OptionList).highlighted == 1
        assert kept.cursors[2] == "owner"

    again = Side(world.epic(), kept)
    app = _Stands(again)
    async with app.run_test(size=(60, 30)) as pilot:
        await pilot.pause()

        assert again.tab == 2
        assert again.query_one(OptionList).highlighted == 1
        await _settled(pilot, lambda: "enter Take over" in _hinted(app))


async def test_people_are_claimed_released_taken_over_and_set_away() -> None:
    world = World()
    side = Side(world.epic())
    app = _Stands(side)
    async with app.run_test(size=(60, 30)) as pilot:
        await pilot.press("3")
        await _settled(pilot, lambda: "enter Claim" in _hinted(app))
        said = _said(side)
        assert "reviewer" in said
        assert "Anyone" in said
        assert "web" in said
        assert "shift+W Away for all" in _hinted(app)

        await pilot.press("enter")
        assert world.asked[-1] == ("claim", {"role": "reviewer", "take": False})

        world.people = world.people._replace(claims={"reviewer": "c1", "owner": "c2"})
        await _settled(pilot, lambda: "enter Release" in _hinted(app))
        assert "You" in _said(side)
        await pilot.press("enter")
        assert world.asked[-1] == ("release", {"role": "reviewer"})

        await pilot.press("down", "enter")
        assert world.asked[-1] == ("claim", {"role": "owner", "take": True})

        await pilot.press("w")
        assert world.asked[-1] == ("afk", {"on": True, "role": "owner"})
        await pilot.press("W")
        assert world.asked[-1] == ("afk", {"on": True})

        world.people = world.people._replace(away=True)
        await _settled(pilot, lambda: "shift+W Back for all" in _hinted(app))
        assert "Away" in _said(side)
        await pilot.press("W")
        assert world.asked[-1] == ("afk", {"on": False})


async def test_a_line_of_the_board_is_added_changed_and_removed_once_asked() -> None:
    world = World()
    side = Side(world.epic())
    app = _Stands(side)
    async with app.run_test(size=(80, 30)) as pilot:
        await pilot.press("2")
        await _settled(pilot, lambda: "enter Edit" in _hinted(app))
        assert "plan" in _said(side)
        assert "A Add" in _hinted(app)
        assert "D Remove" in _hinted(app)

        await pilot.press("a")
        await _settled(pilot, lambda: isinstance(app.screen, Entry))
        await pilot.press(*"next", "enter", *"tests", "enter")
        await _settled(pilot, lambda: bool(world.boarded))
        assert world.boarded == [("next", "tests")]

        await pilot.press("enter")
        await _settled(pilot, lambda: isinstance(app.screen, Entry))
        await pilot.press("!", "enter")
        await _settled(pilot, lambda: len(world.boarded) == 2)
        assert world.boarded[-1] == ("plan", "ship it!")

        # Removing asks first, and nothing goes on a no.
        await pilot.press("d")
        await _settled(pilot, lambda: len(app.screen_stack) == 2)
        assert "Remove plan?" in str(app.screen.query_one("#asked").render())
        await pilot.press("escape")
        await _settled(pilot, lambda: len(app.screen_stack) == 1)
        assert len(world.boarded) == 2
        await pilot.press("d")
        await _settled(pilot, lambda: len(app.screen_stack) == 2)
        await pilot.click("#act-yes")
        await _settled(pilot, lambda: len(world.boarded) == 3)
        assert world.boarded[-1] == ("plan", "")

        # A line the flow owns is the flow's to change.
        await pilot.press("down", "d")
        await pilot.pause()
        assert len(app.screen_stack) == 1
        assert "Only the flow changes this line" in str(
            side.query_one(".side-note", Static).render()
        )
        assert len(world.boarded) == 3


async def test_a_flow_that_keeps_no_board_says_so_and_takes_no_key_for_one() -> None:
    world = World()
    world.lines = None
    side = Side(world.epic())
    app = _Stands(side)
    async with app.run_test(size=(60, 30)) as pilot:
        await pilot.press("2")
        await pilot.pause()

        assert "This flow keeps no board." in _said(side)
        await pilot.press("a")
        await pilot.pause()
        assert len(app.screen_stack) == 1


async def test_a_side_question_is_asked_of_a_session_and_closed_once_asked() -> None:
    world = World()
    side = Side(world.epic())
    app = _Stands(side)
    async with app.run_test(size=(80, 30)) as pilot:
        await pilot.press("4")
        await _settled(pilot, lambda: "A New aside" in _hinted(app))
        assert "No side question yet" in _said(side)
        listed = ("btw.list", {"workspace": "/work", "epic": "20260101-ship"})
        await _settled(pilot, lambda: listed in world.called)

        # Whom to ask, picked from the list dropped under its row, then the question.
        await pilot.press("a")
        await _settled(pilot, lambda: len(app.screen_stack) == 2)
        await pilot.press("enter")
        await _settled(pilot, lambda: len(app.screen_stack) == 3)
        await pilot.press("enter")
        await _settled(pilot, lambda: len(app.screen_stack) == 2)
        await pilot.press(*"how is it going?", "enter", "enter")
        await _settled(pilot, lambda: "It is going well." in _said(side))

        (asked,) = [params for method, params in world.called if method == "btw.ask"]
        assert asked["to"] == "Ada/2"
        assert asked["question"] == "how is it going?"
        assert asked["workspace"] == "/work"
        assert asked["aside"].startswith("tui-")
        assert "btw · Ada/2" in _said(side)
        await _settled(pilot, lambda: "enter Ask" in _hinted(app))
        assert "D Close" in _hinted(app)

        await pilot.press("d")
        await _settled(pilot, lambda: len(app.screen_stack) == 2)
        await pilot.click("#act-yes")
        await _settled(
            pilot, lambda: any(method == "btw.leave" for method, _ in world.called)
        )
        await _settled(pilot, lambda: "No side question yet" in _said(side))


async def test_with_no_session_open_there_is_nobody_to_ask() -> None:
    world = World()
    world.sessions = []
    side = Side(world.epic())
    app = _Stands(side)
    async with app.run_test(size=(80, 30)) as pilot:
        await pilot.press("4")
        await pilot.pause()

        assert "No harness session is open in this epic yet." in _said(side)
        await pilot.press("a")
        await pilot.pause()
        assert len(app.screen_stack) == 1
