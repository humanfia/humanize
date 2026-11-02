"""`hmz.web.places`: what each host runs, as the pages are told it."""

from __future__ import annotations

import threading
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any, cast

from hmz import daemon
from hmz.web import places
from hmz.web.places import Places

if TYPE_CHECKING:
    from pathlib import Path

    import pytest

    from hmz.web.held import Held


class _Looks:
    """An event that says it is not set as often as told, then that it is, at once."""

    def __init__(self, rounds: int) -> None:
        self._rounds = rounds

    def wait(self, _: float) -> bool:
        self._rounds -= 1
        return self._rounds < 0

    def set(self) -> None:
        self._rounds = 0


class _Inline:
    """A thread that runs where it is started."""

    def __init__(self, target: Any, **_: Any) -> None:
        self._target = target

    def start(self) -> None:
        self._target()


def _places(
    monkeypatch: pytest.MonkeyPatch, here: Path, *, apart: bool, rounds: int = 0
) -> Places:
    """Places, its daemon a stand-in, looking at the daemon `rounds` times as it is made."""

    def hmz(at: Path) -> SimpleNamespace:
        return SimpleNamespace(at=at)

    monkeypatch.setattr(daemon, "Hmz", hmz)
    monkeypatch.setattr(
        places,
        "threading",
        SimpleNamespace(
            Lock=threading.Lock, Event=lambda: _Looks(rounds), Thread=_Inline
        ),
    )
    return Places(here, apart=apart)


class _Link:
    """A link held to a host, saying what stands."""

    def __init__(self, **standing: dict[str, Any]) -> None:
        self._standing = standing

    def standing(self, kind: str) -> dict[str, Any] | None:
        return self._standing.get(kind)


def test_a_host_held_here_says_the_questions_it_waits_on(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    found = _places(monkeypatch, tmp_path, apart=False)
    run = {"state": "running", "run": 3, "flow": "chat", "turn": "done"}
    asked = [{"question": "q7", "run": 3}, {"question": "q8", "run": 3}]
    held = found.of(str(tmp_path)).held
    held["chat:1"] = cast(
        "Held", _Link(run=run, pending={"type": "pending", "pending": asked})
    )
    held[""] = cast("Held", _Link(run={"state": "running", "run": 1, "flow": "ralph"}))

    said = {one["slot"]: one for one in found.running()}

    assert said["chat:1"]["asking"] == ["3:q7", "3:q8"]
    assert said["chat:1"]["turn"] == "done"
    assert said[""]["asking"] == []


def test_a_host_the_daemon_holds_says_the_questions_it_waits_on(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    status = {
        "state": "running",
        "run": 4,
        "flow": "ralph",
        "pending": [{"question": "q2", "role": "human", "text": "?", "mode": "ask"}],
    }
    host = SimpleNamespace(workspace=str(tmp_path), slot="", status=lambda: status)
    monkeypatch.setattr(daemon, "daemons", lambda: [host])

    found = _places(monkeypatch, tmp_path, apart=True, rounds=1)

    (said,) = found.running()
    assert (said["run"], said["asking"]) == (4, ["4:q2"])
