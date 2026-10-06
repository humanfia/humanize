"""`hmz exec`: a flow run from the command line, with the runtime mocked.

What the line itself may say -- which flags, which values -- is the runtime's to read
(`Hmz.read`); what is here is what `hmz exec` does with what was read, and with how the run
ended.
"""

from __future__ import annotations

import signal
import sys
import threading
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any
from unittest import mock

import pytest

import hmz.runtime
from hmz.cli import main
from hmz.flows import BudgetExceeded
from hmz.runtime import Refused, telemetry

if TYPE_CHECKING:
    from collections.abc import Callable


class _Running:
    """A run, doing whatever `does` does when it is run."""

    def __init__(self, does: Callable[[_Running], object] = lambda run: None) -> None:
        self.does = does
        self.blind = ""
        self.watched: list[object] = []
        self.noticing: list[Callable[[str], None]] = []
        self.stopped = threading.Event()

    def watch(self, heard: object) -> None:
        self.watched.append(heard)

    def noticed(self, notices: Callable[[str], None]) -> None:
        self.noticing.append(notices)

    def unreadable(self) -> str:
        return self.blind

    def run(self) -> None:
        self.does(self)

    def stop(self) -> None:
        self.stopped.set()


_LINE = SimpleNamespace(
    as_json=False,
    flow="ralph_loop",
    task="do the thing",
    agents={"coder": "claude/m:high"},
    envs={"box": "local"},
    params={"rounds": 2},
    budget={"cost": 5.0},
    profile=False,
    resume=False,
)


@pytest.fixture
def runtime(monkeypatch: pytest.MonkeyPatch) -> mock.Mock:
    """`hmz.runtime.Hmz`, mocked: reading `_LINE` and running a `_Running`."""
    held = mock.Mock()
    held.read.return_value = _LINE
    held.run.return_value = _Running()
    monkeypatch.setattr(hmz.runtime, "Hmz", mock.Mock(return_value=held))
    return held


@pytest.fixture
def crash(monkeypatch: pytest.MonkeyPatch) -> mock.Mock:
    """What a crash would be reported with."""
    reports = mock.Mock()
    monkeypatch.setattr(telemetry, "crash", reports)
    return reports


def test_exec_runs_the_flow_the_line_names(
    runtime: mock.Mock, crash: mock.Mock, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["exec", "-f", "ralph_loop", "do the thing"]) == 0
    runtime.reports.assert_called_once_with()
    runtime.read.assert_called_once_with(["-f", "ralph_loop", "do the thing"])
    runtime.run.assert_called_once_with(
        "ralph_loop",
        "do the thing",
        agents={"coder": "claude/m:high"},
        envs={"box": "local"},
        params={"rounds": 2},
        budget={"cost": 5.0},
        profile=False,
        resume=False,
    )
    running: _Running = runtime.run.return_value
    assert len(running.watched) == 1
    assert capsys.readouterr().err == ""
    crash.assert_not_called()


def test_what_the_run_notices_is_said_aside(
    runtime: mock.Mock, capsys: pytest.CaptureFixture[str]
) -> None:
    def notices(run: _Running) -> None:
        run.noticing[0]("moved to docker")

    running = _Running(notices)
    running.blind = "the agent cannot read this"
    runtime.run.return_value = running
    assert main(["exec", "x"]) == 0
    assert capsys.readouterr().err == (
        "hmz exec: the agent cannot read this\nhmz exec: moved to docker\n"
    )


def test_a_line_that_cannot_be_read_exits_as_the_reading_does(
    runtime: mock.Mock,
) -> None:
    runtime.read.side_effect = SystemExit(2)
    with pytest.raises(SystemExit) as raised:
        main(["exec", "--bogus"])
    assert raised.value.code == 2
    runtime.run.assert_not_called()


def test_an_interrupt_before_the_run_exits_without_a_traceback(
    runtime: mock.Mock,
) -> None:
    runtime.read.side_effect = KeyboardInterrupt
    with pytest.raises(SystemExit) as raised:
        main(["exec", "x"])
    assert raised.value.code == 128 + signal.SIGINT


def test_a_flow_refused_before_it_runs_is_a_bad_line(
    runtime: mock.Mock, capsys: pytest.CaptureFixture[str]
) -> None:
    runtime.run.side_effect = Refused("no flow called nope")
    with pytest.raises(SystemExit) as raised:
        main(["exec", "-f", "nope", "x"])
    assert raised.value.code == 2
    assert capsys.readouterr().err == "hmz exec: error: no flow called nope\n"


def test_an_environment_refused_once_asked_is_a_bad_line(
    runtime: mock.Mock, crash: mock.Mock, capsys: pytest.CaptureFixture[str]
) -> None:
    def refuses(run: _Running) -> None:
        raise Refused("box is unreachable")

    runtime.run.return_value = _Running(refuses)
    with pytest.raises(SystemExit) as raised:
        main(["exec", "x"])
    assert raised.value.code == 2
    assert capsys.readouterr().err == "hmz exec: error: box is unreachable\n"
    crash.assert_not_called()


def test_a_spent_budget_is_the_end_of_the_run_not_a_crash(
    runtime: mock.Mock, crash: mock.Mock, capsys: pytest.CaptureFixture[str]
) -> None:
    def spends(run: _Running) -> None:
        raise BudgetExceeded("cost 5 spent")

    runtime.run.return_value = _Running(spends)
    assert main(["exec", "x"]) == 0
    assert capsys.readouterr().err == "hmz exec: stopped -- cost 5 spent\n"
    crash.assert_not_called()


def test_a_flow_that_fails_is_reported_and_raised_as_it_was(
    runtime: mock.Mock, crash: mock.Mock
) -> None:
    failure = RuntimeError("the flow broke")

    def fails(run: _Running) -> None:
        raise failure

    runtime.run.return_value = _Running(fails)
    with pytest.raises(RuntimeError) as raised:
        main(["exec", "x"])
    assert raised.value is failure
    crash.assert_called_once_with(failure, doing="hmz exec")


@pytest.mark.parametrize(
    "stopping", [KeyboardInterrupt, SystemExit(4)], ids=["interrupt", "exit"]
)
def test_somebody_stopping_the_run_is_not_reported(
    runtime: mock.Mock, crash: mock.Mock, stopping: BaseException | type[BaseException]
) -> None:
    def stops(run: _Running) -> None:
        raise stopping

    runtime.run.return_value = _Running(stops)
    with pytest.raises((KeyboardInterrupt, SystemExit)):
        main(["exec", "x"])
    crash.assert_not_called()


@pytest.mark.parametrize("signum", [signal.SIGTERM, signal.SIGHUP, signal.SIGINT])
def test_a_signal_stops_the_run_and_exits_as_the_signal_would(
    runtime: mock.Mock, crash: mock.Mock, signum: int
) -> None:
    running = _Running(lambda run: signal.raise_signal(signum))
    runtime.run.return_value = running
    with pytest.raises(SystemExit) as raised:
        main(["exec", "x"])
    assert raised.value.code == 128 + signum
    assert running.stopped.wait(5)
    crash.assert_not_called()


@pytest.mark.parametrize(
    "failure", [RuntimeError("cancelled"), Refused("cut off")], ids=["crash", "refused"]
)
def test_a_run_that_fails_because_a_signal_stopped_it_exits_as_the_signal(
    runtime: mock.Mock, crash: mock.Mock, failure: Exception
) -> None:
    def stopped(run: _Running) -> None:
        signal.raise_signal(signal.SIGTERM)
        raise failure

    runtime.run.return_value = _Running(stopped)
    with pytest.raises(SystemExit) as raised:
        main(["exec", "x"])
    assert raised.value.code == 128 + signal.SIGTERM
    crash.assert_not_called()


def test_a_signal_somebody_chose_to_ignore_stays_ignored(
    runtime: mock.Mock, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen: list[Any] = []
    runtime.run.return_value = _Running(
        lambda run: seen.append(signal.getsignal(signal.SIGHUP))
    )
    was = signal.signal(signal.SIGHUP, signal.SIG_IGN)
    try:
        assert main(["exec", "x"]) == 0
    finally:
        signal.signal(signal.SIGHUP, was)
    assert seen == [signal.SIG_IGN]
    del monkeypatch


def test_json_keeps_stdout_for_objects(
    runtime: mock.Mock, capsys: pytest.CaptureFixture[str]
) -> None:
    runtime.read.return_value = SimpleNamespace(**{**vars(_LINE), "as_json": True})
    runtime.run.return_value = _Running(lambda run: sys.stdout.write("a stray line\n"))
    assert main(["exec", "--json", "x"]) == 0
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == "a stray line\n"
