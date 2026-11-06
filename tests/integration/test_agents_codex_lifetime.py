"""Codex app servers owned through account changes, failed starts, cuts and concurrent stops."""

from __future__ import annotations

import contextlib
import gc
import threading
import time
import weakref
from dataclasses import replace
from pathlib import Path
from typing import TYPE_CHECKING

import psutil
import pytest

from hmz.coganchor.agents import (
    AgentBase,
    CodexAgent,
    Event,
    Failed,
    SessionBase,
    Stopped,
)
from hmz.coganchor.homes import Home
from tests.integration.doubles_agents import Standins, standins
from tests.integration.test_agents_codex import CODEX, CONFIG

if TYPE_CHECKING:
    from hmz.coganchor.homes import Virtual


@pytest.fixture
def codex(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Standins:
    held = standins(tmp_path, monkeypatch, "CODEX_HOME")
    held.install("codex", CODEX)
    return held


def _reaped(codex: Standins) -> None:
    """Every launched stand-in and its process home are gone."""
    launches = codex.calls()
    assert launches
    for launch in launches:
        assert not psutil.pid_exists(launch.pid)
        at = launch.env["CODEX_HOME"]
        assert at is not None
        assert not Path(at).exists()


def _killed(codex: Standins) -> None:
    """Whatever stand-in a failing test left running, taken down."""
    for launch in codex.calls():
        with contextlib.suppress(psutil.NoSuchProcess):
            process = psutil.Process(launch.pid)
            process.kill()
            process.wait(10)


def _moved(agent: CodexAgent) -> None:
    """The agent's server, said to be on an account the agent has since left.

    What an account falling back leaves behind, without a second account to sign into: a
    named one is read through a credential map that only a Linux host can lay down.
    """
    server = agent.server
    server.knows = ("an account left", *server.knows[1:])


def test_stopping_an_agent_also_reaps_account_detached_servers(
    codex: Standins,
) -> None:
    agent = CodexAgent(CONFIG)
    first = agent.server
    _moved(agent)
    second = agent.server
    assert first is not second
    try:
        agent.stop()
        _reaped(codex)
    finally:
        _killed(codex)


def test_a_cut_ends_a_turn_on_a_server_dispatch_has_let_go_of(
    codex: Standins,
) -> None:
    """A cut puts down every server the agent owns, one an account change let go of included."""
    codex.install(
        "codex",
        CODEX.replace(
            '    if said == "hang":\n',
            """    if said == "hold":
        item("started", thread, id="c-1", type="commandExecution", status="inProgress",
             command="sleep 600")
        time.sleep(600)
    if said == "hang":
""",
        ),
    )
    agent = CodexAgent(CONFIG)
    session = agent.new()
    running, ended = threading.Event(), threading.Event()
    said: list[str] = []

    def taking() -> None:
        # Ended as a cut turn ends, on one result of what had been said: anything raised
        # instead leaves `ended` unset, and the test fails on it.
        for event in session.stream("hold"):
            if event.kind == "tool":
                running.set()
            elif event.kind == "result":
                said.append(event.text)
        ended.set()

    turn = threading.Thread(target=taking, daemon=True)
    turn.start()
    try:
        assert running.wait(10)
        # The account moves on: the server the turn runs on is let go of from dispatch.
        _moved(agent)
        _ = agent.server
        session.cut(why="the flow cut the conversation off")
        assert ended.wait(10)
        assert said == [""]
        _reaped(codex)
    finally:
        agent.stop()
        _killed(codex)
        turn.join(10)


def test_a_cut_before_the_turn_has_a_server_ends_it_before_anything_is_sent(
    codex: Standins,
) -> None:
    """A cut that lands before there is a server to put down still ends the turn it was for."""
    agent = CodexAgent(CONFIG)
    session = agent.new()

    def cutting(_agent: AgentBase, whose: SessionBase | None, event: Event) -> None:
        if whose is session and event.kind == "begins":
            session.cut(why="the flow cut the conversation off")

    agent.watch(cutting)
    try:
        said = [
            one.text for one in session.stream("never sent") if one.kind == "result"
        ]
        assert said == [""]
        assert "never sent" not in codex.said()
    finally:
        agent.stop()


def test_a_start_finishing_after_stop_is_reaped_and_refused(
    codex: Standins, monkeypatch: pytest.MonkeyPatch
) -> None:
    agent = CodexAgent(CONFIG)
    entered, released = threading.Event(), threading.Event()
    spawn = agent.spawned
    failures: list[Failed] = []
    homes: list[Path] = []

    def paused(
        argv: list[str],
        cwd: str = "",
        home: Home | None = None,
        virtual: Virtual | None = None,
    ) -> list[str]:
        assert home is not None
        homes.append(home.at)
        entered.set()
        assert released.wait(10)
        return spawn(argv, cwd, home, virtual)

    def starting() -> None:
        try:
            _ = agent.server
        except Failed as error:
            failures.append(error)

    monkeypatch.setattr(agent, "spawned", paused)
    worker = threading.Thread(target=starting)
    worker.start()
    try:
        assert entered.wait(10)
        agent.stop()
        released.set()
        worker.join(10)
        assert not worker.is_alive()
        assert len(failures) == 1
        assert homes
        assert all(not home.exists() for home in homes)
        if codex.calls():
            _reaped(codex)
    finally:
        released.set()
        worker.join(10)
        agent.stop()
        _killed(codex)


def test_owner_stop_joins_a_retired_servers_in_progress_writeback(
    codex: Standins, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A retired server already going down is still waited for when its agent stops."""
    agent = CodexAgent(CONFIG)
    old = agent.server
    old.share()
    agent.reconfigure(replace(CONFIG, web_search=False))
    assert agent.server is not old
    entered, released, joined = (threading.Event() for _ in range(3))
    drop, stop = Home.drop, old.stop

    def flushing(home: Home) -> None:
        if home is old.home:
            entered.set()
            assert released.wait(10)
        drop(home)

    def stopping() -> None:
        if entered.is_set():
            joined.set()
        stop()

    monkeypatch.setattr(Home, "drop", flushing)
    monkeypatch.setattr(old, "stop", stopping)
    draining = threading.Thread(target=old.give)
    closing = threading.Thread(target=agent.stop)
    draining.start()
    try:
        assert entered.wait(10)
        _ = agent.server
        closing.start()
        assert joined.wait(5)
        assert closing.is_alive()
    finally:
        released.set()
        draining.join(10)
        if closing.ident is not None:
            closing.join(10)
        agent.stop()
    assert not draining.is_alive()
    assert not closing.is_alive()


def test_a_refused_introduction_reaps_the_process_before_dropping_its_home(
    codex: Standins,
) -> None:
    codex.install(
        "codex",
        r"""
note()
for line in sys.stdin:
    request = json.loads(line)
    out({"id": request["id"], "error": {"code": -32600, "message": "refused"}})
""",
    )
    agent = CodexAgent(CONFIG)
    try:
        with pytest.raises(Failed, match="refused"):
            _ = agent.server
        _reaped(codex)
    finally:
        agent.stop()
        _killed(codex)


def test_stop_reaps_a_transport_waiting_for_its_initialization_response(
    codex: Standins, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A starting server is owned before it waits on its introduction."""
    initializing = tmp_path / "initializing"
    monkeypatch.setenv("HMZ_TEST_INITIALIZING", str(initializing))
    codex.install(
        "codex",
        r"""
note()
request = json.loads(sys.stdin.readline())
assert request["method"] == "initialize"
pathlib.Path(os.environ["HMZ_TEST_INITIALIZING"]).touch()
sys.stdin.read()
""",
    )
    agent = CodexAgent(CONFIG)
    failures: list[Failed] = []

    def starting() -> None:
        try:
            _ = agent.server
        except Failed as error:
            failures.append(error)

    worker = threading.Thread(target=starting)
    worker.start()
    try:
        deadline = time.monotonic() + 10
        while not initializing.exists():
            assert time.monotonic() < deadline
            time.sleep(0.01)
        agent.stop()
        worker.join(10)
        assert not worker.is_alive()
        assert len(failures) == 1
        _reaped(codex)
    finally:
        agent.stop()
        _killed(codex)
        worker.join(10)


def test_stop_ends_a_turn_whose_server_it_cut_off_mid_message(
    codex: Standins,
) -> None:
    """A message a stop cuts off is passed over, and the turn hears the stream has ended."""
    codex.install(
        "codex",
        CODEX.replace(
            '    if said == "hang":\n',
            """    if said == "cut":
        # A command, and the start of the message after it, in one write: by the time the
        # command is heard, the server is partway through a message it never finishes.
        with writing:
            sys.stdout.write(json.dumps({"method": "item/started", "params": {
                "threadId": thread, "turnId": "turn-1", "item": {
                    "id": "c-1", "type": "commandExecution", "status": "inProgress",
                    "command": "echo cut"}}}) + '\\n{"method": "item/completed", "params": {')
            sys.stdout.flush()
            time.sleep(600)
    if said == "hang":
""",
        ),
    )
    agent = CodexAgent(CONFIG)
    session = agent.new()
    stopped: list[Stopped] = []

    def taking() -> None:
        try:
            for event in session.stream("cut"):
                if event.kind == "tool":
                    agent.stop()
        except Stopped as said:
            stopped.append(said)

    turn = threading.Thread(target=taking, daemon=True)
    turn.start()
    try:
        turn.join(30)
        assert not turn.is_alive()
        assert len(stopped) == 1
        _reaped(codex)
    finally:
        agent.stop()
        _killed(codex)


def test_stopped_servers_are_released_and_collection_still_stops_live_ones(
    codex: Standins,
) -> None:
    """A server put down is let go of, while the agent's collection still stops the rest."""
    agent = CodexAgent(CONFIG)
    owner = weakref.ref(agent)
    first = agent.server
    old = weakref.ref(first)
    released = threading.Event()
    weakref.finalize(first, released.set)
    try:
        agent.reconfigure(replace(CONFIG, web_search=False))
        second = agent.server
        assert second is not first
        assert agent.server is second
        del first, second
        gc.collect()
        assert released.wait(10)
        assert old() is None
        del agent
        gc.collect()
        assert owner() is None
        _reaped(codex)
    finally:
        if remaining := owner():
            remaining.stop()
        _killed(codex)
