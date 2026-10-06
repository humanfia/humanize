from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest

from hmz.runtime.tracing.session import (
    Action,
    Session,
    label,
    mapping,
    records,
    summarize,
    text_of,
    title_of,
    truncate,
    wanted,
)
from tests.unit.runtime.tracing.logs import jsonl

if TYPE_CHECKING:
    from pathlib import Path


def test_defaults_are_fresh_per_instance() -> None:
    one, two = Action("a", "tool", 1, 2), Action("b", "tool", 1, 2)
    one.args["x"] = 1
    assert two.args == {}
    assert one.spawn is None
    held = Session("k", "claude", "id", "main", "t")
    assert (held.parent, held.agent, held.args, held.actions) == (None, "", {}, [])


def test_records_skips_torn_and_non_mapping_lines(tmp_path: Path) -> None:
    path = jsonl(tmp_path / "log.jsonl", [{"a": 1}, "[1, 2]", "", '{"b":', {"c": 3}])
    assert list(records(path)) == [{"a": 1}, {"c": 3}]


def test_records_replaces_undecodable_bytes(tmp_path: Path) -> None:
    path = tmp_path / "log.jsonl"
    path.write_bytes(b'{"a": "\xff"}\n')
    assert list(records(path)) == [{"a": "�"}]


@pytest.mark.parametrize(
    ("text", "limit", "expected"),
    [
        ("  a\n  b\tc ", 96, "a b c"),
        ("abcdef", 6, "abcdef"),
        ("abcdefg", 6, "abcde…"),
        ("", 10, ""),
    ],
)
def test_summarize(text: str, limit: int, expected: str) -> None:
    assert summarize(text, limit) == expected


def test_truncate_clips_strings_and_lists_recursively() -> None:
    assert truncate("abcdef", 3) == "abc… (+3 chars)"
    assert truncate("abc", 3) == "abc"
    assert truncate(7) == 7
    assert truncate({1: "abcd"}, 2) == {"1": "ab… (+2 chars)"}
    clipped = truncate(list(range(40)))
    assert clipped[:32] == list(range(32))
    assert clipped[32:] == ["… (+8 items)"]
    assert truncate(list(range(32))) == list(range(32))


@pytest.mark.parametrize(
    ("value", "expected"),
    [({"a": 1}, {"a": 1}), ([1], {}), (None, {}), ("x", {})],
)
def test_mapping(value: Any, expected: dict[str, Any]) -> None:
    assert mapping(value) == expected


@pytest.mark.parametrize(
    ("content", "expected"),
    [
        (None, ""),
        ("plain", "plain"),
        (
            ["a", 3, {"text": "b"}, {"thinking": "c"}, {"output": ""}, {"x": 1}],
            "a\nb\nc",
        ),
        ([{"think": "t", "text": "x"}], "x"),
        ({"text": "inner"}, "inner"),
        ({"content": [{"text": "deep"}]}, "deep"),
        (12, "12"),
        (True, "true"),
    ],
)
def test_text_of(content: Any, expected: str) -> None:
    assert text_of(content) == expected


@pytest.mark.parametrize(
    ("tool_input", "expected"),
    [
        ("ls  -la", "Bash: ls -la"),
        ("   ", "Bash"),
        ({"command": "make", "description": "build it"}, "Bash: build it"),
        ({"description": " ", "command": "make"}, "Bash: make"),
        ({"other": "x"}, "Bash"),
        (None, "Bash"),
    ],
)
def test_label(tool_input: Any, expected: str) -> None:
    assert label("Bash", tool_input) == expected


@pytest.mark.parametrize(
    ("sessions", "extra", "expected"),
    [
        (None, (), True),
        (("claude:abc",), (), True),
        (("abc",), (), True),
        (("ab",), (), True),
        (("zz",), (), False),
        (("short",), ("shortened",), True),
        ((), (), False),
    ],
)
def test_wanted(
    sessions: tuple[str, ...] | None, extra: tuple[str, ...], expected: bool
) -> None:
    assert wanted(sessions, "claude:abcdef", *extra) is expected


def test_title_of_takes_the_first_prompted_turn() -> None:
    actions = [
        Action("t", "tool", 0, 1, {"prompt": "not a turn"}),
        Action("t", "turn", 0, 1, {"prompt": "  "}),
        Action("t", "turn", 0, 1, {"prompt": "fix the\nbug"}),
    ]
    assert title_of("abc", actions) == "abc · fix the bug"
    assert title_of("abc", []) == "abc"
