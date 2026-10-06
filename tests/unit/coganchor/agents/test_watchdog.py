"""`hmz.coganchor.agents.watchdog`: the clock a turn runs under.

The ladder itself is climbed a tick a second against a real process, which is the integration
suite's to watch; here is everything about the clock a turn can be asked without one.
"""

from __future__ import annotations

import contextlib
from typing import TYPE_CHECKING

import pytest

from hmz.coganchor import backends
from hmz.coganchor.agents.watchdog import WATCHDOG, Watchdog, held, silence
from tests.unit.coganchor.agents.doubles_core import Scripted

if TYPE_CHECKING:
    from collections.abc import Generator


def test_silence_is_what_the_backend_wrote_down(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv(WATCHDOG, raising=False)
    claude = backends.named("claude")
    assert claude is not None
    assert silence("claude") == claude.silence
    assert silence("never-heard-of-it") == backends.UNKNOWN.silence


@pytest.mark.parametrize(("said", "window"), [("12.5", 12.5), ("0", 0.0), ("-1", -1.0)])
def test_the_environment_overrides_every_backend(
    monkeypatch: pytest.MonkeyPatch, said: str, window: float
) -> None:
    monkeypatch.setenv(WATCHDOG, said)
    assert silence("claude") == window


def test_an_unreadable_override_is_ignored(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(WATCHDOG, "soon")
    claude = backends.named("claude")
    assert claude is not None
    assert silence("claude") == claude.silence


@pytest.mark.parametrize("window", [0.0, 3600.0])
def test_a_quiet_turn_that_ends_on_its_own_is_left_alone(window: float) -> None:
    session = Scripted().new()
    with Watchdog(session, window=window) as watch:
        watch.saw()
        with watch.held(), watch.held():
            watch.saw()
        assert watch.wedged() is None
    assert watch.wedged() is None


def test_what_the_turn_raised_is_what_comes_out() -> None:
    session = Scripted().new()
    with pytest.raises(OSError, match="pipe"), Watchdog(session, window=3600.0):
        raise OSError("pipe")


def test_held_stops_every_running_clock_of_an_agent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stopped: list[Watchdog] = []
    holds = Watchdog.held

    @contextlib.contextmanager
    def holding(self: Watchdog) -> Generator[None]:
        stopped.append(self)
        with holds(self):
            yield

    monkeypatch.setattr(Watchdog, "held", holding)
    agent = Scripted()
    first, second, _idle = agent.new(), agent.new(), agent.new()
    with (
        Watchdog(first, window=3600.0) as ticking,
        Watchdog(second, window=0.0),  # a clock turned off is not running
        held(agent),
    ):
        assert stopped == [ticking]
    with held(Scripted()):
        pass
    assert stopped == [ticking]
