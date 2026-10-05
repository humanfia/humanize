"""The whole run, packaged up to send to whoever is being asked to fix something.

What is on the screen was never the run. The turns went to a coding agent that wrote its own
log, under an id of its own, and the run points at that log by a link -- which is worth nothing
the moment the archive leaves this machine. So a bundle follows every one of them and carries
what is behind it.

Asked for from `/epics`, which is where the runs of this directory are: exporting one belongs
beside gathering its trace, both being things done to a run that has already happened rather
than to whichever run this screen happens to be showing.

Driven headlessly, as every test of the interface is.
"""

from __future__ import annotations

import os
import sys
import tarfile
from typing import TYPE_CHECKING

import pytest
from textual.widgets import Label, OptionList

from hmz.runtime.epic import epics
from hmz.runtime.exporting import TRANSCRIPT
from hmz.tui import Humanize
from hmz.tui.pick import Does, Epics, Exporting
from tests.integration.tui.test_app import onto, rows
from tests.stubs import written
from tests.tui.fixtures import until

if TYPE_CHECKING:
    from pathlib import Path

    from textual.pilot import Pilot

#: A flow that opens one session and says one thing, so that there is a run to package up.
PLAIN = '''"""Runs once, and says what it was told."""

from hmz.flows import Agent, AgentCollection, EnvCollection, FlowContext, FlowParams
from hmz.flows import LocalEnv, flow


class Agents(AgentCollection):
    worker: Agent


class Envs(EnvCollection):
    workspace: LocalEnv


@flow(agents=Agents, envs=Envs, params=FlowParams)
async def plain(task: str, *, agents: Agents, envs: Envs, params: FlowParams,
                ctx: FlowContext) -> None:
    worker = agents["worker"]
    await worker.run(task, session=await worker.spawn(), env=envs["workspace"])
'''

#: A `claude` that answers whatever it is told and logs the session where Claude Code logs
#: one, since what a bundle carries is what the backend wrote rather than what humanize did.
QUIET = """
import json, os, pathlib, sys

flags = dict(zip(sys.argv, sys.argv[1:]))
ident = flags["--session-id"]
under = pathlib.Path(os.environ["CLAUDE_CONFIG_DIR"]) / "projects" / "-a-project"
under.mkdir(parents=True, exist_ok=True)
(under / (ident + ".jsonl")).write_text(
    json.dumps({"type": "user", "text": "what the agent was told"}) + "\\n"
)
print(json.dumps({"type": "system", "session_id": ident}), flush=True)
print(json.dumps({"type": "result", "result": "done"}), flush=True)
"""


@pytest.fixture
def workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A directory with a flow in it, a fake `claude` to drive it, and a log for it to write."""
    binaries = tmp_path / "bin"
    binaries.mkdir()
    fake = binaries / "claude"
    fake.write_text(f"#!{sys.executable}\n{QUIET}")
    fake.chmod(0o755)
    monkeypatch.setenv("PATH", f"{binaries}{os.pathsep}{os.environ['PATH']}")
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path / "claude-home"))
    where = tmp_path / ".hmz/flows"
    where.mkdir(parents=True)
    written(where, "plain", PLAIN)
    monkeypatch.chdir(tmp_path)
    return tmp_path


def _ran(task: str) -> None:
    """Runs the flow here the way a command line would, so there is an epic to export."""
    from hmz.runtime import Hmz

    Hmz().run(
        "plain", task, agents={"worker": "claude/m:high"}, budget={"cost": 1}
    ).run()


async def exports_to(app: Humanize, driver: Pilot[None], *typed: str) -> None:
    """Picks `export run` on the run gone into, and answers where it goes.

    Args:
      app: The interface, on the sheet of one run.
      driver: What is pumping it.
      typed: The keys that write where it goes, `tab` among them where it is finished.
    """
    await onto(app, driver, "export")
    await driver.press("enter")
    await until(lambda: isinstance(app.screen, Exporting), driver)
    await driver.press(*typed)
    await driver.press("enter")  # keeps the row, which moves on to `done`
    await driver.press("enter")


def _written(app: Humanize) -> str:
    """What the row of a form being written says, and what is said under it."""
    screen = app.screen
    assert isinstance(screen, Exporting)
    return (
        f"{screen.query_one('#choices', OptionList).get_option_at_index(0).prompt}\n"
        f"{screen.query_one('#tuning', Label).content}"
    )


def _archives(under: Path) -> list[Path]:
    """Every exported run anywhere below a directory, which is where an export may not wander."""
    return sorted(under.rglob("*.epic.tar.gz"))


def _held(at: Path) -> dict[str, str]:
    """Everything one bundle holds, by the name it is under inside the run's own directory."""
    held: dict[str, str] = {}
    with tarfile.open(at) as opened:
        for one in opened.getmembers():
            handle = opened.extractfile(one)
            held[one.name.partition("/")[2]] = (
                handle.read().decode("utf-8") if handle is not None else ""
            )
    return held


@pytest.mark.timeout(90)
async def test_a_run_out_of_the_list_is_exported_from_the_menu_under_it(
    workspace: Path,
) -> None:
    """Exporting an old run is gathering its trace as well: both are reading one back.

    And it goes where it is told to, finished as it is typed: nowhere in the project unless
    somebody says so.
    """
    _ran("do the thing")
    (workspace / "bundles").mkdir()

    app = Humanize()
    async with app.run_test() as driver:
        await driver.press(*"/epics")
        await driver.press("enter")
        await until(lambda: isinstance(app.screen, Epics), driver)
        sheet = app.screen
        await driver.press("enter")
        await until(lambda: isinstance(app.screen, Does), driver)
        assert "export" in rows(app)
        await exports_to(app, driver, *"bun", "tab")
        await until(lambda: app.screen is sheet, driver)
        # Under the list while it is open: what was written reaches the transcript when the
        # list is left, so waiting for it there with the list still up waits for nothing.
        await until(
            lambda: "epic.tar.gz" in str(sheet.query_one("#tuning", Label).content),
            driver,
        )

    (epic,) = epics(workspace)
    at = workspace / "bundles" / f"{epic.name}.epic.tar.gz"
    assert at.is_file()
    assert _archives(workspace) == [at]
    held = _held(at)
    # No transcript in this one: what is on the screen is not this run, which may be a week old.
    assert TRANSCRIPT not in held
    # And the trace of the run rides along, gathering one having been the other half of the
    # row this was: a bundle is read by somebody who was not there.
    assert [one for one in held if one.startswith("traces/")], held


@pytest.mark.timeout(60)
async def test_where_an_export_goes_is_finished_as_it_is_typed(workspace: Path) -> None:
    """As a shell finishes a path: as far as everything it could be agrees, then each in turn.

    What it could be is said under the list while it is written, the one tab took picked out,
    and `~` is the home it names.
    """
    _ran("do the thing")
    (workspace / "outbox" / "alpha2").mkdir(parents=True)
    (workspace / "outbox" / "alpha2" / "inner.txt").write_text("")
    (workspace / "outbox" / "alpha.tgz").write_text("")
    (workspace / "outbox" / "beta").write_text("")
    (workspace / "outbox" / ".hidden").write_text("")
    (workspace / "home" / "exports").mkdir(parents=True)

    app = Humanize()
    async with app.run_test() as driver:
        await driver.press(*"/epics")
        await driver.press("enter")
        await until(lambda: isinstance(app.screen, Epics), driver)
        await driver.press("enter")
        await until(lambda: isinstance(app.screen, Does), driver)
        await onto(app, driver, "export")
        await driver.press("enter")
        await until(lambda: isinstance(app.screen, Exporting), driver)
        form = app.screen
        assert isinstance(form, Exporting)

        await driver.press(*"outbox/a")
        await driver.pause()
        said = _written(app)
        assert "alpha.tgz" in said
        assert "alpha2/" in said
        assert "beta" not in said
        # As far as both agree, which is as far as a shell would go.
        await driver.press("tab")
        await driver.pause()
        assert form._typed_in["to"] == "outbox/alpha"
        # Then each in turn, round and round, the focus staying on the row.
        await driver.press("tab")
        await driver.pause()
        assert form._typed_in["to"] == "outbox/alpha.tgz"
        await driver.press("tab")
        await driver.pause()
        assert form._typed_in["to"] == "outbox/alpha2/"
        await driver.press("tab")
        await driver.pause()
        assert form._typed_in["to"] == "outbox/alpha.tgz"
        assert form.query_one("#choices", OptionList).has_focus
        # A dot-file only once a dot is typed.
        for _ in "alpha.tgz":
            await driver.press("backspace")
        await driver.pause()
        assert ".hidden" not in _written(app)
        await driver.press(".")
        await driver.pause()
        assert ".hidden" in _written(app)
        # And a `~` naming nobody is nothing to finish, rather than the end of the interface.
        await driver.press(*"x/~nobody-at-all/", "tab")
        await driver.pause()
        assert form._typed_in["to"] == "outbox/.x/~nobody-at-all/"

        # Kept, and begun on again: tab goes on into the directory it took, not beside it.
        await driver.press("escape")
        await driver.press(*"outbox/al", "tab", "tab", "tab")
        await driver.pause()
        assert form._typed_in["to"] == "outbox/alpha2/"
        await driver.press("enter", "up", "enter", "tab")
        await driver.pause()
        assert form._typed_in["to"] == "outbox/alpha2/inner.txt"

        # Put back to what was kept, and written again from the home a `~` names.
        await driver.press("escape")
        await driver.press(*["backspace"] * len("outbox/alpha2/"))
        await driver.press(*"~/ex", "tab", "enter", "enter")
        await until(lambda: app.screen is not form, driver)
        await until(
            lambda: (
                "epic.tar.gz" in str(app.screen.query_one("#tuning", Label).content)
            ),
            driver,
        )

    (epic,) = epics(workspace)
    assert (workspace / "home" / "exports" / f"{epic.name}.epic.tar.gz").is_file()


@pytest.mark.timeout(60)
async def test_an_export_goes_nowhere_until_it_is_told_where(workspace: Path) -> None:
    """Nowhere of its own choosing; and walking out of the question is back to the run."""
    _ran("do the thing")

    app = Humanize()
    async with app.run_test() as driver:
        await driver.press(*"/epics")
        await driver.press("enter")
        await until(lambda: isinstance(app.screen, Epics), driver)
        await driver.press("enter")
        await until(lambda: isinstance(app.screen, Does), driver)
        await onto(app, driver, "export")
        await driver.press("enter")
        await until(lambda: isinstance(app.screen, Exporting), driver)
        form = app.screen

        await onto(app, driver, "done")
        await driver.press("enter")
        await driver.pause()
        assert app.screen is form
        assert "required" in str(form.query_one("#tuning", Label).content)

        await driver.press("escape")
        await until(lambda: isinstance(app.screen, Does), driver)

    assert _archives(workspace) == []
