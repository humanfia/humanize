"""`hmz.tui.views.aichan`: her conversations in the context zone, and what its keys do."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from textual.app import App, ComposeResult

from hmz.tui import humanfia, shell
from hmz.tui.pick import AiForgets, AiMarks, AiRenames
from hmz.tui.views.aichan import VIEWS, Conversations, keeps, remembers
from hmz.tui.views.navigator import Kept

if TYPE_CHECKING:
    from pathlib import Path


def _one(
    number: int, title: str, updated: str, state: str = "waiting"
) -> dict[str, Any]:
    return {
        "id": number,
        "title": title,
        "scope": "workspace",
        "workspace": "/home/me/project",
        "nous": "fast",
        "preset": "read-only",
        "slot": f"ai:{number}",
        "state": state,
        "updated": updated,
    }


class _Daemon:
    """What answers `aichan.*`, and what it was asked."""

    def __init__(self, *listed: dict[str, Any]) -> None:
        self.listed = list(listed)
        self.asked: list[tuple[str, dict[str, Any]]] = []
        self.refuses = ""

    def __call__(self, method: str, **params: Any) -> Any:
        self.asked.append((method, params))
        if self.refuses:
            raise OSError(self.refuses)
        if method == "rename":
            for one in self.listed:
                if one["id"] == params["id"]:
                    one["title"] = params["title"]
        if method == "forget":
            self.listed = [one for one in self.listed if one["id"] != params["id"]]
        return {"conversations": [dict(one) for one in self.listed]}


class _Host(App[None]):
    """An interface that is the view, and what it was told to follow and to start."""

    def __init__(
        self, daemon: _Daemon, marks: AiMarks, kept: Kept | None = None
    ) -> None:
        super().__init__()
        self.followed: list[dict[str, Any]] = []
        self.started = 0
        self._daemon, self._marks, self._kept = daemon, marks, kept

    def get_css_variables(self) -> dict[str, str]:
        return {**humanfia.FALLBACK, **super().get_css_variables()}

    def compose(self) -> ComposeResult:
        yield Conversations(
            follows=self.followed.append,
            news=self._starts,
            asks=self._daemon,
            marks=self._marks,
            kept=self._kept,
        )

    def _starts(self) -> None:
        self.started += 1


def _rows(app: _Host) -> list[str]:
    listing = app.query_one(Conversations)
    return [str(one.prompt) for one in listing.options]


async def _listed(app: _Host, pilot: Any) -> Conversations:
    listing = app.query_one(Conversations)
    await app.workers.wait_for_complete()  # pyright: ignore[reportUnknownMemberType]
    await pilot.pause()
    listing.focus()
    return listing


def test_the_view_is_ai_chans_in_the_context_zone_on_f3() -> None:
    (view,) = VIEWS

    assert (view.name, view.zone, view.title, view.key) == (
        "aichan",
        "context",
        "Ai-chan",
        "f3",
    )
    assert shell.views()["aichan"] is view
    assert [key for key, _ in view.keys] == ["enter", "n", "r", "p", "u", "delete"]


async def test_the_pinned_come_first_then_the_latest_and_the_unread_are_dotted() -> (
    None
):
    marks = AiMarks()
    marks.pinned.add(1)
    marks.unread.add(2)
    daemon = _Daemon(
        _one(1, "old", "2026-01-01"),
        _one(2, "mid", "2026-01-02"),
        _one(3, "new", "2026-01-03", "running"),
    )
    app = _Host(daemon, marks)

    async with app.run_test(size=(60, 20)) as pilot:
        await _listed(app, pilot)
        new, first, second, third = _rows(app)

    assert "New conversation" in new
    assert first.startswith("■ ")
    assert "Ai-chan#1 · old" in first
    assert "Ai-chan#3 · new" in second
    assert "typing…" in second
    assert "Ai-chan#2 · mid" in third
    assert "●" in third
    assert "workspace project · read-only" in third


async def test_with_no_conversation_it_says_so_and_a_refusal_is_said() -> None:
    app = _Host(_Daemon(), AiMarks())
    async with app.run_test(size=(60, 20)) as pilot:
        await _listed(app, pilot)
        assert _rows(app)[-1] == "No conversations yet"

    daemon = _Daemon()
    daemon.refuses = "no daemon"
    app = _Host(daemon, AiMarks())
    async with app.run_test(size=(60, 20)) as pilot:
        await _listed(app, pilot)
        assert "could not be loaded: no daemon" in _rows(app)[-1]


async def test_enter_follows_a_conversation_and_reads_it_and_new_starts_one() -> None:
    marks = AiMarks()
    marks.unread.add(3)
    app = _Host(_Daemon(_one(3, "new", "2026-01-03")), marks)

    async with app.run_test(size=(60, 20)) as pilot:
        await _listed(app, pilot)
        await pilot.press("enter")
        assert (app.started, app.followed) == (1, [])

        await pilot.press("n")
        assert app.started == 2

        await pilot.press("down", "enter")
        assert [one["slot"] for one in app.followed] == ["ai:3"]
        assert not marks.unread


async def test_p_pins_and_u_marks_unread_without_asking_the_daemon() -> None:
    marks = AiMarks()
    daemon = _Daemon(_one(3, "new", "2026-01-03"), _one(2, "mid", "2026-01-02"))
    app = _Host(daemon, marks)

    async with app.run_test(size=(60, 20)) as pilot:
        await _listed(app, pilot)
        await pilot.press("down", "down", "p")
        assert marks.pinned == {2}
        assert "Ai-chan#2" in _rows(app)[1]
        # The cursor went up with the conversation it was on, not to whatever took its row.
        listing = app.query_one(Conversations)
        assert (listing.under() or {})["id"] == 2

        await pilot.press("u")
        assert marks.unread
        await pilot.press("u")
        assert not marks.unread

    assert [method for method, _ in daemon.asked] == ["list"]


async def test_r_renames_and_delete_asks_first() -> None:
    daemon = _Daemon(_one(3, "new", "2026-01-03"))
    app = _Host(daemon, AiMarks())

    async with app.run_test(size=(80, 24)) as pilot:
        await _listed(app, pilot)
        await pilot.press("down", "r")
        await pilot.pause()
        assert isinstance(app.screen, AiRenames)
        await pilot.press(*"again", "tab", "enter")
        await app.workers.wait_for_complete()  # pyright: ignore[reportUnknownMemberType]
        await pilot.pause()
        assert ("rename", {"id": 3, "title": "again"}) in daemon.asked
        assert "Ai-chan#3 · again" in _rows(app)[1]

        await pilot.press("delete")
        await pilot.pause()
        assert isinstance(app.screen, AiForgets)
        # Keeping it is the answer the keys open on.
        await pilot.press("enter")
        await pilot.pause()
        assert not any(method == "forget" for method, _ in daemon.asked)

        await pilot.press("delete")
        await pilot.pause()
        await pilot.press("right", "enter")
        await app.workers.wait_for_complete()  # pyright: ignore[reportUnknownMemberType]
        await pilot.pause()
        assert ("forget", {"id": 3}) in daemon.asked
        assert _rows(app)[-1] == "No conversations yet"


async def test_the_one_the_log_follows_is_read_as_it_is_said_in_and_left_when_deleted() -> (
    None
):
    marks = AiMarks()
    daemon = _Daemon(_one(3, "new", "2026-01-03"))
    left: list[int] = []
    listing = Conversations(
        follows=lambda _: None,
        news=lambda: None,
        asks=daemon,
        marks=marks,
        followed=lambda: 3,
        forgot=left.append,
    )

    class _Shows(App[None]):
        def compose(self) -> ComposeResult:
            yield listing

    app = _Shows()
    async with app.run_test(size=(80, 24)) as pilot:
        await app.workers.wait_for_complete()  # pyright: ignore[reportUnknownMemberType]
        await pilot.pause()
        listing.focus()
        # Said in since: still read, since it is the one on the screen.
        daemon.listed[0]["updated"] = "2026-01-04"
        listing.reads()
        await app.workers.wait_for_complete()  # pyright: ignore[reportUnknownMemberType]
        await pilot.pause()
        assert "●" not in str(listing.options[1].prompt)

        await pilot.press("down", "delete")
        await pilot.pause()
        await pilot.press("right", "enter")
        await app.workers.wait_for_complete()  # pyright: ignore[reportUnknownMemberType]
        await pilot.pause()
    assert left == [3]


async def test_what_is_pinned_and_unread_is_kept_for_the_next_interface(
    tmp_path: Path,
) -> None:
    kept = Kept(tmp_path / "navigator.json")
    kept.group = "date"
    kept.marks("pinned", "a-chat", on=True)
    daemon = _Daemon(_one(1, "old", "2026-01-01"), _one(2, "new", "2026-01-02"))
    app = _Host(daemon, AiMarks(), kept)

    async with app.run_test(size=(60, 20)) as pilot:
        await _listed(app, pilot)
        await pilot.press("down", "p")  # the newest, which is first: pinned
        await pilot.press("down", "u")  # the other: unread
        await pilot.pause()

    again = AiMarks()
    remembers(again, Kept(tmp_path / "navigator.json"))
    assert again.pinned == {2}
    assert again.unread == {1}
    # Beside the navigator's own, which it leaves as it found them.
    held = Kept(tmp_path / "navigator.json")
    assert held.group == "date"
    assert held.all("pinned") == {"a-chat"}

    # And what is read, up to when, and what was let go of.
    again.pinned.clear()
    again.reads(_one(1, "old", "2026-01-01"))
    keeps(again, Kept(tmp_path / "navigator.json"))
    last = AiMarks()
    remembers(last, Kept(tmp_path / "navigator.json"))
    assert (last.pinned, last.unread) == (set(), set())
    assert last.seen == {1: "2026-01-01"}
    assert last.is_unread(_one(1, "old", "2026-01-05"))
