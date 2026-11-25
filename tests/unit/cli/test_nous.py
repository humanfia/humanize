"""`hmz nous`: every nous listed and scanned, one written, renamed and cleared."""

from __future__ import annotations

import json
from typing import Any
from unittest import mock

import pytest

from hmz.cli import main, tree

SAID: dict[str, Any] = {
    "nous": [{"name": "careful"}],
    "policies": [{"name": "constant", "about": "the same wait every time"}],
    "default": "exponential-jitter",
    "strategies": [],
    "faults": ["*"],
    "concrete": ["claude/opus", "claude@work/opus", "codex/sol"],
    "scanning": False,
}


def _node(id_: str, use: str, on: dict[str, str], balance: str = "") -> mock.Mock:
    return mock.Mock(id=id_, use=use, balance=balance, on=on)


def _graph(*nodes: mock.Mock) -> mock.Mock:
    graph = mock.Mock(start=nodes[0].id, nodes=nodes)
    graph.sent.return_value = {"start": nodes[0].id, "nodes": len(nodes)}
    return graph


def _entry(name: str, **more: Any) -> mock.Mock:
    said: dict[str, Any] = {
        "virtual": False,
        "tries": 0,
        "policy": "exponential-jitter",
        "timeout": 0.0,
        "graph": None,
        "then": None,
    } | more
    one = mock.Mock(**said)
    one.name = name
    return one


CHAIN = _graph(_node("n1", "claude/opus", {"*": "n2"}), _node("n2", "codex/sol", {}))
BALANCE = _graph(_node("a", "", {}, balance="shuffle"))
CAREFUL = _entry("careful", virtual=True, tries=1, policy="constant", graph=CHAIN)
OPUS = _entry("claude/opus", tries=3, timeout=600.0, then=BALANCE)


@pytest.fixture
def nous(monkeypatch: pytest.MonkeyPatch) -> mock.Mock:
    """The nous family of the client the command reaches, with two nous written."""
    client = mock.Mock()
    monkeypatch.setattr(tree, "reach", mock.Mock(return_value=client))
    held = {"careful": CAREFUL, "claude/opus": OPUS}
    book = mock.Mock(
        nous=(CAREFUL, OPUS), concrete=tuple(SAID["concrete"]), failed=(), said=SAID
    )
    book.entry.side_effect = held.get
    family = client.nous
    for method in (family.list, family.scan, family.set, family.rename, family.clear):
        method.return_value = book
    return family


def test_the_nous_written_are_listed_a_line_each(
    nous: mock.Mock, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["nous", "list"]) == 0

    lines = [line.split("  ") for line in capsys.readouterr().out.splitlines()]
    assert [[cell.strip() for cell in line if cell] for line in lines] == [
        [
            "careful",
            "Virtual",
            "1 more go, constant",
            "no limit",
            "claude/opus,codex/sol",
            "nowhere",
        ],
        [
            "claude/opus",
            "Concrete",
            "3 more goes, exponential-jitter",
            "at most 600s",
            "-",
            '{"start":"a","nodes":1}',
        ],
    ]

    assert main(["nous", "list", "--json"]) == 0
    assert json.loads(capsys.readouterr().out) == SAID


def test_every_concrete_nous_is_listed_a_line_each(
    nous: mock.Mock, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["nous", "list", "--concrete"]) == 0

    assert capsys.readouterr().out == "claude/opus\nclaude@work/opus\ncodex/sol\n"
    nous.list.assert_called_once_with()


def test_a_scan_counts_what_it_found_and_says_who_would_not_answer(
    nous: mock.Mock, capsys: pytest.CaptureFixture[str]
) -> None:
    nous.scan.return_value.failed = (
        mock.Mock(cli="codex", account="work", why="timed out"),
        mock.Mock(cli="pi", account="", why="not signed in"),
    )

    assert main(["nous", "scan"]) == 0

    said = capsys.readouterr()
    assert said.out == "3 concrete nous of 2 harnesses.\n"
    assert said.err == (
        "codex@work would not answer: timed out\npi would not answer: not signed in\n"
    )

    assert main(["nous", "scan", "--json"]) == 0
    said = capsys.readouterr()
    assert json.loads(said.out) == {
        **SAID,
        "failed": [
            {"cli": "codex", "account": "work", "why": "timed out"},
            {"cli": "pi", "account": "", "why": "not signed in"},
        ],
    }
    assert said.err == ""


def test_a_nous_never_written_is_written_with_what_the_line_says(
    nous: mock.Mock, capsys: pytest.CaptureFixture[str]
) -> None:
    line = ["nous", "set", "fast", "--graph", "claude/haiku", "--graph", "codex/luna"]

    assert main([*line, "--tries", "2", "--timeout", "30", "--then", "codex/sol"]) == 0

    assert capsys.readouterr().out == "Saved.\n"
    nous.set.assert_called_once_with(
        "fast",
        tries=2,
        policy=None,
        timeout=30.0,
        graph=["claude/haiku", "codex/luna"],
        then="codex/sol",
    )


def test_what_the_line_does_not_say_of_a_nous_stays_as_it_was_written(
    nous: mock.Mock,
) -> None:
    assert main(["nous", "set", "careful", "--tries", "5"]) == 0
    nous.set.assert_called_with(
        "careful", tries=5, policy="constant", timeout=0.0, graph=CHAIN, then=None
    )

    assert main(["nous", "set", "claude/opus", "--policy", "linear"]) == 0
    nous.set.assert_called_with(
        "claude/opus", tries=3, policy="linear", timeout=600.0, graph=None, then=BALANCE
    )

    assert main(["nous", "set", "claude/opus", "--no-then", "--timeout", "0"]) == 0
    nous.set.assert_called_with(
        "claude/opus",
        tries=3,
        policy="exponential-jitter",
        timeout=0.0,
        graph=None,
        then=None,
    )


def test_a_graph_is_taken_as_json_too(
    nous: mock.Mock, capsys: pytest.CaptureFixture[str]
) -> None:
    graph = {"start": "a", "nodes": [{"id": "a", "use": "codex/sol"}]}

    line = ["nous", "set", "fast", "--graph", json.dumps(graph)]
    assert main([*line, "--then", '["claude/opus", "codex/sol"]', "--json"]) == 0

    assert json.loads(capsys.readouterr().out) == SAID
    nous.set.assert_called_once_with(
        "fast",
        tries=None,
        policy=None,
        timeout=None,
        graph=graph,
        then=["claude/opus", "codex/sol"],
    )


def test_a_graph_that_is_not_json_is_a_usage_error_and_nothing_is_written(
    nous: mock.Mock, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["nous", "set", "fast", "--graph", "{nope"]) == 2

    said = capsys.readouterr()
    assert said.out == ""
    assert said.err == (
        "hmz nous set: This is not valid JSON.\nRun `hmz nous set --help` for help.\n"
    )
    nous.set.assert_not_called()


def test_a_nous_is_renamed_and_cleared(
    nous: mock.Mock, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["nous", "rename", "careful", "slow"]) == 0
    assert capsys.readouterr().out == "Renamed\n"
    nous.rename.assert_called_once_with("careful", "slow")

    assert main(["nous", "clear", "slow"]) == 0
    assert capsys.readouterr().out == "Removed\n"
    nous.clear.assert_called_once_with("slow")

    assert main(["nous", "clear", "slow", "--json"]) == 0
    assert json.loads(capsys.readouterr().out) == SAID
