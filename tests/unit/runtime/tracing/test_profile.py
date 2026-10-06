from __future__ import annotations

import json
import types
from typing import TYPE_CHECKING, Any

import psutil
import pytest

from hmz.runtime.tracing import profile
from hmz.runtime.tracing.profile import PROFILE, Process, Profiler, Thread, read
from tests.unit.runtime.tracing.logs import jsonl

if TYPE_CHECKING:
    from pathlib import Path

NOW = 1_000.0


def line(pid: int, began: float, **extra: Any) -> dict[str, Any]:
    return {
        "event": "ran",
        "pid": pid,
        "ppid": 1,
        "name": f"p{pid}",
        "began": began,
        **extra,
    }


def test_label_names_the_program_and_which_one() -> None:
    assert Process(7, 1, "make", (), 0.0, 1.0).label == "make · 7"


def test_read_takes_the_last_word_on_each_program(tmp_path: Path) -> None:
    path = jsonl(
        tmp_path / PROFILE,
        [
            line(2, 20.0, argv=["b", 1], ended=21.0),
            line(1, 10.0, ended=11.0, threads=[[1, 10.0, 11.0, 0.5], [9, 9]]),
            line(1, 10.0, ended=15.0, event="left"),
            "{torn",
            "[1]",
            {"pid": 3},  # no start
            {"pid": "x", "began": 1.0},
        ],
    )
    assert read(path) == read(tmp_path)  # the epic that holds it reads the same
    first, second = read(path)
    assert first == Process(1, 1, "p1", (), 10.0, 15.0)
    assert second == Process(2, 1, "p2", ("b", "1"), 20.0, 21.0)


def test_read_keeps_threads_whole(tmp_path: Path) -> None:
    jsonl(tmp_path / PROFILE, [line(1, 10.0, threads=[[1, 10.0, 11.0, 0.5], [2, 3]])])
    [one] = read(tmp_path)
    assert one.threads == (Thread(1, 10.0, 11.0, 0.5),)
    assert one.ended == 10.0  # never said to have ended: ended where it began


def test_read_lines_starts_up_with_the_clock(tmp_path: Path) -> None:
    jsonl(
        tmp_path / PROFILE,
        [
            line(1, 10.0, seen=10.4, ended=30.0),
            line(2, 20.0, seen=20.3, ended=20.1),  # smallest gap, 0.3
            line(3, 25.0, ended=26.0),  # never seen sampled: left alone
        ],
    )
    held = {one.pid: one for one in read(tmp_path)}
    assert held[1].began == pytest.approx(10.3)
    assert held[2].began == 20.1  # no later than it ended
    assert held[3].began == 25.0


def test_read_does_not_move_starts_backwards(tmp_path: Path) -> None:
    jsonl(tmp_path / PROFILE, [line(1, 10.0, seen=9.0, ended=12.0)])
    assert read(tmp_path)[0].began == 10.0


def test_read_of_no_profile_is_nothing(tmp_path: Path) -> None:
    assert read(tmp_path) == []
    assert read(tmp_path / "missing.jsonl") == []


class FakeThread(types.SimpleNamespace):
    id: int
    user_time: float
    system_time: float


class FakeProcess:
    def __init__(self, pid: int, *, threads: bool = True, gone: bool = False) -> None:
        self.pid = pid
        self.has_threads = threads
        self.gone = gone

    def create_time(self) -> float:
        if self.gone:
            raise psutil.NoSuchProcess(self.pid)
        return NOW - self.pid

    def ppid(self) -> int:
        return 1

    def name(self) -> str:
        return f"proc{self.pid}"

    def cmdline(self) -> list[str]:
        return [f"proc{self.pid}", "--flag"]

    def threads(self) -> list[FakeThread]:
        if not self.has_threads:
            raise NotImplementedError
        return [FakeThread(id=self.pid, user_time=1.0, system_time=0.5)]


def fake_psutil(
    monkeypatch: pytest.MonkeyPatch, sightings: list[list[FakeProcess]]
) -> None:
    """Each look under the root sees the next of `sightings`, then the last one forever."""
    looks = iter(sightings)
    last: list[list[FakeProcess]] = [[]]

    class Root:
        def __init__(self, pid: int | None) -> None:
            assert pid == 1

        def children(self, *, recursive: bool) -> list[FakeProcess]:
            assert recursive
            last[0] = next(looks, last[0])
            return last[0]

    monkeypatch.setattr(
        profile, "psutil", types.SimpleNamespace(Process=Root, Error=psutil.Error)
    )
    monkeypatch.setattr(profile, "time", types.SimpleNamespace(time=lambda: NOW))


def written(path: Path) -> list[tuple[str, int]]:
    return [
        (said["event"], said["pid"])
        for said in map(json.loads, path.read_text().splitlines())
    ]


def test_profiler_writes_what_ran_and_when_it_left(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    stays, goes = FakeProcess(3), FakeProcess(5, threads=False)
    fake_psutil(monkeypatch, [[stays, goes, FakeProcess(9, gone=True)], [stays]])
    at = tmp_path / "epic" / PROFILE
    profiler = Profiler(at, root=1)
    profiler.start()
    profiler.start()  # already sampling: nothing more
    profiler.stop()

    assert written(at) == [("ran", 3), ("ran", 5), ("left", 5), ("left", 3)]
    said = json.loads(at.read_text().splitlines()[0])
    assert (said["began"], said["seen"]) == (NOW - 3, NOW)
    held = {one.pid: one for one in read(at)}
    assert set(held) == {3, 5}
    # read back, each start is moved by the smallest gap between starting and being seen
    assert held[3] == Process(
        pid=3,
        ppid=1,
        name="proc3",
        argv=("proc3", "--flag"),
        began=NOW,
        ended=NOW,
        threads=(Thread(3, NOW, NOW, 1.5),),
        seen=NOW,
    )
    assert held[5].threads == ()
    assert held[5].began == NOW - 2


def test_profiler_with_nothing_under_it_writes_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class Gone:
        def __init__(self, pid: int | None) -> None:
            raise psutil.NoSuchProcess(pid or 0)

    monkeypatch.setattr(
        profile, "psutil", types.SimpleNamespace(Process=Gone, Error=psutil.Error)
    )
    at = tmp_path / PROFILE
    profiler = Profiler(at, root=1)
    profiler.start()
    profiler.stop()
    profiler.stop()  # stopping twice is harmless
    assert not at.exists()
    assert read(at) == []
