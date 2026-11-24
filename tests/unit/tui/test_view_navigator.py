"""`hmz.tui.views.navigator`: every chat and epic beside the log, what waits on you first."""

from __future__ import annotations

import datetime
import json
from functools import partial
from typing import TYPE_CHECKING, Any

from textual.app import App, ComposeResult
from textual.widgets import Input, OptionList

from hmz.tui import humanfia
from hmz.tui.pick import Acts
from hmz.tui.shell import Hints, Shell, Zone
from hmz.tui.views import navigator
from hmz.tui.views.navigator import Kept, Navigator

if TYPE_CHECKING:
    from pathlib import Path

    import pytest
    from textual.pilot import Pilot

VIEW = navigator.VIEWS[0]


def _ago(minutes: float) -> str:
    at = datetime.datetime.now(datetime.UTC) - datetime.timedelta(minutes=minutes)
    return at.isoformat()


class Daemon:
    """A daemon that answers what a test gave it, and keeps what it was asked."""

    def __init__(self, here: str) -> None:
        self.here = here
        self.chats: list[dict[str, Any]] = [
            self.chat("c-old", "an old chat", 90),
            self.chat("c-new", "a new chat", 5),
            self.chat("c-asks", "which colour", 30, state="asking"),
            self.chat("c-far", "a chat elsewhere", 60, workspace="/far/other"),
        ]
        self.runs: list[dict[str, Any]] = [
            {
                "name": "e-done",
                "workspace": here,
                "flow": "@local/writes",
                "task": "write the docs",
                "began": _ago(200),
                "ended": _ago(190),
                "how": "done",
                "held": False,
                "slot": "",
                "asking": [],
            },
            {
                "name": "e-runs",
                "workspace": here,
                "flow": "@local/writes",
                "task": "fix the build",
                "began": _ago(2),
                "ended": "",
                "how": "running",
                "held": True,
                "slot": "",
                "asking": [],
            },
        ]
        self.asked: list[tuple[str, dict[str, Any]]] = []

    def chat(
        self, name: str, title: str, minutes: float, *, state: str = "resting",
        workspace: str = "",
    ) -> dict[str, Any]:  # fmt: skip
        return {
            "id": name,
            "title": title,
            "workspace": workspace or self.here,
            "folderless": False,
            "began": _ago(minutes + 1),
            "updated": _ago(minutes),
            "state": state,
            "slot": "",
        }

    def __call__(self, method: str, **params: Any) -> dict[str, Any]:
        self.asked.append((method, params))
        if method == "chat.list":
            return {"chats": list(self.chats), "total": len(self.chats)}
        if method == "runs.list":
            return {"runs": list(self.runs), "total": len(self.runs)}
        if method == "workspaces.list":
            return {
                "workspaces": [
                    {"path": self.here, "there": True, "chats": 3, "epics": 2},
                    {"path": "/far/other", "there": False, "chats": 1, "epics": 0},
                    {"path": "/far/empty", "there": True, "chats": 0, "epics": 0},
                ]
            }
        if method == "chat.archive":
            self.chats = [one for one in self.chats if one["id"] != params["chat"]]
        return {}


class _Stands(App[None]):
    """An interface that is the zones and a prompt, and keeps what a view asked of it."""

    def __init__(self) -> None:
        super().__init__()
        self.shell = Shell(self)
        self.opened: list[tuple[Any, ...]] = []
        self.shown: list[str] = []
        self.did: list[str] = []
        self.on_log = ""

    def get_css_variables(self) -> dict[str, str]:
        return {**humanfia.FALLBACK, **super().get_css_variables()}

    def compose(self) -> ComposeResult:
        yield Zone(id="navigator")
        yield Input(id="editor")
        yield Zone(id="context")
        yield Hints(id="hints")

    def on_mount(self) -> None:
        for zone in self.query(Zone):
            zone.told = self.shell.hints

    def opens_chat(self, chat: str, slot: str | None = None) -> None:
        self.opened.append(("chat", chat, slot))

    def opens_epic(
        self, epic: str, slot: str | None = None, *, here: bool = True
    ) -> None:
        self.opened.append(("epic", epic, slot, here))

    def showing(self) -> str:
        return self.on_log

    def show(self, text: str, style: str = "") -> None:
        del style
        self.shown.append(text)

    def copied(self, text: str) -> None:
        self.did.append(f"copied {text}")

    def action_chat(self) -> None:
        self.did.append("chat")

    def action_flow(self) -> None:
        self.did.append("flow")


def _ids(listing: Navigator) -> list[str]:
    return [str(one.id) for one in listing.query_one(OptionList).options]


def _drawn(listing: Navigator) -> list[str]:
    return [str(one.prompt) for one in listing.query_one(OptionList).options]


async def _until(
    pilot: Pilot[None], listing: Navigator, row: str, *, there: bool
) -> None:
    for _ in range(300):
        await pilot.pause(0.01)
        if (row in _ids(listing)) is there:
            return
    raise AssertionError(f"gave up waiting on {row}")


async def _opened(
    pilot: Pilot[None], daemon: Daemon, kept: Kept, *, keys: bool = True
) -> Navigator:
    """Opens the navigator in its zone, and waits until it has listed what there is."""
    listing = Navigator(daemon, kept)
    await pilot.app.query_one("#navigator", Zone).shows(VIEW, listing, keys=keys)
    await _until(pilot, listing, "r:c-new", there=True)
    return listing


async def _onto(pilot: Pilot[None], listing: Navigator, row: str) -> None:
    await pilot.press("home")
    for _ in range(len(_ids(listing))):
        if listing.under() == row:
            return
        await pilot.press("down")
    raise AssertionError(f"{row} is not listed")


def test_what_is_kept_is_read_back_and_anything_else_is_the_default(
    tmp_path: Path,
) -> None:
    at = tmp_path / "state" / "navigator.json"
    kept = Kept(at)
    assert kept.group == "folder"

    kept.group = "date"
    kept.marks("pinned", "one", on=True)
    kept.marks("pinned", "two", on=True)
    kept.marks("pinned", "one", on=False)

    again = Kept(at)
    assert again.group == "date"
    assert again.all("pinned") == {"two"}
    assert not again.has("unread", "two")
    at.write_text(json.dumps({"group": "sideways", "pinned": "no"}))
    assert Kept(at).group == "folder"
    assert Kept(at).all("pinned") == frozenset()


async def test_what_waits_on_you_is_first_then_the_folders_in_the_pages_words(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    here = str(tmp_path)
    async with _Stands().run_test(size=(120, 30)) as pilot:
        listing = await _opened(pilot, Daemon(here), Kept(tmp_path / "kept.json"))

        assert _ids(listing) == [
            "g::waiting",
            "r:c-asks",
            f"g:{here}",
            "r:e-runs",
            "r:c-new",
            "r:c-old",
            "r:e-done",
            "g:/far/other",
            "r:c-far",
            "g:/far/empty",
        ]
        waiting, asks, _, runs, new, *_ = _drawn(listing)
        assert "WAITING FOR YOU" in waiting
        assert asks.rstrip().endswith("Awaiting input")
        assert runs.rstrip().endswith("Running")
        assert new.rstrip().endswith("5m ago")
        # A folder whose directory is gone keeps its rows, and says so.
        assert "OTHER missing" in _drawn(listing)[7]
        # The keys are the view's own, on the hint line, with the way back.
        hints = str(pilot.app.query_one(Hints).render())
        assert hints.startswith("↑↓ Move   enter Open   N New chat   shift+N New epic")
        assert "esc Back" in hints


async def test_enter_opens_a_chat_and_an_epic_and_says_of_one_elsewhere(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    app = _Stands()
    async with app.run_test(size=(120, 30)) as pilot:
        kept = Kept(tmp_path / "kept.json")
        kept.marks("unread", "c-new", on=True)
        listing = await _opened(pilot, Daemon(str(tmp_path)), kept)

        await _onto(pilot, listing, "r:c-new")
        await pilot.press("enter")
        await pilot.pause()
        assert app.opened == [("chat", "c-new", None)]
        # Opened, it is read, and the prompt has the keys to go on in it.
        assert not kept.has("unread", "c-new")
        assert isinstance(app.focused, Input)

        listing.focus()
        await _onto(pilot, listing, "r:e-runs")
        await pilot.press("enter")
        await pilot.pause()
        listing.focus()
        await _onto(pilot, listing, "r:e-done")
        await pilot.press("enter")
        await pilot.pause()
        # One a host of this directory goes with is on the log; one ended is gone into.
        assert app.opened[1:] == [
            ("epic", "e-runs", "", True),
            ("epic", "e-done", None, True),
        ]

        listing.focus()
        await _onto(pilot, listing, "r:c-far")
        await pilot.press("enter")
        await pilot.pause()
        assert app.shown == [
            "This is in the folder other. Run `hmz` in that folder to open it."
        ]
        assert len(app.opened) == 3


async def test_a_row_is_pinned_marked_unread_and_the_grouping_stepped_and_kept(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    at = tmp_path / "kept.json"
    async with _Stands().run_test(size=(120, 30)) as pilot:
        listing = await _opened(pilot, Daemon(str(tmp_path)), Kept(at))
        await _onto(pilot, listing, "r:c-old")

        await pilot.press("p")
        assert _ids(listing)[2:4] == ["g::pinned", "r:c-old"]
        # The cursor went with the row.
        assert listing.under() == "r:c-old"

        await pilot.press("u")
        assert Kept(at).all("unread") == {"c-old"}
        await pilot.press("down")
        assert "●" in _drawn(listing)[3]

        await pilot.press("g")
        assert Kept(at).group == "date"
        assert "g::date:today" in _ids(listing)
        assert _ids(listing)[-4:] == [
            "g::folders",
            f"f:{tmp_path}",
            "f:/far/other",
            "f:/far/empty",
        ]
        await pilot.press("g")
        assert "g::all" in _ids(listing)
        await pilot.press("g")
        assert Kept(at).group == "folder"
        assert Kept(at).all("pinned") == {"c-old"}


async def test_the_list_does_not_reorder_under_the_keys_and_settles_once_they_leave(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    daemon = Daemon(str(tmp_path))
    app = _Stands()
    async with app.run_test(size=(120, 30)) as pilot:
        listing = await _opened(pilot, daemon, Kept(tmp_path / "kept.json"))
        await _onto(pilot, listing, "r:c-old")
        before = _ids(listing)

        # The daemon says another chat waits now, and a new one has begun.
        daemon.chats[0]["state"] = "asking"
        daemon.chats.append(daemon.chat("c-newest", "the newest", 0))
        listing.reads()
        await _until(pilot, listing, "r:c-newest", there=True)

        held = _ids(listing)
        assert [one for one in held if one != "r:c-newest"] == before
        assert listing.under() == "r:c-old"
        # What changed is drawn where the row stands.
        await pilot.press("up")
        assert (
            _drawn(listing)[held.index("r:c-old")].rstrip().endswith("Awaiting input")
        )

        await pilot.press("escape")
        await pilot.pause()
        await pilot.pause()
        assert isinstance(app.focused, Input)
        assert _ids(listing)[:3] == ["g::waiting", "r:c-asks", "r:c-old"]


async def test_the_menu_of_a_row_offers_the_pages_actions_and_does_the_one_taken(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    daemon = Daemon(str(tmp_path))
    app = _Stands()
    async with app.run_test(size=(120, 30)) as pilot:
        listing = await _opened(pilot, daemon, Kept(tmp_path / "kept.json"))
        await _onto(pilot, listing, "r:c-old")

        await pilot.press("full_stop")
        await pilot.pause()
        assert isinstance(app.screen, Acts)
        offered = [
            str(one.id).removeprefix("=")
            for one in app.screen.query_one("#choices", OptionList).options
        ]
        assert offered == [
            "open", "pin", "unread", "rename", "fork", "copy", "upload", "archive",
            "delete",
        ]  # fmt: skip
        app.screen.dismiss("archive")
        await _until(pilot, listing, "r:c-old", there=False)

        assert ("chat.archive", {"chat": "c-old"}) in daemon.asked


async def test_new_chat_and_new_epic_fall_back_to_what_the_prompt_has_for_them(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(navigator, "views", lambda: {"navigator": VIEW})
    app = _Stands()
    async with app.run_test(size=(120, 30)) as pilot:
        await _opened(pilot, Daemon(str(tmp_path)), Kept(tmp_path / "kept.json"))

        await pilot.press("N")
        await pilot.press("n")
        await pilot.pause()

        assert app.did == ["flow", "chat"]
        assert isinstance(app.focused, Input)


async def test_opened_with_the_interface_it_stays_closed_on_a_narrow_terminal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    daemon = Daemon(str(tmp_path))
    async with _Stands().run_test(size=(100, 30)) as pilot:
        zone = pilot.app.query_one("#navigator", Zone)
        made = Navigator(daemon, Kept(tmp_path / "kept.json"), starting=True)
        # As the interface opens it: from its own loop, the keys left with the prompt.
        pilot.app.call_later(partial(zone.shows, VIEW, made, keys=False))
        await pilot.pause()
        for _ in range(100):
            await pilot.pause(0.01)
            if not zone.has_class("open"):
                break

        assert not zone.has_class("open")
        assert daemon.asked == []


async def test_a_notice_marks_its_chat_unread_unless_it_is_the_one_on_the_log(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    app = _Stands()
    async with app.run_test(size=(120, 30)) as pilot:
        kept = Kept(tmp_path / "kept.json")
        await _opened(pilot, Daemon(str(tmp_path)), kept, keys=False)
        app.on_log = "c-new"

        navigator.told(app, {"kind": "done", "chat": "c-new"}, unread=True)
        navigator.told(app, {"kind": "done", "epic": "e-done"}, unread=True)
        await pilot.pause()

        assert kept.all("unread") == {"e-done"}


async def test_only_a_folder_nothing_ran_in_is_offered_to_be_forgotten(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    daemon = Daemon(str(tmp_path))
    app = _Stands()
    async with app.run_test(size=(120, 30)) as pilot:
        kept = Kept(tmp_path / "kept.json")
        # Its one chat pinned, the folder's own group is bare, and it is no folder to forget.
        kept.marks("pinned", "c-far", on=True)
        listing = await _opened(pilot, daemon, kept)

        async def offered(heading: str) -> list[str]:
            await _onto(pilot, listing, heading)
            await pilot.press("full_stop")
            await pilot.pause()
            assert isinstance(app.screen, Acts)
            found = [
                str(one.id).removeprefix("=")
                for one in app.screen.query_one("#choices", OptionList).options
            ]
            app.screen.dismiss(None)
            await pilot.pause()
            return found

        assert await offered("g:/far/other") == ["search", "copy", "fold"]
        assert await offered("g:/far/empty") == ["search", "copy", "fold", "forget"]
        assert "chat" in await offered(f"g:{tmp_path}")
