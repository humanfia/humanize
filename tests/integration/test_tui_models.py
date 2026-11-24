"""The model picker of `/flow`: what checking again for models finds is what is picked from."""

from __future__ import annotations

import threading
from typing import TYPE_CHECKING, Any

import pytest

import hmz.coganchor.models
from hmz.tui import Humanize
from hmz.tui.flows import Flows
from hmz.tui.pick import Agent, Catalogue, Clis
from tests.integration.doubles_tui import (
    MODEL,
    PATIENCE,
    RUNS,
    SIZE,
    gives_a_budget,
    leaves,
    on,
    opens,
    picks,
    screen,
    shows,
    stand_in,
    typed,
    until,
)

if TYPE_CHECKING:
    from pathlib import Path

    from hmz.coganchor.models import Model

#: Every epic here is held by a daemon of the test's own, in this process.
pytestmark = pytest.mark.usefixtures("daemon", "loops")


@pytest.fixture
def asked(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, asking: None) -> list[bool]:
    """The stand-in `claude` on `PATH`, which says nothing it runs until it is let to."""
    del asking
    stand_in(tmp_path, monkeypatch)
    real = hmz.coganchor.models.ask
    let: list[bool] = []

    def held(cli: str, *args: Any, **kwargs: Any) -> tuple[Model, ...]:
        if not let:
            raise RuntimeError(f"{cli} is not answering yet")
        return real(cli, *args, **kwargs)

    monkeypatch.setattr(hmz.coganchor.models, "ask", held)
    return let


async def test_a_model_found_by_checking_again_takes_the_efforts_it_was_found_with(
    asked: list[bool],
) -> None:
    app = Humanize()
    async with app.run_test(size=SIZE) as pilot:
        await shows(pilot, "◉ no agent")  # set up on no model: the stand-in said none
        await typed(pilot, "/flow")
        await on(pilot, Flows)
        await opens(pilot, "goal")
        await gives_a_budget(pilot)
        await opens(pilot, "0")
        await on(pilot, Agent)
        await opens(pilot, "cli")  # nothing it runs said, so nothing it was set up on
        await on(pilot, Clis)
        await opens(pilot, "claude")
        await on(pilot, Agent)
        await opens(pilot, "model")
        await on(pilot, Catalogue)
        await shows(pilot, "has listed no models yet")
        asked.append(True)
        await pilot.click("#act-again")
        await shows(pilot, MODEL)
        await pilot.press("shift+tab")  # off the button, back on to the list
        await opens(pilot, MODEL)
        await on(pilot, Agent)
        await picks(pilot, "effort", "low")
        await leaves(pilot)
        await shows(pilot, "set up: /flow goal <task> starts it")
    from hmz.daemon import Hmz

    assert Hmz().settings.agents("goal")["worker"].spec == f"claude/{MODEL}:low"


async def test_checking_again_is_said_over_the_models_already_listed(
    asked: list[bool], monkeypatch: pytest.MonkeyPatch
) -> None:
    asked.append(True)
    held = threading.Event()
    real = hmz.coganchor.models.ask

    def slow(*args: Any, **kwargs: Any) -> tuple[Model, ...]:
        held.wait(PATIENCE)
        return real(*args, **kwargs)

    try:
        async with Humanize().run_test(size=SIZE) as pilot:
            await shows(pilot, f"◉ {RUNS}")
            await typed(pilot, "/flow")
            await on(pilot, Flows)
            await opens(pilot, "goal")
            await opens(pilot, "0")
            await on(pilot, Agent)
            await opens(pilot, "cli")
            await on(pilot, Clis)
            await opens(pilot, "claude")
            await on(pilot, Agent)
            await opens(pilot, "model")
            catalogue = await on(pilot, Catalogue)
            await pilot.click("#act-again")
            await shows(pilot, MODEL)
            # The models may be listed before this first check is done: it ends first.
            await until(
                pilot,
                lambda: "Asking claude" not in screen(pilot.app),
                "the first check to end",
            )

            monkeypatch.setattr(hmz.coganchor.models, "ask", slow)
            catalogue.asked_again()
            await shows(pilot, MODEL, "Asking claude for models…")
            held.set()
            await until(
                pilot,
                lambda: "Asking claude" not in screen(pilot.app),
                "the check to end",
            )
    finally:
        held.set()
