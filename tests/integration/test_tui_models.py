"""The model picker of `/flow`: what checking again for models finds is what is picked from."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest

import hmz.coganchor.models
from hmz.tui import Humanize
from hmz.tui.flows import Flows
from hmz.tui.pick import Agent, Catalogue, Clis
from tests.integration.doubles_tui import (
    MODEL,
    SIZE,
    leaves,
    on,
    opens,
    picks,
    shows,
    stand_in,
    typed,
)

if TYPE_CHECKING:
    from pathlib import Path

    from hmz.coganchor.models import Model


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
        await shows(pilot, "◉ chat")  # set up on no model: the stand-in said none
        await typed(pilot, "/flow")
        await on(pilot, Flows)
        await opens(pilot, "chat")
        await opens(pilot, "0")
        await on(pilot, Agent)
        await opens(pilot, "cli")  # nothing it runs said, so nothing it was set up on
        await on(pilot, Clis)
        await opens(pilot, "claude")
        await on(pilot, Agent)
        await opens(pilot, "model")
        await on(pilot, Catalogue)
        await shows(pilot, "has not reported any models")
        asked.append(True)
        await pilot.click("#act-again")
        await shows(pilot, MODEL)
        await pilot.press("shift+tab")  # off the button, back on to the list
        await opens(pilot, MODEL)
        await on(pilot, Agent)
        await picks(pilot, "effort", "low")
        await leaves(pilot)
        await shows(pilot, f"claude/{MODEL}:low")
