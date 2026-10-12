"""`hmz.tui.pick.Backing`: one backup target's form, and what answering it holds."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from textual.app import App
from textual.widgets import Label

from hmz.tui import pick

if TYPE_CHECKING:
    from collections.abc import Callable


class _Host(App[None]):
    """Puts the form up and keeps what it was answered with."""

    def __init__(self, form: pick.Backing) -> None:
        super().__init__()
        self.form = form
        self.answers: list[pick.Repo | str | None] = []

    def on_mount(self) -> None:
        self.push_screen(self.form, self.answers.append)


async def _answered(
    repo: pick.Repo,
    then: Callable[[pick.Backing], None] = lambda _: None,
    taken: frozenset[str] = frozenset(),
) -> tuple[list[pick.Repo | str | None], str]:
    host = _Host(pick.Backing(repo, taken=taken))
    async with host.run_test() as pilot:
        await pilot.pause()
        then(host.form)
        host.form.action_done()
        await pilot.pause()
        said = (
            "" if host.answers else str(host.form.query_one("#tuning", Label).content)
        )
    return host.answers, said


async def test_a_target_is_held_with_what_its_rows_say() -> None:
    def sets(form: pick.Backing) -> None:
        form.dropped("session", "on")
        form.dropped("interval", "15 minutes")
        form.dropped("default", "on")

    answers, _ = await _answered(pick.Repo("lab", "git@example:you/epics.git"), sets)

    assert answers == [
        pick.Repo(
            "lab",
            "git@example:you/epics.git",
            "main",
            ("session", "interval"),
            15,
            default=True,
        )
    ]


async def test_minutes_not_offered_are_kept_while_off() -> None:
    repo = pick.Repo("lab", "u", policies=("interval",), every=45)
    assert "45 minutes" in pick.Backing(repo, taken=frozenset()).choices("interval")

    answers, _ = await _answered(repo, lambda form: form.dropped("interval", "off"))

    assert answers == [pick.Repo("lab", "u", every=45)]


@pytest.mark.parametrize(
    ("name", "url", "wrong"),
    [
        ("two words", "u", "name is one short word"),
        ("home", "u", "another target is named home"),
        ("lab", "", "URL is required"),
    ],
)
async def test_a_target_that_is_not_one_is_refused(
    name: str, url: str, wrong: str
) -> None:
    answers, said = await _answered(pick.Repo(name, url), taken=frozenset({"home"}))

    assert answers == []
    assert wrong in said
