"""`hmz accounts`: accounts listed, made, corrected, copied and removed, and never shown."""

from __future__ import annotations

import io
import json
from typing import Any
from unittest import mock

import pytest

from hmz.cli import main, tree

SECRET = "sk-never-printed"


def _account(cli: str, name: str, **more: Any) -> mock.Mock:
    said: dict[str, Any] = {
        "way": "key",
        "sets": ("ANTHROPIC_API_KEY",),
        "made": "2026-01-01T00:00:00Z",
        "models": ("opus", "haiku"),
        "asked": "2026-01-02T00:00:00Z",
        "serves": ("pi",),
    } | more
    one = mock.Mock(cli=cli, **said)
    one.name = name
    return one


def _ask(env: str, about: str, *, secret: bool, fixed: str = "") -> mock.Mock:
    return mock.Mock(env=env, about=about, secret=secret, fixed=fixed)


def _way(name: str, about: str, *asks: mock.Mock, terminal: bool = False) -> mock.Mock:
    way = mock.Mock(about=about, group="", terminal=terminal, asks=asks)
    way.name = name
    return way


@pytest.fixture
def accounts(monkeypatch: pytest.MonkeyPatch) -> mock.Mock:
    """The accounts family of the client the command reaches, holding one account."""
    client = mock.Mock()
    monkeypatch.setattr(tree, "reach", mock.Mock(return_value=client))
    work = _account("claude", "work")
    local = _account("claude", "", way="", sets=(), made="", models=("opus",))
    ways = {
        "login": _way("login", "sign in to a Claude subscription", terminal=True),
        "key": _way(
            "key",
            "an Anthropic API key, from the console",
            _ask("ANTHROPIC_API_KEY", "the API key", secret=True),
        ),
        "gateway": _way(
            "gateway",
            "an endpoint",
            _ask("ANTHROPIC_BASE_URL", "where it is, as a URL", secret=False),
            _ask("ANTHROPIC_AUTH_TOKEN", "the key it takes", secret=True),
            _ask("CLOUD_ML_REGION", "the region", secret=False, fixed="us-east5"),
        ),
    }
    backend = mock.Mock(cli="claude", wants="", ways=tuple(ways.values()))
    backend.way.side_effect = ways.get
    other = mock.Mock(cli="codex", wants="", ways=())
    held = {("claude", "work"): work, ("claude", ""): local}
    listing = mock.Mock(
        gateway="LiteLLM", accounts=(work, local), backends=(backend, other)
    )

    def account(cli: str, name: str) -> mock.Mock | None:
        return held.get((cli, name))

    listing.account.side_effect = account
    listing.backend.side_effect = {"claude": backend, "codex": other}.get
    family = client.accounts
    for method in (
        family.list,
        family.create,
        family.correct,
        family.remove,
        family.models,
        family.copy,
    ):
        method.return_value = listing
    client.nous.list.return_value = mock.Mock(
        concrete=("claude/opus", "codex/sol", "codex/luna", "codex@work/terra")
    )
    return family


DOCUMENT = {
    "gateway": "LiteLLM",
    "accounts": [
        {
            "cli": "claude",
            "name": "work",
            "way": "key",
            "sets": ["ANTHROPIC_API_KEY"],
            "made": "2026-01-01T00:00:00Z",
            "models": ["opus", "haiku"],
            "asked": "2026-01-02T00:00:00Z",
            "serves": ["pi"],
        },
        {
            "cli": "claude",
            "name": "",
            "way": "",
            "sets": [],
            "made": "",
            "models": ["opus"],
            "asked": "2026-01-02T00:00:00Z",
            "serves": ["pi"],
        },
    ],
}


def test_the_accounts_are_listed_by_their_names(
    accounts: mock.Mock, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["accounts", "list"]) == 0
    assert capsys.readouterr().out == (
        "claude  work   key  ANTHROPIC_API_KEY  2 models\n"
        "claude  Local                          1 model\n"
    )

    assert main(["accounts", "list", "--json"]) == 0
    assert json.loads(capsys.readouterr().out) == DOCUMENT
    assert accounts.list.call_count == 2


def test_the_ways_in_are_listed_with_what_each_asks(
    accounts: mock.Mock, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["accounts", "ways", "claude"]) == 0
    assert capsys.readouterr().out.splitlines() == [
        "claude  login (at a terminal)  sign in to a Claude subscription",
        "claude  key  an Anthropic API key, from the console",
        "    ANTHROPIC_API_KEY  the API key",
        "claude  gateway  an endpoint",
        "    ANTHROPIC_BASE_URL  where it is, as a URL",
        "    ANTHROPIC_AUTH_TOKEN  the key it takes",
        "    CLOUD_ML_REGION  the region Left empty, it is us-east5.",
    ]

    assert main(["accounts", "ways", "--json"]) == 0
    said = json.loads(capsys.readouterr().out)
    assert [one["cli"] for one in said["backends"]] == ["claude", "codex"]
    assert said["backends"][0]["ways"][1] == {
        "name": "key",
        "about": "an Anthropic API key, from the console",
        "group": "",
        "terminal": False,
        "asks": [
            {
                "env": "ANTHROPIC_API_KEY",
                "about": "the API key",
                "secret": True,
                "fixed": "",
            }
        ],
    }


def test_an_account_is_made_from_the_environment_and_never_printed(
    accounts: mock.Mock,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", SECRET)

    line = ["accounts", "add", "claude", "home", "--way", "key"]
    assert main([*line, "--env", "ANTHROPIC_API_KEY"]) == 0

    said = capsys.readouterr()
    assert said.out == "Made claude@home.\n"
    assert SECRET not in said.out + said.err
    accounts.create.assert_called_once_with(
        "claude", "home", "key", {"ANTHROPIC_API_KEY": SECRET}
    )

    assert main([*line, "--env", "ANTHROPIC_API_KEY", "--json"]) == 0
    said = capsys.readouterr()
    assert json.loads(said.out) == DOCUMENT
    assert SECRET not in said.out + said.err


def test_answers_come_from_the_line_another_variable_and_standard_input(
    accounts: mock.Mock, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("sys.stdin", io.StringIO(f"{SECRET}\r\n"))
    monkeypatch.setenv("REGION", "eu")

    line = ["accounts", "add", "claude", "proxy", "--way", "gateway"]
    url = "ANTHROPIC_BASE_URL=https://llm.example.org/?a=b"
    more = ["--set", url, "--env", "CLOUD_ML_REGION=REGION"]
    assert main([*line, *more, "--stdin", "ANTHROPIC_AUTH_TOKEN"]) == 0

    accounts.create.assert_called_once_with(
        "claude",
        "proxy",
        "gateway",
        {
            "ANTHROPIC_BASE_URL": "https://llm.example.org/?a=b",
            "CLOUD_ML_REGION": "eu",
            "ANTHROPIC_AUTH_TOKEN": SECRET,
        },
    )


@pytest.mark.parametrize(
    ("answers", "wrong"),
    [
        (
            ["--set", f"ANTHROPIC_API_KEY={SECRET}"],
            (
                "ANTHROPIC_API_KEY is a credential: give it with `--env` or "
                "`--stdin`, not on the command line"
            ),
        ),
        (
            ["--set", "ANTHROPIC_API_KEY"],
            "`--set` takes an answer as NAME=VALUE",
        ),
        (
            ["--env", "HMZ_UNSET_KEY"],
            "the environment variable HMZ_UNSET_KEY is not set",
        ),
    ],
)
def test_an_answer_that_cannot_be_taken_is_a_usage_error_and_nothing_is_made(
    accounts: mock.Mock,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    answers: list[str],
    wrong: str,
) -> None:
    monkeypatch.delenv("HMZ_UNSET_KEY", raising=False)

    assert main(["accounts", "add", "claude", "home", "--way", "key", *answers]) == 2

    said = capsys.readouterr()
    assert said.out == ""
    assert said.err == (
        f"hmz accounts add: {wrong}\nRun `hmz accounts add --help` for help.\n"
    )
    assert SECRET not in said.err
    accounts.create.assert_not_called()


@pytest.mark.parametrize("how", ["--stdin", "--env"])
def test_an_answer_brought_empty_is_refused_rather_than_said_saved(
    accounts: mock.Mock,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    how: str,
) -> None:
    monkeypatch.setattr("sys.stdin", io.StringIO("\n"))
    monkeypatch.setenv("ANTHROPIC_API_KEY", "")

    line = ["accounts", "correct", "claude", "work", how, "ANTHROPIC_API_KEY"]
    assert main(line) == 2

    assert capsys.readouterr().err.splitlines()[0] == (
        "hmz accounts correct: the answer given for ANTHROPIC_API_KEY is empty"
    )
    accounts.correct.assert_not_called()


def test_a_set_with_no_name_is_not_said_back(
    accounts: mock.Mock, capsys: pytest.CaptureFixture[str]
) -> None:
    line = ["accounts", "add", "claude", "home", "--way", "key", "--set", SECRET]

    assert main(line) == 2

    assert SECRET not in capsys.readouterr().err
    accounts.create.assert_not_called()


def test_an_account_is_corrected_with_what_changes_alone(
    accounts: mock.Mock,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("NEW_KEY", SECRET)

    line = ["accounts", "correct", "claude", "work"]
    assert main([*line, "--env", "ANTHROPIC_API_KEY=NEW_KEY"]) == 0

    said = capsys.readouterr()
    assert said.out == "Saved.\n"
    assert SECRET not in said.out + said.err
    accounts.correct.assert_called_once_with(
        "claude", "work", {"ANTHROPIC_API_KEY": SECRET}
    )

    assert main([*line, "--set", f"ANTHROPIC_API_KEY={SECRET}"]) == 2
    assert SECRET not in capsys.readouterr().err
    assert accounts.correct.call_count == 1


def test_an_account_whose_way_is_not_known_keeps_every_variable_off_the_line(
    accounts: mock.Mock, capsys: pytest.CaptureFixture[str]
) -> None:
    accounts.list.return_value.account.side_effect = None
    accounts.list.return_value.account.return_value = _account(
        "claude", "old", way="gone", sets=("OLD_TOKEN",)
    )

    line = ["accounts", "correct", "claude", "old"]
    assert main([*line, "--set", f"OLD_TOKEN={SECRET}"]) == 2

    assert "OLD_TOKEN is a credential" in capsys.readouterr().err
    accounts.correct.assert_not_called()


def test_an_account_is_removed_and_copied(
    accounts: mock.Mock, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["accounts", "remove", "claude", "work"]) == 0
    assert capsys.readouterr().out == "Removed\n"
    accounts.remove.assert_called_once_with("claude", "work")

    assert main(["accounts", "copy", "claude", "work", "pi"]) == 0
    assert capsys.readouterr().out == "Copied to pi\n"
    accounts.copy.assert_called_once_with("claude", "work", "pi")

    assert main(["accounts", "copy", "claude", "work", "pi", "--json"]) == 0
    assert json.loads(capsys.readouterr().out) == DOCUMENT


def test_the_models_of_an_account_are_asked_and_printed_a_line_each(
    accounts: mock.Mock, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["accounts", "models", "claude", "work"]) == 0
    assert capsys.readouterr().out == "opus\nhaiku\n"
    accounts.models.assert_called_once_with("claude", "work")

    assert main(["accounts", "models", "claude", "--json"]) == 0
    assert json.loads(capsys.readouterr().out) == {
        "cli": "claude",
        "name": "",
        "models": ["opus"],
        "asked": "2026-01-02T00:00:00Z",
    }
    accounts.models.assert_called_with("claude", "")


def test_the_machines_own_models_are_read_off_the_nous_where_it_is_not_listed(
    accounts: mock.Mock, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["accounts", "models", "codex"]) == 0
    assert capsys.readouterr().out == "sol\nluna\n"

    assert main(["accounts", "models", "pi", "--json"]) == 0
    assert json.loads(capsys.readouterr().out) == {
        "cli": "pi",
        "name": "",
        "models": [],
        "asked": "",
    }
    assert main(["accounts", "models", "pi"]) == 0
    assert capsys.readouterr().out == "No models listed\n"
