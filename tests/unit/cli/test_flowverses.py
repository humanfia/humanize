"""`hmz flowverses`: the flowverses listed, one shown, and flows installed and removed."""

from __future__ import annotations

import io
import json
from types import SimpleNamespace as Said
from typing import Any
from unittest import mock

import pytest

from hmz.cli import main, tree

ANSWER: dict[str, list[Any]] = {"verses": [], "installed": [], "updates": []}


@pytest.fixture
def verses(monkeypatch: pytest.MonkeyPatch) -> mock.Mock:
    """The flowverses family of the client the command reaches."""
    client = mock.Mock()
    monkeypatch.setattr(tree, "reach", mock.Mock(return_value=client))
    return client.flowverses


def _typed(
    monkeypatch: pytest.MonkeyPatch, line: str, *, terminal: bool = True
) -> None:
    """Puts somebody at the terminal who types one line, or nobody."""
    typed = io.StringIO(line)
    typed.isatty = lambda: terminal  # type: ignore[method-assign]
    monkeypatch.setattr("sys.stdin", typed)


def _kept(**said: Any) -> Said:
    held: dict[str, Any] = {
        "verses": (),
        "installed": (),
        "updates": (),
        "said": "",
        "answer": ANSWER,
    }
    return Said(**(held | said))


def test_the_flowverses_and_what_is_installed_are_listed_under_headings(
    verses: mock.Mock, capsys: pytest.CaptureFixture[str]
) -> None:
    verses.list.return_value = _kept(
        verses=(
            Said(name="official", url="https://x/official", installed=2, fetched=True),
            Said(name="team", url="", installed=0, fetched=False),
        ),
        installed=(
            Said(flow="ralph", version="1.0.0", verse="official"),
            Said(flow="@team/review", version="0.2.0", verse="team"),
        ),
        updates=(Said(flow="ralph", to="1.1.0"),),
    )

    assert main(["flowverses", "list"]) == 0

    assert capsys.readouterr().out.splitlines() == [
        "Flowverses",
        "  official  https://x/official  2",
        "  team      local               0  Not fetched yet.",
        "Installed",
        "  ralph         1.0.0  official  1.1.0 out",
        "  @team/review  0.2.0  team",
    ]

    assert main(["flowverses", "list", "--json"]) == 0
    assert json.loads(capsys.readouterr().out) == ANSWER


def test_nothing_installed_is_said_where_it_would_be_listed(
    verses: mock.Mock, capsys: pytest.CaptureFixture[str]
) -> None:
    verses.list.return_value = _kept()

    assert main(["flowverses", "list"]) == 0

    assert capsys.readouterr().out.splitlines() == [
        "Flowverses",
        "Installed",
        "  No flows installed yet.",
    ]


def _index(**said: Any) -> Said:
    held: dict[str, Any] = {
        "name": "team",
        "url": "https://x/team",
        "fetched": True,
        "edited": False,
        "flows": (),
        "skipped": (),
        "answer": {"name": "team"},
    }
    return Said(**(held | said))


def test_a_flowverse_is_shown_a_release_a_line(
    verses: mock.Mock, capsys: pytest.CaptureFixture[str]
) -> None:
    verses.get.return_value = _index(
        edited=True,
        flows=(
            Said(
                flow="@team/review",
                installed="1.0.0",
                releases=(
                    Said(version="1.1.0-rc.1", prerelease=True, description="Newer"),
                    Said(version="1.0.0", prerelease=False, description="Reviews"),
                ),
            ),
        ),
        skipped=(Said(at="flows/x/flow.yaml", why="unreadable"),),
    )

    assert main(["flowverses", "show", "team"]) == 0

    assert capsys.readouterr().out.splitlines() == [
        "team  https://x/team",
        "Something is written into it: fetching resets it to what its repository says.",
        "@team/review  1.1.0-rc.1 (pre)  -          Newer",
        "@team/review  1.0.0             Installed  Reviews",
        "1 skipped",
        "  flows/x/flow.yaml  unreadable",
    ]
    verses.get.assert_called_once_with("team")

    assert main(["flowverses", "show", "team", "--json"]) == 0
    assert json.loads(capsys.readouterr().out) == {"name": "team"}


@pytest.mark.parametrize(
    ("fetched", "says"),
    [(True, "This flowverse lists no flow."), (False, "Not fetched yet.")],
)
def test_a_flowverse_listing_nothing_says_why(
    verses: mock.Mock, capsys: pytest.CaptureFixture[str], fetched: bool, says: str
) -> None:
    verses.get.return_value = _index(url="", fetched=fetched)

    assert main(["flowverses", "show", "team"]) == 0

    assert capsys.readouterr().out.splitlines() == ["team  local", says]


@pytest.mark.parametrize(
    ("line", "change", "given"),
    [
        (["add", "acme/flows"], "add", ("acme/flows", None)),
        (["add", "acme/flows", "--name", "team"], "add", ("acme/flows", "team")),
        (["fetch", "team"], "fetch", ("team",)),
        (["install", "@team/review"], "install", ("@team/review", None)),
        (
            ["install", "@team/review", "--version", "1.1.0"],
            "install",
            ("@team/review", "1.1.0"),
        ),
        (["remove", "team", "-y"], "remove", ("team",)),
        (["uninstall", "@team/review", "--yes"], "uninstall", ("@team/review",)),
    ],
)
def test_a_change_says_what_the_daemon_said_it_did(
    verses: mock.Mock,
    capsys: pytest.CaptureFixture[str],
    line: list[str],
    change: str,
    given: tuple[str | None, ...],
) -> None:
    getattr(verses, change).return_value = _kept(
        said="done it", answer={"said": "done it"} | ANSWER
    )

    assert main(["flowverses", *line]) == 0
    assert capsys.readouterr().out == "done it\n"
    getattr(verses, change).assert_called_once_with(*given)

    assert main(["flowverses", *line, "--json"]) == 0
    assert json.loads(capsys.readouterr().out) == {"said": "done it"} | ANSWER


@pytest.mark.parametrize(
    ("line", "change", "asks"),
    [
        (
            ["remove", "team"],
            "remove",
            "Remove team and every flow installed out of it? [y/N] ",
        ),
        (["uninstall", "ralph"], "uninstall", "Uninstall ralph? [y/N] "),
    ],
)
def test_removing_asks_first_and_takes_only_a_yes(
    verses: mock.Mock,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    line: list[str],
    change: str,
    asks: str,
) -> None:
    getattr(verses, change).return_value = _kept(said="gone")

    _typed(monkeypatch, "n\n")
    assert main(["flowverses", *line]) == 1
    said = capsys.readouterr()
    assert said.out == ""
    assert said.err == f"{asks}hmz flowverses {line[0]}: Nothing was changed.\n"
    getattr(verses, change).assert_not_called()

    _typed(monkeypatch, "Yes\n")
    assert main(["flowverses", *line]) == 0
    said = capsys.readouterr()
    assert said.out == "gone\n"
    assert said.err == asks
    getattr(verses, change).assert_called_once_with(line[1])


def test_nobody_at_a_terminal_is_not_asked_and_nothing_is_removed(
    verses: mock.Mock,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _typed(monkeypatch, "y\n", terminal=False)

    assert main(["flowverses", "remove", "team"]) == 1

    said = capsys.readouterr()
    assert said.out == ""
    assert said.err == (
        "hmz flowverses remove: Nobody is at a terminal to ask; run it again with `-y`.\n"
    )

    _typed(monkeypatch, "y\n")
    assert main(["flowverses", "uninstall", "ralph", "--json"]) == 1

    said = capsys.readouterr()
    assert json.loads(said.out) == {
        "error": {
            "code": 0,
            "message": "Nobody is at a terminal to ask; run it again with `-y`.",
        }
    }
    assert said.err == ""
    verses.remove.assert_not_called()
    verses.uninstall.assert_not_called()
