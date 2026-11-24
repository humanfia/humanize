"""`hmz exec`: a flow run from the command line, with the SDK's daemon client mocked.

What the line itself may say -- which flags, which values -- is the SDK's to read
(`Hmz.read`); what is here is what `hmz exec` does with what was read, and with how the epic
its daemon held ended.
"""

from __future__ import annotations

import errno
import signal
import threading
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any
from unittest import mock

import pytest

import hmz.sdk
from hmz.cli import main
from hmz.flows import BudgetExceeded
from hmz.runtime import Refused

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path


class _Running:
    """A run, doing whatever `does` does when it is run."""

    def __init__(self, does: Callable[[_Running], object] = lambda run: None) -> None:
        self.does = does
        self.blind = ""
        self.watched: list[object] = []
        self.noticing: list[Callable[[str], None]] = []
        self.printing: list[Callable[[str], None]] = []
        self.stopped = threading.Event()
        self.closed = threading.Event()
        #: The epic, once named; none, as before its `run` snapshot, unless a test names one.
        self.epic: Path | None = None

    def watch(self, heard: object) -> None:
        self.watched.append(heard)

    def opened(self, opens: object) -> None:
        del opens

    def printed(self, prints: Callable[[str], None]) -> None:
        self.printing.append(prints)

    def noticed(self, notices: Callable[[str], None]) -> None:
        self.noticing.append(notices)

    def unreadable(self) -> str:
        return self.blind

    def run(self) -> None:
        self.does(self)

    def stop(self) -> None:
        self.stopped.set()

    def wait(self, timeout: float | None = None) -> bool:
        del timeout
        return True

    def close(self) -> None:
        self.closed.set()


_LINE = SimpleNamespace(
    as_json=False,
    flow="ralph_loop",
    task="do the thing",
    agents={"coder": "claude/m:high"},
    envs={"box": "local"},
    params={"rounds": 2},
    budget={"cost": 5.0},
    profile_flow=False,
    profile_environment=False,
    resume=False,
    backup=None,
)


@pytest.fixture
def runtime(monkeypatch: pytest.MonkeyPatch) -> mock.Mock:
    """`hmz.sdk.Hmz`, mocked: reading `_LINE` and running a `_Running`."""
    held = mock.Mock()
    held.read.return_value = _LINE
    held.run.return_value = _Running()
    monkeypatch.setattr(hmz.sdk, "Hmz", mock.Mock(return_value=held), raising=False)
    return held


def test_exec_runs_the_flow_the_line_names(
    runtime: mock.Mock, capsys: pytest.CaptureFixture[str]
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
        profile_flow=False,
        profile_environment=False,
        resume=False,
        backup=None,
    )
    running: _Running = runtime.run.return_value
    assert len(running.watched) == 1
    assert capsys.readouterr().err == ""


def test_what_the_host_printed_is_put_on_stdout(
    runtime: mock.Mock, capsys: pytest.CaptureFixture[str]
) -> None:
    runtime.run.return_value = _Running(lambda run: run.printing[0]("answered"))

    assert main(["exec", "x"]) == 0
    assert capsys.readouterr() == ("answered\n", "")


def test_a_daemon_that_cannot_be_reached_is_said_and_exits_one(
    runtime: mock.Mock, capsys: pytest.CaptureFixture[str]
) -> None:
    runtime.run.side_effect = OSError("no socket")

    with pytest.raises(SystemExit) as raised:
        main(["exec", "x"])
    assert raised.value.code == 1
    assert capsys.readouterr().err == "hmz: the daemon cannot be reached: no socket\n"


def test_a_daemon_of_another_version_is_said_as_it_refused(
    runtime: mock.Mock, capsys: pytest.CaptureFixture[str]
) -> None:
    runtime.run.side_effect = OSError(errno.EADDRINUSE, "held by an older Humanize")

    with pytest.raises(SystemExit) as raised:
        main(["exec", "x"])
    assert raised.value.code == 1
    assert capsys.readouterr().err == "hmz: held by an older Humanize\n"


def test_what_the_run_notices_is_said_aside(
    runtime: mock.Mock, capsys: pytest.CaptureFixture[str]
) -> None:
    def notices(run: _Running) -> None:
        run.noticing[0]("moved to docker")

    running = _Running(notices)
    running.blind = "the agent cannot read this"
    runtime.run.return_value = running
    assert main(["exec", "x"]) == 0
    # What the check answered is the host's to say, as a notice: said here too, it is twice.
    assert capsys.readouterr().err == "hmz exec: moved to docker\n"


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
    runtime: mock.Mock, capsys: pytest.CaptureFixture[str]
) -> None:
    def refuses(run: _Running) -> None:
        raise Refused("box is unreachable")

    runtime.run.return_value = _Running(refuses)
    with pytest.raises(SystemExit) as raised:
        main(["exec", "x"])
    assert raised.value.code == 2
    assert capsys.readouterr().err == "hmz exec: error: box is unreachable\n"


def test_a_spent_budget_is_the_end_of_the_run_not_a_crash(
    runtime: mock.Mock, capsys: pytest.CaptureFixture[str]
) -> None:
    def spends(run: _Running) -> None:
        raise BudgetExceeded("cost 5 spent")

    runtime.run.return_value = _Running(spends)
    assert main(["exec", "x"]) == 0
    assert capsys.readouterr().err == "hmz exec: stopped -- cost 5 spent\n"


def test_a_flow_that_fails_is_said_as_its_host_said_it_and_exits_one(
    runtime: mock.Mock, capsys: pytest.CaptureFixture[str]
) -> None:
    def fails(run: _Running) -> None:
        raise RuntimeError("FlowError: the flow broke")

    runtime.run.return_value = _Running(fails)
    assert main(["exec", "x"]) == 1
    assert capsys.readouterr().err == "FlowError: the flow broke\n"


@pytest.mark.parametrize(
    "stopping", [KeyboardInterrupt, SystemExit(4)], ids=["interrupt", "exit"]
)
def test_somebody_stopping_the_line_is_not_a_failure(
    runtime: mock.Mock, stopping: BaseException | type[BaseException]
) -> None:
    def stops(run: _Running) -> None:
        raise stopping

    runtime.run.return_value = _Running(stops)
    with pytest.raises(SystemExit):
        main(["exec", "x"])


@pytest.mark.parametrize("signum", [signal.SIGTERM, signal.SIGHUP, signal.SIGINT])
def test_a_signal_stops_the_run_and_exits_as_the_signal_would(
    runtime: mock.Mock, signum: int
) -> None:
    running = _Running(lambda run: signal.raise_signal(signum))
    runtime.run.return_value = running
    with pytest.raises(SystemExit) as raised:
        main(["exec", "x"])
    assert raised.value.code == 128 + signum
    assert running.stopped.wait(5)


@pytest.mark.parametrize(
    "failure", [RuntimeError("cancelled"), Refused("cut off")], ids=["crash", "refused"]
)
def test_a_run_that_fails_because_a_signal_stopped_it_exits_as_the_signal(
    runtime: mock.Mock, failure: Exception
) -> None:
    def stopped(run: _Running) -> None:
        signal.raise_signal(signal.SIGTERM)
        raise failure

    runtime.run.return_value = _Running(stopped)
    with pytest.raises(SystemExit) as raised:
        main(["exec", "x"])
    assert raised.value.code == 128 + signal.SIGTERM


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
    runtime.run.return_value = _Running(lambda run: run.printing[0]("a stray line"))
    assert main(["exec", "--json", "x"]) == 0
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == "a stray line\n"


@pytest.fixture
def backing(monkeypatch: pytest.MonkeyPatch) -> list[bool]:
    """`runs.get` saying, at each ask, whether the epic's backups are done: the last for good."""
    import hmz.reach
    import hmz.sdk.client
    import hmz.sdk.running

    said: list[bool] = []

    def backed(client: object, name: str) -> bool:
        del client, name
        return said.pop(0) if len(said) > 1 else said[0]

    monkeypatch.setattr(hmz.reach, "dial", mock.Mock())
    monkeypatch.setattr(hmz.sdk.client, "Client", mock.MagicMock())
    monkeypatch.setattr(hmz.sdk.running, "backed", backed)
    monkeypatch.setattr(hmz.sdk.running, "BACKING", 1.0)
    return said


def test_an_epic_whose_backups_are_done_is_left_at_once(
    runtime: mock.Mock, capsys: pytest.CaptureFixture[str], backing: list[bool]
) -> None:
    from pathlib import Path

    backing.append(True)
    running = runtime.run.return_value = _Running()
    running.epic = Path("/e/20261117T000000.000Z-abcdef")

    assert main(["exec", "x"]) == 0
    assert capsys.readouterr().err == ""
    assert running.closed.is_set()


def test_exec_waits_for_the_backups_of_its_epic(
    runtime: mock.Mock, capsys: pytest.CaptureFixture[str], backing: list[bool]
) -> None:
    from pathlib import Path

    backing.extend([False, True])
    running = runtime.run.return_value = _Running()
    running.epic = Path("/e/20261117T000000.000Z-abcdef")

    assert main(["exec", "x"]) == 0
    assert capsys.readouterr().err == "hmz exec: backing the epic up\n"
    assert running.closed.is_set()


def test_a_backup_not_done_in_time_is_left_saying_so(
    runtime: mock.Mock, capsys: pytest.CaptureFixture[str], backing: list[bool]
) -> None:
    from pathlib import Path

    backing.append(False)
    running = runtime.run.return_value = _Running()
    running.epic = Path("/e/20261117T000000.000Z-abcdef")

    assert main(["exec", "x"]) == 0
    assert capsys.readouterr().err == (
        "hmz exec: backing the epic up\n"
        "hmz exec: a backup took longer than 1s and was left; "
        "`hmz backup run EPIC` sends it again\n"
    )
