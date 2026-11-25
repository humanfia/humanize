"""`client.settings`, `client.accounts` and `client.nous`: typed calls through a mocked client."""

from __future__ import annotations

from typing import Any
from unittest import mock

import pytest

from hmz.sdk.families.accounts import Account, Accounts, Ask, Backend, Way
from hmz.sdk.families.nous import Entry, Failed, Graph, Kind, Member, Node, Nous
from hmz.sdk.families.settings import Backup, Settings, Target

SETTINGS: dict[str, Any] = {
    "workspace": "/home/me",
    "flow": "ralph",
    "chat": "claude/opus:auto",
    "prefer": "flow",
    "ai_chan": "",
    "details": True,
    "harness_sessions": False,
    "reports": None,
    "flows": ["ralph"],
    "backup": {
        "targets": [
            {
                "name": "lab",
                "url": "https://***@example.org/epics.git",
                "branch": "main",
                "policies": ["session", "end"],
                "every": 30,
            }
        ],
        "defaults": ["lab"],
    },
    "listen": ["tcp://0.0.0.0:7000"],
    "ice_servers": [{"urls": "turn:t:1", "username": "u", "credential": True}],
}

ACCOUNTS: dict[str, Any] = {
    "gateway": "LiteLLM",
    "accounts": [
        {
            "cli": "claude",
            "name": "work",
            "way": "key",
            "sets": ["ANTHROPIC_API_KEY"],
            "made": "2026-01-01T00:00:00Z",
            "models": ["opus"],
            "asked": "2026-01-02T00:00:00Z",
            "serves": ["pi"],
        }
    ],
    "backends": [
        {
            "cli": "claude",
            "wants": "",
            "ways": [
                {
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
            ],
        }
    ],
}

CHAIN: dict[str, Any] = {
    "start": "n1",
    "nodes": [
        {
            "id": "n1",
            "use": "claude/opus",
            "balance": "",
            "among": [],
            "spread": 0,
            "on": {"*": "n2"},
        },
        {
            "id": "n2",
            "use": "",
            "balance": "shuffle",
            "among": [{"nous": "codex/sol", "weight": 2}],
            "spread": 1,
            "on": {},
        },
    ],
}

NOUS: dict[str, Any] = {
    "nous": [
        {
            "name": "careful",
            "virtual": True,
            "tries": 2,
            "policy": "constant",
            "timeout": 600.0,
            "graph": CHAIN,
            "then": None,
        }
    ],
    "policies": [{"name": "constant", "about": "the same wait every time"}],
    "default": "exponential-jitter",
    "strategies": [{"name": "shuffle", "about": "at random"}],
    "faults": ["spent", "*"],
    "concrete": ["claude/opus", "codex/sol"],
    "scanning": False,
}


@pytest.fixture
def client() -> mock.Mock:
    return mock.Mock(spec=["call", "heard"])


def test_settings_are_read_whole_and_typed(client: mock.Mock) -> None:
    client.call.return_value = SETTINGS

    kept = Settings(client).get("/home/me")

    client.call.assert_called_once_with(
        "settings.get", {"workspace": "/home/me"}, idem=None, seconds=None
    )
    assert (kept.workspace, kept.flow, kept.chat, kept.prefer) == (
        "/home/me",
        "ralph",
        "claude/opus:auto",
        "flow",
    )
    assert (kept.details, kept.harness_sessions, kept.reports) == (True, False, None)
    assert kept.flows == ("ralph",)
    assert kept.backup == Backup(
        (
            Target(
                "lab",
                "https://***@example.org/epics.git",
                "main",
                ("session", "end"),
                30,
            ),
        ),
        ("lab",),
    )
    assert kept.listen == ("tcp://0.0.0.0:7000",)
    assert kept.ice_servers == (
        {"urls": "turn:t:1", "username": "u", "credential": True},
    )
    assert kept.forgot is None
    assert kept.said == SETTINGS


def test_settings_of_the_users_home_name_no_workspace(client: mock.Mock) -> None:
    client.call.return_value = SETTINGS

    Settings(client).get()

    client.call.assert_called_once_with("settings.get", {}, idem=None, seconds=None)


def test_only_the_settings_given_are_written(client: mock.Mock) -> None:
    client.call.return_value = SETTINGS

    Settings(client).set(details=False, reports=True, idem="k")

    client.call.assert_called_once_with(
        "settings.set", {"details": False, "reports": True}, idem="k", seconds=None
    )


def test_a_backup_read_is_a_backup_that_can_be_written_back(client: mock.Mock) -> None:
    client.call.return_value = SETTINGS
    settings = Settings(client)

    settings.set(
        backup=settings.get().backup,
        listen=("tcp://0.0.0.0:1",),
        ice_servers=[{"urls": "stun:s:1"}],
        chat="codex/sol",
        prefer="native",
        harness_sessions=True,
        workspace="~/project",
    )

    assert client.call.call_args == mock.call(
        "settings.set",
        {
            "workspace": "~/project",
            "chat": "codex/sol",
            "prefer": "native",
            "harness_sessions": True,
            "backup": SETTINGS["backup"],
            "listen": ["tcp://0.0.0.0:1"],
            "ice_servers": [{"urls": "stun:s:1"}],
        },
        idem=None,
        seconds=None,
    )


def test_forgetting_says_whether_there_was_anything(client: mock.Mock) -> None:
    client.call.return_value = {**SETTINGS, "forgot": True}

    assert Settings(client).forget("/home/me", idem="k").forgot is True
    client.call.assert_called_once_with(
        "settings.forget", {"workspace": "/home/me"}, idem="k", seconds=None
    )


def test_accounts_are_listed_with_the_ways_in(client: mock.Mock) -> None:
    client.call.return_value = ACCOUNTS

    listing = Accounts(client).list()

    client.call.assert_called_once_with("accounts.list", {}, idem=None, seconds=None)
    work = Account(
        "claude",
        "work",
        "key",
        ("ANTHROPIC_API_KEY",),
        "2026-01-01T00:00:00Z",
        ("opus",),
        "2026-01-02T00:00:00Z",
        ("pi",),
    )
    key = Way(
        "key",
        "an Anthropic API key, from the console",
        "",
        terminal=False,
        asks=(Ask("ANTHROPIC_API_KEY", "the API key", secret=True, fixed=""),),
    )
    assert listing.gateway == "LiteLLM"
    assert listing.accounts == (work,)
    assert listing.backends == (Backend("claude", (key,), ""),)
    assert listing.account("claude", "work") == work
    assert listing.account("claude", "home") is None
    assert listing.backend("codex") is None
    backend = listing.backend("claude")
    assert backend is not None
    assert backend.way("key") == key
    assert backend.way("login") is None
    assert listing.said == ACCOUNTS


def test_an_account_is_made_corrected_copied_and_removed(client: mock.Mock) -> None:
    client.call.return_value = ACCOUNTS
    accounts = Accounts(client)

    accounts.create("claude", "work", "key", {"ANTHROPIC_API_KEY": "sk"}, idem="a")
    accounts.correct("claude", "work", {"ANTHROPIC_API_KEY": "sk2"})
    accounts.correct("claude", "work")
    accounts.copy("claude", "work", "pi")
    accounts.models("claude", wait=30)
    accounts.models("claude", "work")
    accounts.remove("claude", "work", idem="r")

    whose = {"cli": "claude", "name": "work"}
    assert client.call.call_args_list == [
        mock.call(
            "accounts.create",
            {**whose, "way": "key", "answers": {"ANTHROPIC_API_KEY": "sk"}},
            idem="a",
            seconds=None,
        ),
        mock.call(
            "accounts.correct",
            {**whose, "answers": {"ANTHROPIC_API_KEY": "sk2"}},
            idem=None,
            seconds=None,
        ),
        mock.call(
            "accounts.correct", {**whose, "answers": {}}, idem=None, seconds=None
        ),
        mock.call("accounts.copy", {**whose, "into": "pi"}, idem=None, seconds=None),
        mock.call(
            "accounts.models", {"cli": "claude", "name": ""}, idem=None, seconds=30
        ),
        mock.call("accounts.models", whose, idem=None, seconds=None),
        mock.call("accounts.remove", whose, idem="r", seconds=None),
    ]


def test_nous_are_listed_with_their_graphs(client: mock.Mock) -> None:
    client.call.return_value = NOUS

    book = Nous(client).list()

    client.call.assert_called_once_with("nous.list", {}, idem=None, seconds=None)
    graph = Graph(
        "n1",
        (
            Node("n1", "claude/opus", "", (), 0, {"*": "n2"}),
            Node("n2", "", "shuffle", (Member("codex/sol", 2),), 1, {}),
        ),
    )
    assert book.nous == (Entry("careful", True, 2, "constant", 600.0, graph, None),)
    assert book.policies == (Kind("constant", "the same wait every time"),)
    assert book.strategies == (Kind("shuffle", "at random"),)
    assert (book.default, book.faults) == ("exponential-jitter", ("spent", "*"))
    assert book.concrete == ("claude/opus", "codex/sol")
    assert (book.scanning, book.failed) == (False, ())
    assert book.entry("careful") == book.nous[0]
    assert book.entry("fast") is None
    assert graph.sent() == {
        "start": "n1",
        "nodes": [
            {**CHAIN["nodes"][0]},
            {**CHAIN["nodes"][1]},
        ],
    }


def test_a_scan_names_the_harnesses_that_would_not_answer(client: mock.Mock) -> None:
    client.call.return_value = {
        **NOUS,
        "failed": [{"cli": "codex", "account": "work", "why": "timed out"}],
    }

    book = Nous(client).scan(wait=120, idem="s")

    client.call.assert_called_once_with("nous.scan", {}, idem="s", seconds=120)
    assert book.failed == (Failed("codex", "work", "timed out"),)


def test_a_nous_is_written_in_whichever_shape_its_graph_is_given(
    client: mock.Mock,
) -> None:
    client.call.return_value = NOUS
    nous = Nous(client)
    graph = nous.list().nous[0].graph

    nous.set("claude/opus", tries=3, timeout=600)
    nous.set("careful", graph=graph, then="codex/sol", policy="constant")
    nous.set("careful", graph=("claude/opus", "codex/sol"), then=CHAIN)
    nous.rename("careful", "slow", idem="n")
    nous.clear("slow")

    assert graph is not None
    assert client.call.call_args_list[1:] == [
        mock.call(
            "nous.set",
            {"name": "claude/opus", "tries": 3, "timeout": 600},
            idem=None,
            seconds=None,
        ),
        mock.call(
            "nous.set",
            {
                "name": "careful",
                "policy": "constant",
                "graph": graph.sent(),
                "then": "codex/sol",
            },
            idem=None,
            seconds=None,
        ),
        mock.call(
            "nous.set",
            {"name": "careful", "graph": ["claude/opus", "codex/sol"], "then": CHAIN},
            idem=None,
            seconds=None,
        ),
        mock.call(
            "nous.rename", {"name": "careful", "to": "slow"}, idem="n", seconds=None
        ),
        mock.call("nous.clear", {"name": "slow"}, idem=None, seconds=None),
    ]


def test_each_family_names_the_methods_it_makes() -> None:
    assert Settings.METHODS == ("settings.get", "settings.set", "settings.forget")
    assert Accounts.METHODS == (
        "accounts.list",
        "accounts.create",
        "accounts.correct",
        "accounts.remove",
        "accounts.models",
        "accounts.copy",
    )
    assert Nous.METHODS == (
        "nous.list",
        "nous.scan",
        "nous.set",
        "nous.rename",
        "nous.clear",
    )
