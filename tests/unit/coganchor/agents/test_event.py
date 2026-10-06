"""`hmz.coganchor.agents.event`: what a turn says, what it costs, and how it fails."""

from __future__ import annotations

import io
import subprocess

import pytest

from hmz.coganchor.agents.event import (
    KINDS,
    Event,
    Failed,
    Question,
    Saying,
    Stopped,
    Unrecoverable,
    Usage,
    say,
)


def test_the_kinds_of_token() -> None:
    assert KINDS == ("input", "output", "cache_read", "cache_write", "reasoning")


def test_usage_is_a_mapping_of_kinds() -> None:
    usage = Usage({"input": 1.0, "cache_read": 2.0}, output=3.0)
    assert dict(usage) == {"input": 1.0, "cache_read": 2.0, "output": 3.0}
    assert (usage.input, usage.output, usage.total) == (1.0, 3.0, 6.0)
    assert usage["cache_read"] == 2.0
    assert len(usage) == 3
    assert usage.get("reasoning", 0) == 0
    with pytest.raises(KeyError):
        _ = usage["reasoning"]
    assert repr(usage) == "Usage(input=1, cache_read=2, output=3)"


def test_an_empty_usage_spent_nothing() -> None:
    usage = Usage()
    assert (usage.input, usage.output, usage.total, len(usage)) == (0.0, 0.0, 0, 0)
    assert repr(usage) == "Usage()"


def test_usages_add_kind_by_kind() -> None:
    added = Usage(input=1, output=2) + {"output": 3, "reasoning": 4}
    assert dict(added) == {"input": 1, "output": 5, "reasoning": 4}


@pytest.mark.parametrize(
    ("over", "rate"),
    [(2.0, {"input": 2.0, "output": 1.0}), (0.0, {"input": 0.0, "output": 0.0})],
)
def test_usage_over_seconds_is_a_rate(over: float, rate: dict[str, float]) -> None:
    assert dict(Usage(input=4, output=2) / over) == rate
    assert dict(Usage(input=4, output=2) / -1) == {"input": 0.0, "output": 0.0}


def test_failed_is_a_called_process_error_that_says_why() -> None:
    failed = Failed(
        1,
        ["sandbox", "--", "/usr/bin/codex", "exec", "--json"],
        output='{"type":"x"}\nthe model is not supported\n{"type":"y"}',
        stderr=b"warning:   no\n project",
        fault="model",
        fix="pick another model",
    )
    assert isinstance(failed, subprocess.CalledProcessError)
    assert (failed.fault, failed.fix) == ("model", "pick another model")
    assert failed.reads() == "(model: pick another model)"
    assert str(failed) == (
        "Command 'codex exec' returned non-zero exit status 1. warning: no project "
        "the model is not supported (model: pick another model)"
    )


@pytest.mark.parametrize(
    ("cmd", "named"),
    [
        ("a whole line", "a whole line"),
        (["claude", "-p"], "claude"),
        (["/bin/pi", "Run"], "pi"),
        (["wrap", "--"], ""),
    ],
)
def test_failed_names_the_cli(cmd: str | list[str], named: str) -> None:
    said = str(Failed(2, cmd))
    assert said == f"Command '{named}' returned non-zero exit status 2."


def test_failed_says_nothing_it_was_not_told() -> None:
    failed = Failed(1, ["x"], output="{only protocol}", stderr="   ")
    assert failed.reads() == ""
    assert str(failed) == "Command 'x' returned non-zero exit status 1."
    assert Failed(1, ["x"], fault="auth").reads() == "(auth)"


def test_failed_clips_a_long_complaint() -> None:
    said = str(Failed(1, ["x"], stderr="y" * 1000))
    assert said.endswith("y…")
    assert len(said) < 500


def test_unrecoverable_is_still_a_failure() -> None:
    assert issubclass(Unrecoverable, Failed)
    assert not issubclass(Stopped, subprocess.CalledProcessError)


def test_events_and_questions_default_to_nothing() -> None:
    event = Event(kind="text", text="hi")
    assert (event.whose, dict(event.tokens), dict(event.spent)) == ("", {}, {})
    assert Question("why?") == Question(text="why?", options=(), asker="")


def test_saying_gathers_fragments_into_one_utterance() -> None:
    saying = Saying()
    saying.delta("text", "Hello, ")
    saying.delta("reasoning", "  thinking  ")
    saying.delta("text", "world")
    assert [(one.kind, one.text) for one in saying.upto()] == [
        ("reasoning", "thinking"),
        ("text", "Hello, world"),
    ]
    assert saying.upto() == []
    saying.delta("text", " again")
    assert [one.text for one in saying.ended()] == ["again"]
    assert saying.rest() == []


def test_saying_whole_replaces_and_says_only_the_unseen_part() -> None:
    saying = Saying()
    saying.delta("text", "abc")
    saying.upto()
    saying.whole("text", "abcdef")
    assert [one.text for one in saying.ended()] == ["def"]


def test_saying_whole_that_disagrees_starts_again() -> None:
    saying = Saying()
    saying.delta("text", "abc")
    saying.upto()
    saying.whole("text", "xyz")
    assert [one.text for one in saying.ended()] == ["xyz"]


def test_saying_keeps_answers_apart_by_whose() -> None:
    saying = Saying()
    saying.delta("text", "one", "m1")
    saying.delta("text", "two", "m2")
    saying.delta("text", " more")  # unnamed: the one last written to
    assert [one.text for one in saying.ended("m1")] == ["one"]
    assert [one.text for one in saying.upto()] == ["two more"]
    saying.delta("text", "three", "m3")
    assert [one.text for one in saying.rest()] == ["three"]
    assert saying.rest() == []


def test_say_writes_and_survives_a_sink_that_has_gone() -> None:
    sink = io.StringIO()
    say("hello", sink)
    say("frag", sink, end="")
    assert sink.getvalue() == "hello\nfrag"

    class Gone(io.StringIO):
        def write(self, s: str) -> int:
            raise BrokenPipeError

    say("nobody", Gone())
