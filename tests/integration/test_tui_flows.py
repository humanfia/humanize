"""`/flow`: picking the flow, its agents' CLI, model and effort, and its budget, then running it."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest
import yaml

from hmz.daemon.link import Link
from hmz.runtime.flowing import index
from hmz.tui import Humanize
from hmz.tui.flows import Flows
from hmz.tui.pick import Agent, Clis
from tests.integration.doubles_tui import (
    MODEL,
    OWN,
    RUNS,
    SIZE,
    leaves,
    on,
    opened,
    opens,
    own_flow,
    picks,
    rows,
    screen,
    set_up_own_flow,
    shows,
    stand_in,
    started,
    trail,
    typed,
    until,
)

if TYPE_CHECKING:
    from collections.abc import Mapping
    from pathlib import Path

    from textual.pilot import Pilot


@pytest.fixture
def workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, asking: None) -> Path:
    """The stand-in `claude` on `PATH`, and a flow of the workspace's own beside the built-ins."""
    del asking
    workspace = stand_in(tmp_path, monkeypatch)
    own_flow(workspace)
    return workspace


def remembered(tmp_path: Path, workspace: Path) -> dict[str, Any]:
    """What the settings file keeps about the workspace, or nothing where it keeps nothing."""
    kept = tmp_path / "humanize-home" / "settings.yaml"
    said: dict[str, Any] = yaml.safe_load(kept.read_text()) if kept.exists() else {}
    return dict(said.get("workspaces", {}).get(str(workspace), {}))


async def into_flows(pilot: Pilot[None]) -> Flows:
    """Opens `/flow` on the flows installed, once the interface is set up."""
    await opened(pilot)
    await typed(pilot, "/flow")
    return await on(pilot, Flows)


async def test_flow_lists_the_built_in_flows_and_the_workspace_s_own(
    workspace: Path,
) -> None:
    app = Humanize()
    async with app.run_test(size=SIZE) as pilot:
        await into_flows(pilot)

        listed = rows(app)
        assert {"chat", "goal", "ralph_loop", OWN} <= set(listed)
        drawn = screen(app)
        assert "Talks to one agent for as long as you keep answering it." in drawn


async def test_walking_out_of_flow_without_saving_changes_nothing(
    workspace: Path, tmp_path: Path
) -> None:
    app = Humanize()
    async with app.run_test(size=SIZE) as pilot:
        await into_flows(pilot)
        await opens(pilot, "goal")
        await shows(pilot, trail("Installed", "goal"))

        await leaves(pilot, saving=False)

        await shows(pilot, "◉ chat")
    assert remembered(tmp_path, workspace) == {}


async def test_an_own_flow_given_a_budget_and_saved_runs_and_is_opened_on_next_time(
    workspace: Path, tmp_path: Path
) -> None:
    async with Humanize().run_test(size=SIZE) as pilot:
        await set_up_own_flow(pilot)
        await shows(pilot, f"coder · {RUNS}")

        await typed(pilot, "make it so")
        drawn = await shows(pilot, "the flow is done")

    assert "heard make it so" in drawn
    assert (workspace / "said.txt").read_text() == "started: heard make it so\n"
    assert remembered(tmp_path, workspace)["flow"] == OWN
    async with Humanize().run_test(size=SIZE) as pilot:
        await shows(pilot, f"◉ {OWN}", f"coder · {RUNS}")


async def test_an_effort_picked_for_an_agent_is_what_its_next_turn_starts_at(
    workspace: Path, tmp_path: Path
) -> None:
    app = Humanize()
    async with app.run_test(size=SIZE) as pilot:
        await into_flows(pilot)
        await opens(pilot, "chat")
        await opens(pilot, "0")  # its one agent
        await on(pilot, Agent)
        await picks(pilot, "effort", "low")
        await shows(pilot, "unsaved changes")
        await leaves(pilot)
        await shows(pilot, f"claude/{MODEL}:low")

        await typed(pilot, "hello")
        await shows(pilot, "heard hello")

    (argv,) = started(workspace)
    assert argv[argv.index("--effort") + 1] == "low"
    assert remembered(tmp_path, workspace)["flows"] == {
        "chat": {"agents": {"assistant": f"claude/{MODEL}:low"}}
    }


async def test_the_cli_and_model_pickers_offer_what_the_installed_agent_said_it_runs(
    workspace: Path,
) -> None:
    app = Humanize()
    async with app.run_test(size=SIZE) as pilot:
        await into_flows(pilot)
        await opens(pilot, "chat")
        await opens(pilot, "0")
        await on(pilot, Agent)

        await opens(pilot, "cli")
        await on(pilot, Clis)
        assert "claude" in rows(app)
        await shows(pilot, "claude ✔", "1 model")
        await pilot.press("escape")

        await on(pilot, Agent)
        await opens(pilot, "model")
        await shows(pilot, f"{MODEL} ✔")


async def test_the_flows_with_a_newer_release_are_counted_on_the_status_line(
    workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    held = index.Installed(
        verse="official", name="kernel", version="1.0.0", commit="", repo=""
    )
    newer = [index.Update(held, "1.1.0")]
    monkeypatch.setattr(index, "updates", lambda: newer)
    app = Humanize()
    async with app.run_test(size=SIZE) as pilot:
        await opened(pilot)
        await shows(
            pilot, "kernel 1.0.0 ↑ 1.1.0; update from /flow", "1 flow update · "
        )

        newer.clear()
        await typed(pilot, "/flow")
        await on(pilot, Flows)
        await leaves(pilot)
        await until(pilot, lambda: "flow update" not in screen(app), "the count to go")


async def test_both_profiling_switches_are_remembered_and_sent_with_the_start(
    workspace: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    asked: list[Mapping[str, Any]] = []
    asking = Link.asked

    def spied(self: Link, said: Mapping[str, Any], **kwargs: Any) -> dict[str, Any]:
        asked.append(said)
        return asking(self, said, **kwargs)

    monkeypatch.setattr(Link, "asked", spied)
    async with Humanize().run_test(size=SIZE) as pilot:
        await into_flows(pilot)
        await opens(pilot, "chat")
        await shows(pilot, "profile flow", "profile environment")
        await picks(pilot, "\x1eprofile-flow", "on")
        await picks(pilot, "\x1eprofile-environment", "on")
        await shows(pilot, "samples the flow's own Python")
        await leaves(pilot)
        await shows(pilot, "◉ chat")

        await typed(pilot, "hello")
        await shows(pilot, "heard hello")

    (start,) = [one for one in asked if one.get("do") == "start"]
    assert (start["profile_flow"], start["profile_environment"]) == (True, True)
    kept = remembered(tmp_path, workspace)["flows"]["chat"]
    assert (kept["profile_flow"], kept["profile_environment"]) == (True, True)
    async with Humanize().run_test(size=SIZE) as pilot:
        await into_flows(pilot)
        await opens(pilot, "chat")
        await shows(pilot, "samples the flow's own Python")
