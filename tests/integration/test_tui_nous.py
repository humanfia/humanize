"""`/settings nous`: every nous listed, written on its form and its graph's, and saved."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from textual.widgets import OptionList

from hmz.runtime import Hmz
from hmz.tui import Humanize
from hmz.tui.pick import GraphForm, NodeForm, NousForm
from hmz.tui.settings import Adjusts
from tests.integration.doubles_tui import (
    SIZE,
    leaves,
    on,
    onto,
    opened,
    opens,
    picks,
    shows,
    stand_in,
    typed,
)

if TYPE_CHECKING:
    from pathlib import Path

    from textual.pilot import Pilot

    from hmz.coganchor.nous import Nous

#: Every epic here is held by a daemon of the test's own, in this process.
pytestmark = pytest.mark.usefixtures("daemon")


@pytest.fixture
def workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, asking: None) -> Path:
    """The stand-in `claude` on `PATH`, as `/settings` is opened on it."""
    del asking
    return stand_in(tmp_path, monkeypatch)


async def into_nous(pilot: Pilot[None]) -> Adjusts:
    """Opens `/settings nous`."""
    await opened(pilot)
    await typed(pilot, "/settings nous")
    return await on(pilot, Adjusts)


def listing(pilot: Pilot[None]) -> None:
    """Gives the rows of the form on top the focus, which keeping a row may move to `done`."""
    pilot.app.screen.query_one("#choices", OptionList).focus()


async def writes(pilot: Pilot[None], row: str, said: str) -> None:
    """Types into one written row of the form on top, and keeps it."""
    listing(pilot)
    await onto(pilot, row)
    await pilot.press(*said, "enter")
    await pilot.pause()
    listing(pilot)


async def done(pilot: Pilot[None], under: type[object]) -> None:
    """Answers the form on top from its `done` button, landing on the sheet under it."""
    await pilot.click("#act-done")
    await on(pilot, under)
    listing(pilot)


def written(name: str) -> Nous:
    """One nous as the settings hold it."""
    found = {one.name: one for one in Hmz().nous.all()}
    assert name in found, f"{name} is not written down: {sorted(found)}"
    return found[name]


def virtual_and_one_naming_it() -> None:
    """`smart`, a virtual nous, and `claude/sonnet`, whose then is `smart`."""
    book = Hmz().nous
    book.write("smart", graph=["claude/opus"])
    book.write("claude/sonnet", tries=1, then=["smart"])


async def test_every_nous_is_listed_with_its_envelope_and_its_graphs(
    workspace: Path,
) -> None:
    virtual_and_one_naming_it()
    async with Humanize().run_test(size=SIZE) as pilot:
        await opened(pilot)
        await typed(pilot, "/settings")
        await on(pilot, Adjusts)
        await shows(pilot, "Nous", "2 nous")

        await opens(pilot, "nous")
        await shows(
            pilot,
            "smart",
            "Virtual · once",
            "claude/opus · then none",
            "claude/sonnet",
            "Concrete · 1 more go",
            "then smart",
        )


async def test_a_concrete_nous_is_added_with_tries_and_a_then_chain(
    workspace: Path,
) -> None:
    async with Humanize().run_test(size=SIZE) as pilot:
        await into_nous(pilot)
        await shows(pilot, "No nous yet.")
        await pilot.click("#act-add")
        await on(pilot, NousForm)

        await writes(pilot, "name", "claude/opus")
        await picks(pilot, "tries", "2")
        await opens(pilot, "then")
        await on(pilot, GraphForm)
        for nous in ("codex/gpt-5", "claude/sonnet"):
            await opens(pilot, "add")
            await on(pilot, NodeForm)
            await writes(pilot, "use", nous)
            await done(pilot, GraphForm)
        # The first goes on to the second, on any fault.
        await opens(pilot, "node:n1")
        await on(pilot, NodeForm)
        await picks(pilot, "on:*", "n2")
        await done(pilot, GraphForm)
        await done(pilot, NousForm)
        await shows(pilot, "codex/gpt-5 → claude/sonnet")
        await done(pilot, Adjusts)

        await shows(pilot, "claude/opus", "2 more goes", "● Unsaved")
        await leaves(pilot)

    one = written("claude/opus")
    assert one.tries == 2
    assert one.then is not None
    assert one.then.chained() == ("codex/gpt-5", "claude/sonnet")


async def test_a_virtual_nous_is_made_of_a_balance_node_and_a_fault_edge(
    workspace: Path,
) -> None:
    strategy = Hmz().nous.strategies()[-1].name
    async with Humanize().run_test(size=SIZE) as pilot:
        await into_nous(pilot)
        await pilot.click("#act-add")
        await on(pilot, NousForm)
        await writes(pilot, "name", "smart")

        await opens(pilot, "graph")
        await on(pilot, GraphForm)
        await opens(pilot, "add")
        await on(pilot, NodeForm)
        await picks(pilot, "kind", "balance")
        await picks(pilot, "balance", strategy)
        await writes(pilot, "among", "claude/opus 2, codex/gpt-5 1")
        await done(pilot, GraphForm)
        await opens(pilot, "add")
        await on(pilot, NodeForm)
        await writes(pilot, "use", "claude/sonnet")
        await done(pilot, GraphForm)
        await opens(pilot, "node:n1")
        await on(pilot, NodeForm)
        await picks(pilot, "on:throttled", "n2")
        await done(pilot, GraphForm)
        await shows(pilot, "throttled → n2")
        await done(pilot, NousForm)
        await done(pilot, Adjusts)

        await shows(
            pilot,
            "smart",
            f"{strategy}: claude/opus×2,",
        )
        await leaves(pilot)

    graph = written("smart").graph
    assert graph is not None
    first = graph.node(graph.start)
    assert first is not None
    assert first.balance == strategy
    assert first.among == (("claude/opus", 2), ("codex/gpt-5", 1))
    assert first.on == (("throttled", "n2"),)
    assert graph.node("n2") is not None


async def test_a_graph_whose_edges_come_round_is_refused(workspace: Path) -> None:
    async with Humanize().run_test(size=SIZE) as pilot:
        await into_nous(pilot)
        await pilot.click("#act-add")
        await on(pilot, NousForm)
        await writes(pilot, "name", "loops")
        await opens(pilot, "graph")
        await on(pilot, GraphForm)
        for nous in ("claude/opus", "claude/sonnet"):
            await opens(pilot, "add")
            await on(pilot, NodeForm)
            await writes(pilot, "use", nous)
            await done(pilot, GraphForm)
        for node, to in (("n1", "n2"), ("n2", "n1")):
            await opens(pilot, f"node:{node}")
            await on(pilot, NodeForm)
            await picks(pilot, "on:*", to)
            await done(pilot, GraphForm)

        await pilot.click("#act-done")

        await shows(pilot, "loops: the edges come round at node n1")
        await on(pilot, GraphForm)


async def test_a_nous_that_is_none_is_refused(workspace: Path) -> None:
    async with Humanize().run_test(size=SIZE) as pilot:
        await into_nous(pilot)
        await pilot.click("#act-add")
        await on(pilot, NousForm)
        await writes(pilot, "name", "claude/opus")

        await pilot.click("#act-done")

        await shows(pilot, "claude/opus says nothing; give it more tries or a then.")
        await on(pilot, NousForm)


async def test_a_virtual_nous_is_renamed_and_what_names_it_follows(
    workspace: Path,
) -> None:
    virtual_and_one_naming_it()
    async with Humanize().run_test(size=SIZE) as pilot:
        await into_nous(pilot)
        await opens(pilot, "smart")
        await on(pilot, NousForm)
        await onto(pilot, "name")
        await pilot.press(*["backspace"] * len("smart"), *"clever", "enter")
        await done(pilot, Adjusts)

        await shows(pilot, "clever", "then clever")
        await leaves(pilot)

    assert {one.name for one in Hmz().nous.all()} == {"clever", "claude/sonnet"}
    then = written("claude/sonnet").then
    assert then is not None
    assert then.chained() == ("clever",)


async def test_removing_a_virtual_nous_another_names_is_refused(
    workspace: Path,
) -> None:
    virtual_and_one_naming_it()
    async with Humanize().run_test(size=SIZE) as pilot:
        await into_nous(pilot)
        await opens(pilot, "smart")
        await on(pilot, NousForm)

        await pilot.click("#act-remove")
        await on(pilot, Adjusts)

        await shows(pilot, "claude/sonnet still names smart")
        await leaves(pilot)

    assert written("smart").virtual
