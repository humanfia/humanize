"""An interface as one frontend of runs another frontend is reading too.

One host in this process, an interface on it as `alice`, and a program on it as `bob` through
the same `Link` the SDK hands out. Every flow is a file this test wrote and runs for real: one
whose only agents are `Outworlder` roles spends nothing and needs no CLI, and one that drives an
agent drives a stand-in behind the real harness driver, as `tests/integration/runtime` does.

What is checked is what the interface draws of the other frontend -- which role is whose, who
answered what and who said what -- and that what it answers and says reaches the other.
"""

from __future__ import annotations

import json
import os
import threading
import time
from typing import TYPE_CHECKING, Any

import pytest

from hmz.coganchor.agents import AgentConfig
from hmz.daemon import linked
from hmz.runtime import Hmz
from hmz.runtime.flowing.harnesses import HarnessDriver
from hmz.runtime.flowing.specs import parse_agents
from hmz.tui import Humanize
from tests.integration.runtime.test_hosting import ASKS, STEERS, TURN, SteerableAgent
from tests.stubs import written
from tests.tui.fixtures import transcript, until

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator
    from pathlib import Path

    from textual.pilot import Pilot

    from hmz.daemon import Link
    from hmz.runtime import Host

#: How long a test waits for something another thread is doing.
PATIENCE = 20.0


class Bob:
    """The other frontend: a program on the same runs, and everything it has been told."""

    def __init__(self, host: Host) -> None:
        self.link: Link = linked(host, "bob", "sdk")
        self.seen: list[dict[str, Any]] = []
        self._landed = threading.Condition()
        self.link.heard(self._told)

    def _told(self, message: dict[str, Any]) -> None:
        with self._landed:
            self.seen.append(message)
            self._landed.notify_all()

    def told(self, kind: str, /, **fields: Any) -> dict[str, Any]:
        """The first message of a kind saying all of `fields`, waited for."""

        def found() -> dict[str, Any] | None:
            return next(
                (
                    one
                    for one in self.seen
                    if one["type"] == kind
                    and all(one.get(key) == value for key, value in fields.items())
                ),
                None,
            )

        with self._landed:
            one = self._landed.wait_for(found, timeout=PATIENCE)
        assert one is not None, (
            f"never told {kind}: {[one['type'] for one in self.seen]}"
        )
        return one

    def asked(self, role: str) -> dict[str, Any]:
        """The question a role is waiting on, as the frontends were last shown it."""
        self.told_that(
            lambda one: (
                one["type"] == "pending"
                and any(asked["role"] == role for asked in one["pending"])
            )
        )
        with self._landed:
            pending = [one for one in self.seen if one["type"] == "pending"][-1]
        return next(one for one in pending["pending"] if one["role"] == role)

    def told_that(self, what: Callable[[dict[str, Any]], bool]) -> dict[str, Any]:
        with self._landed:
            one = self._landed.wait_for(
                lambda: next((one for one in self.seen if what(one)), None),
                timeout=PATIENCE,
            )
        assert one is not None
        return one


@pytest.fixture
def workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Both flows, and a `claude` on PATH the stand-in is checked for and never runs."""
    binaries = tmp_path / "bin"
    binaries.mkdir()
    fake = binaries / "claude"
    fake.write_text("#!/bin/sh\nexit 0\n")
    fake.chmod(0o755)
    monkeypatch.setenv("PATH", f"{binaries}{os.pathsep}{os.environ['PATH']}")
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    written(tmp_path, "asks", ASKS)
    written(tmp_path, "steers", STEERS)
    return tmp_path


@pytest.fixture
def host(workspace: Path) -> Iterator[Host]:
    held = Hmz().host()
    try:
        yield held
    finally:
        for name in ("start", "go"):
            (workspace / name).write_text("")
        held.close()
        for thread in threading.enumerate():
            if thread.name == "humanize-run":
                thread.join(PATIENCE)


async def _types(app: Humanize, driver: Pilot[None], line: str) -> None:
    """Types one line and sends it, as somebody at the prompt would."""
    app.query_one("#editor").text = line  # pyright: ignore[reportAttributeAccessIssue]
    await driver.press("enter")
    await driver.pause()


def _result(workspace: Path) -> dict[str, Any]:
    deadline = time.monotonic() + PATIENCE
    landed = workspace / "result.json"
    while time.monotonic() < deadline and not landed.exists():
        time.sleep(0.02)
    return json.loads(landed.read_text())


@pytest.mark.timeout(90)
async def test_claims_and_answers_are_drawn_on_both(
    host: Host, workspace: Path
) -> None:
    bob = Bob(host)
    app = Humanize(link=linked(host, "alice", "tui"))
    async with app.run_test() as driver:
        bob.link.start("asks", "the parser", budget={"cost": 1})
        await until(lambda: app._run is not None, driver)
        assert app._run is not None
        assert app._run.by == "bob"
        # Somebody else started it, and what they started it on is on the screen.
        assert "the parser · by bob" in transcript(app)

        app._now_reading("outworlder:planner")
        await _types(app, driver, "/claim")
        await until(lambda: app._claims.get("planner") == app._me, driver)
        bob.link.claim("reviewer")
        await until(lambda: "reviewer" in app._claims, driver)
        assert any(
            "planner · outworlder · yours" in one for one in app._outworlder_lines()
        )
        assert any(
            "reviewer · outworlder · bob's" in one for one in app._outworlder_lines()
        )
        # The monitor lists who else is reading.
        assert app._reading_too() == ["alice · you", "bob"]

        # Bob may not answer the planner, which is alice's; alice answers it from her prompt.
        planning = bob.asked("planner")
        assert planning["owner"] == app._me
        await until(lambda: app._answers_to() is not None, driver)
        await _types(app, driver, "a plan")
        bob.told("answered", role="planner", by="alice", text="a plan")

        # The reviewer is bob's: the interface does not answer it, and says whose it is.
        reviewing = bob.asked("reviewer")
        await until(
            lambda: any(one["role"] == "reviewer" for one in app._pending), driver
        )
        assert app._answers_to() is None
        assert app._waits_on() == "bob"
        app._now_reading("outworlder:reviewer")
        await _types(app, driver, "mine")
        await until(lambda: "reviewer is bob's to answer" in transcript(app), driver)
        bob.link.answer(reviewing["question"], "fine")
        await until(lambda: "fine · by bob" in transcript(app), driver)

        assert _result(workspace) == {"plan": "a plan", "review": "fine"}
        await until(lambda: app._run is None, driver)
    bob.link.close()


@pytest.mark.timeout(90)
async def test_what_each_says_to_an_agent_is_said_by_whom_on_both(
    host: Host, workspace: Path
) -> None:
    bob = Bob(host)
    app = Humanize(link=linked(host, "alice", "tui"))
    async with app.run_test() as driver:
        driver_ = HarnessDriver(
            parse_agents(["coder=claude/m:high"])[0],
            SteerableAgent,
            AgentConfig(model="m", effort="high"),
            None,
        )
        bob.link.start("steers", TURN, agents={"coder": driver_}, budget={"cost": 1})
        (workspace / "start").write_text("")
        await until(lambda: "coder/1" in app._working, driver)

        await _types(app, driver, "from alice")
        bob.told("said", text="from alice", by="alice", key="coder/1")
        bob.link.say("from bob")
        await until(lambda: "from bob · by bob" in transcript(app), driver)
        assert "from alice" in transcript(app)
        assert "from alice · by" not in transcript(app)

        # A stop from either is a stop for both, said with who asked for it.
        bob.link.stop()
        await until(lambda: "bob is stopping the flow" in transcript(app), driver)
        (workspace / "go").write_text("")
        await until(lambda: app._run is None and app._stopping is None, driver)
    bob.link.close()


@pytest.mark.timeout(90)
async def test_leaving_lets_go_of_this_interface_and_not_of_the_run(
    host: Host, workspace: Path
) -> None:
    from hmz.tui.pick import DETACHES, Leaves

    bob = Bob(host)
    app = Humanize(link=linked(host, "alice", "tui"))
    async with app.run_test() as driver:
        bob.link.start("asks", "the parser", budget={"cost": 1})
        await until(lambda: app._run is not None, driver)
        app._now_reading("outworlder:planner")
        await _types(app, driver, "/claim")
        await until(lambda: app._claims.get("planner") == app._me, driver)

        await _types(app, driver, "/exit")
        await until(lambda: isinstance(app.screen, Leaves), driver)
        app.screen.dismiss(DETACHES)
        await until(lambda: not app.is_running, driver)

    # Alice's claim went with her, and the run is still going for bob to answer.
    bob.told("claims", claims={})
    planning = bob.asked("planner")
    assert planning["owner"] is None
    assert host.status()["state"] == "running"
    bob.link.answer(planning["question"], "bob's plan")
    bob.link.answer(bob.asked("reviewer")["question"], "fine")
    assert _result(workspace) == {"plan": "bob's plan", "review": "fine"}
    bob.link.close()
