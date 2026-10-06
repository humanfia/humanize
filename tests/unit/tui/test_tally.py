"""`hmz.tui.tally`: what a run has cost, read from the logs the agents keep for themselves."""

from __future__ import annotations

import json
import threading
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, cast

import pytest

from hmz.coganchor import backends
from hmz.tui.tally import Seen, Tally, reported

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping
    from pathlib import Path

    from hmz.tui.monitor import Monitor


@dataclass
class _Profile:
    """A backend as `hmz.coganchor.backends` describes one: where it logs, and how."""

    name: str
    home: Path

    def directory(self) -> Path:
        return self.home

    def logged(self, ident: str) -> tuple[str, ...]:
        return (f"{ident}.jsonl", f"sub/{ident}-*.jsonl")


@dataclass
class _Told:
    """What a tally tells the monitor, kept to be read back."""

    reports: dict[str, frozenset[str]] = field(
        default_factory=dict[str, frozenset[str]]
    )
    totals: dict[str, tuple[int, dict[str, float] | None]] = field(
        default_factory=dict[str, tuple[int, dict[str, float] | None]]
    )
    sources: set[str] = field(default_factory=set[str])
    landed: threading.Event = field(default_factory=threading.Event)

    def reporting(self, agent: str, kinds: Iterable[str]) -> None:
        self.reports[agent] = frozenset(kinds)

    def counted(
        self,
        source: str,
        model: str,
        total: int,
        now: float | None = None,
        kinds: Mapping[str, float] | None = None,
    ) -> None:
        self.sources.add(source)
        self.totals[model] = (total, dict(kinds) if kinds is not None else None)
        self.landed.set()


@pytest.fixture
def home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Where every backend here logs, with `backends.named` answering for them."""
    where = tmp_path / "logs"
    where.mkdir()
    known = {"claude", "codex", "dsh", "kimi", "mcode", "litellm"}

    def named(backend: str) -> _Profile | None:
        return _Profile(backend, where) if backend in known else None

    monkeypatch.setattr(backends, "named", named)
    return where


@pytest.fixture
def told() -> _Told:
    return _Told()


def _tally(told: _Told, *sessions: Seen) -> Tally:
    return Tally(list(sessions), cast("Monitor", told))


def _write(path: Path, *rows: object, partial: str = "") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as stream:
        for row in rows:
            stream.write((row if isinstance(row, str) else json.dumps(row)) + "\n")
        stream.write(partial)


def _claude(
    message: str | None,
    usage: dict[str, int],
    model: str = "opus",
    at: str | None = None,
) -> dict[str, Any]:
    row: dict[str, Any] = {"message": {"id": message, "model": model, "usage": usage}}
    if at is not None:
        row["timestamp"] = at
    return row


@pytest.mark.parametrize(
    ("backend", "kinds"),
    [
        ("claude", {"input", "output", "cache_read", "cache_write"}),
        ("codex", {"input", "output", "cache_read"}),
        ("dsh", {"input", "output", "cache_read", "cache_write"}),
        ("nobody", set[str]()),
    ],
)
def test_reported_says_the_kinds_a_backend_log_holds(
    backend: str, kinds: set[str]
) -> None:
    assert reported(backend) == kinds


def test_a_session_whose_logs_are_not_there_tells_nothing(
    home: Path, told: _Told
) -> None:
    tally = _tally(told, Seen("builder", "claude", "opus", idents=frozenset({"s1"})))

    tally.read()

    assert told.reports == {}
    assert told.totals == {}


def test_a_backend_nobody_knows_is_skipped(home: Path, told: _Told) -> None:
    _write(home / "s1.jsonl", _claude("m1", {"input_tokens": 5}))
    tally = _tally(told, Seen("x", "unknown", "m", idents=frozenset({"s1"})))

    tally.read()

    assert told.totals == {}


def test_claude_spending_is_read_by_kind_and_said_as_read(
    home: Path, told: _Told
) -> None:
    _write(
        home / "s1.jsonl",
        _claude(
            "m1",
            {
                "input_tokens": 10,
                "output_tokens": 20,
                "cache_read_input_tokens": 30,
                "cache_creation_input_tokens": 40,
            },
        ),
        {"type": "user"},
    )
    tally = _tally(
        told,
        Seen(
            "builder",
            "claude",
            "opus",
            counts=frozenset({"reasoning"}),
            idents=frozenset({"s1"}),
        ),
    )

    tally.read()

    assert told.sources == {"read"}
    assert told.totals == {
        "opus": (
            100,
            {"input": 10.0, "output": 20.0, "cache_read": 30.0, "cache_write": 40.0},
        )
    }
    assert told.reports == {"builder": reported("claude") | {"reasoning"}}


def test_a_claude_message_said_on_several_rows_is_counted_once(
    home: Path, told: _Told
) -> None:
    usage = {"input_tokens": 10, "output_tokens": 5}
    _write(home / "s1.jsonl", _claude("m1", usage), _claude("m1", usage))
    # A fork writes the conversation it was cut from again, under its own name.
    _write(home / "s2.jsonl", _claude("m1", usage))
    tally = _tally(told, Seen("a", "claude", "opus", idents=frozenset({"s1", "s2"})))

    tally.read()

    assert told.totals["opus"][0] == 15


def test_a_claude_message_said_again_with_more_adds_only_the_more(
    home: Path, told: _Told
) -> None:
    _write(
        home / "s1.jsonl",
        _claude("m1", {"output_tokens": 5}),
        _claude("m1", {"output_tokens": 8}),
    )
    tally = _tally(told, Seen("a", "claude", "opus", idents=frozenset({"s1"})))

    tally.read()

    assert told.totals["opus"] == (8, {"output": 8.0})


def test_a_sub_agent_on_another_model_is_counted_as_itself(
    home: Path, told: _Told
) -> None:
    _write(
        home / "s1.jsonl",
        _claude("m1", {"output_tokens": 5}),
        _claude("m2", {"output_tokens": 7}, model="haiku"),
        _claude("m3", {"output_tokens": 1}, model=""),
    )
    tally = _tally(told, Seen("a", "claude", "opus", idents=frozenset({"s1"})))

    tally.read()

    assert {model: total for model, (total, _) in told.totals.items()} == {
        "opus": 6,
        "haiku": 7,
    }


def test_only_what_was_appended_is_read_again_and_a_half_row_waits(
    home: Path, told: _Told
) -> None:
    log = home / "s1.jsonl"
    _write(log, _claude("m1", {"output_tokens": 5}), partial='{"message": {"id"')
    tally = _tally(told, Seen("a", "claude", "opus", idents=frozenset({"s1"})))
    tally.read()
    assert told.totals["opus"][0] == 5

    with log.open("a") as stream:
        stream.write(': "m2", "usage": {"output_tokens": 3}}}\n')
    tally.read()

    assert told.totals["opus"][0] == 8


def test_rows_that_are_not_rows_are_skipped(home: Path, told: _Told) -> None:
    _write(
        home / "s1.jsonl",
        "not json",
        "[1, 2]",
        _claude("m1", {"output_tokens": 0}),
        _claude("m2", {"output_tokens": 4}),
    )
    tally = _tally(told, Seen("a", "claude", "opus", idents=frozenset({"s1"})))

    tally.read()

    assert told.totals == {"opus": (4, {"output": 4.0})}


@pytest.mark.parametrize(
    "at",
    [
        "2020-01-01T00:00:00Z",
        "2020-01-01T00:00:00",
    ],
)
def test_rows_from_before_the_session_was_opened_are_not_this_runs(
    home: Path, told: _Told, at: str
) -> None:
    _write(
        home / "s1.jsonl",
        _claude("old", {"output_tokens": 100}, at=at),
        _claude("new", {"output_tokens": 7}, at="2030-01-01T00:00:00+00:00"),
        _claude("unplaced", {"output_tokens": 1}, at="not a time"),
    )
    tally = _tally(
        told,
        Seen("a", "claude", "opus", idents=frozenset({"s1"}), since=1_700_000_000.0),
    )

    tally.read()

    assert told.totals["opus"][0] == 8


def test_codex_takes_cached_reads_out_of_its_input(home: Path, told: _Told) -> None:
    def counted(total: int, cached: int, inputs: int, out: int) -> dict[str, Any]:
        return {
            "payload": {
                "info": {
                    "last_token_usage": {
                        "total_tokens": inputs + out,
                        "input_tokens": inputs,
                        "cached_input_tokens": cached,
                        "output_tokens": out,
                    },
                    "total_token_usage": {"total_tokens": total},
                }
            }
        }

    _write(
        home / "s1.jsonl",
        counted(110, 60, 100, 10),
        counted(110, 60, 100, 10),  # the same request, said again
        counted(150, 30, 30, 10),  # wholly cached: no plain input left
    )
    tally = _tally(told, Seen("a", "codex", "gpt-5", idents=frozenset({"s1"})))

    tally.read()

    assert told.totals == {
        "gpt-5": (150, {"input": 40.0, "cache_read": 90.0, "output": 20.0})
    }


def test_a_total_the_kinds_do_not_account_for_is_spent_under_no_kind(
    home: Path, told: _Told
) -> None:
    _write(
        home / "s1.jsonl",
        {"payload": {"info": {"last_token_usage": {"total_tokens": 50}}}},
    )
    tally = _tally(told, Seen("a", "codex", "gpt-5", idents=frozenset({"s1"})))

    tally.read()

    assert told.totals == {"gpt-5": (50, {"": 50.0})}


def test_dsh_reads_assistant_messages_alone(home: Path, told: _Told) -> None:
    _write(
        home / "s1.jsonl",
        {
            "type": "assistant/message",
            "time": 1_900_000_000_000,
            "data": {
                "message": {"source": {"model": "deepseek-v3"}},
                "usage": {"inputTokens": 3, "outputTokens": 4},
            },
        },
        {"type": "user/message", "data": {"usage": {"inputTokens": 99}}},
    )
    tally = _tally(told, Seen("a", "dsh", "fallback", idents=frozenset({"s1"})))

    tally.read()

    assert told.totals == {"deepseek-v3": (7, {"input": 3.0, "output": 4.0})}


@pytest.mark.parametrize("backend", ["mcode", "litellm"])
def test_pi_shaped_logs_count_answers_against_provider_and_model(
    home: Path, told: _Told, backend: str
) -> None:
    _write(
        home / "s1.jsonl",
        {
            "message": {
                "role": "assistant",
                "provider": "minimax",
                "model": "m2",
                "usage": {"input": 2, "output": 3, "cacheRead": 4, "cache_read": 4},
                "timestamp": 1_900_000_000,
            }
        },
        {"message": {"role": "user", "usage": {"input": 50}}},
    )
    tally = _tally(told, Seen("a", backend, "fallback", idents=frozenset({"s1"})))

    tally.read()

    [(model, (total, kinds))] = told.totals.items()
    assert model == "minimax/m2"
    assert (kinds or {})["cache_read"] == 4.0
    assert total == 9


def test_kimi_reads_each_steps_usage(home: Path, told: _Told) -> None:
    _write(
        home / "s1.jsonl",
        {
            "envelope": {
                "timestamp": "2030-01-01T00:00:00Z",
                "payload": {"usage": {"inputOther": 6, "output": 2}},
            }
        },
    )
    tally = _tally(told, Seen("a", "kimi", "k2", idents=frozenset({"s1"})))

    tally.read()

    assert told.totals == {"k2": (8, {"input": 6.0, "output": 2.0})}


def test_logs_under_a_runs_own_directory_and_every_pattern_are_read(
    tmp_path: Path, home: Path, told: _Told
) -> None:
    kept = tmp_path / "kept"
    _write(kept / "s1.jsonl", _claude("m1", {"output_tokens": 2}))
    _write(kept / "sub" / "s1-agent.jsonl", _claude("m2", {"output_tokens": 3}))
    tally = _tally(
        told, Seen("a", "claude", "opus", idents=frozenset({"s1"}), kept=str(kept))
    )

    tally.read()

    assert told.totals["opus"][0] == 5


def test_a_session_added_later_is_read_too(home: Path, told: _Told) -> None:
    _write(home / "s1.jsonl", _claude("m1", {"output_tokens": 2}))
    tally = _tally(told)
    tally.read()
    assert told.totals == {}

    tally.add(Seen("a", "claude", "opus", idents=frozenset({"s1"})))
    tally.read()

    assert told.totals["opus"][0] == 2


def test_what_a_backend_reports_is_said_once(home: Path, told: _Told) -> None:
    _write(home / "s1.jsonl", _claude("m1", {"output_tokens": 2}))
    tally = _tally(told, Seen("a", "claude", "opus", idents=frozenset({"s1"})))
    tally.read()
    told.reports.clear()

    tally.read()

    assert told.reports == {}


def test_watching_reads_until_stopped(home: Path, told: _Told) -> None:
    _write(home / "s1.jsonl", _claude("m1", {"output_tokens": 2}))
    tally = _tally(told, Seen("a", "claude", "opus", idents=frozenset({"s1"})))
    tally.stops()  # stopped before it starts: it reads once on its way out

    tally.watch()

    assert told.landed.wait(5.0)
    assert told.totals["opus"][0] == 2
