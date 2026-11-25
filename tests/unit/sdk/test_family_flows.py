"""`client.flows`, `flowverses`, `workspaces` and `paths`: typed calls through a mocked client."""

from __future__ import annotations

from typing import Any
from unittest import mock

import pytest

from hmz.sdk.families.flows import (
    Account,
    AgentRole,
    EnvRole,
    Flow,
    Flows,
    Forked,
    Model,
    Running,
)
from hmz.sdk.families.flowverses import (
    Flowverses,
    Installed,
    Listed,
    Release,
    Skipped,
    Update,
    Verse,
)
from hmz.sdk.families.paths import Entry, Paths
from hmz.sdk.families.workspaces import Workspace, Workspaces

DECLARED: dict[str, Any] = {
    "name": "tells",
    "ref": "tells:tells",
    "description": "Tells a story.",
    "resumable": True,
    "resumes": False,
    "agents": [
        {
            "name": "teller",
            "required": True,
            "auto": False,
            "harness": "",
            "permission": {"preset": "read-only", "network": False, "granular": []},
            "skills": ["plot"],
            "clis": ["claude"],
        }
    ],
    "envs": [
        {
            "name": "workspace",
            "required": True,
            "auto": True,
            "cpu": None,
            "memory": None,
            "gpu": None,
            "image": None,
        }
    ],
    "params": {"properties": {"rounds": {"type": "integer", "default": 3}}},
    "remembered": {"agents": {"teller": "claude/opus"}, "budget": {"cost": 5}},
}

KEPT: dict[str, Any] = {
    "verses": [
        {
            "name": "team",
            "url": "https://example.com/team.git",
            "fetched": True,
            "fixed": False,
            "edited": False,
            "installed": 1,
        }
    ],
    "installed": [
        {
            "flow": "@team/review",
            "verse": "team",
            "listed": "review",
            "version": "1.0.0",
            "repo": "acme/review",
            "ref": "abc",
        }
    ],
    "updates": [{"flow": "@team/review", "from": "1.0.0", "to": "1.1.0"}],
}

KNOWN: dict[str, Any] = {
    "here": "/here",
    "workspaces": [
        {
            "path": "/here",
            "name": "here",
            "epics": 2,
            "chats": 1,
            "last": "2026-01-01T00:00:00Z",
            "running": True,
            "here": True,
            "there": True,
        }
    ],
}


@pytest.fixture
def client() -> mock.Mock:
    return mock.Mock(spec=["call", "heard"])


def test_each_family_names_the_methods_it_calls() -> None:
    assert Flows.METHODS == (
        "flows.list",
        "flows.get",
        "flows.backends",
        "flows.setup",
        "flows.check",
        "flows.fork",
    )
    assert (
        tuple(
            f"flowverses.{one}"
            for one in ("list", "get", "add", "fetch", "remove", "install", "uninstall")
        )
        == Flowverses.METHODS
    )
    assert Workspaces.METHODS == (
        "workspaces.list",
        "workspaces.add",
        "workspaces.forget",
    )
    assert Paths.METHODS == ("paths.list", "paths.complete")


def test_the_flows_on_offer_are_listed_with_the_one_last_set_up(
    client: mock.Mock,
) -> None:
    said = {
        "flows": [{"whose": "local", "name": "tells", "about": "Tells a story."}],
        "flow": "tells",
        "running": [
            {
                "ref": "tells:tells",
                "name": "tells",
                "depth": 0,
                "since": "s",
                "task": "t",
            }
        ],
    }
    client.call.return_value = said

    offered = Flows(client).list("/w")

    assert offered.flows == (Flow("local", "tells", "Tells a story."),)
    assert offered.flow == "tells"
    assert offered.running == (Running("tells:tells", "tells", 0, "s", "t"),)
    assert offered.answer == said
    client.call.assert_called_once_with(
        "flows.list", {"workspace": "/w"}, idem=None, seconds=None
    )


def test_flows_listed_for_no_workspace_name_none(client: mock.Mock) -> None:
    client.call.return_value = {"flows": [], "flow": "", "running": []}

    assert Flows(client).list().flows == ()
    client.call.assert_called_once_with("flows.list", {}, idem=None, seconds=None)


def test_what_a_flow_declares_is_read_role_by_role(client: mock.Mock) -> None:
    client.call.return_value = DECLARED

    flow = Flows(client).get("tells", "/w")

    assert (flow.name, flow.ref, flow.resumable, flow.resumes) == (
        "tells",
        "tells:tells",
        True,
        False,
    )
    assert flow.agents == (
        AgentRole(
            "teller",
            required=True,
            auto=False,
            harness="",
            permission={"preset": "read-only", "network": False, "granular": []},
            skills=("plot",),
            clis=("claude",),
        ),
    )
    assert flow.envs == (
        EnvRole(
            "workspace",
            required=True,
            auto=True,
            cpu=None,
            memory=None,
            gpu=None,
            image=None,
        ),
    )
    assert flow.params == DECLARED["params"]
    assert flow.remembered == DECLARED["remembered"]
    assert flow.answer == DECLARED
    client.call.assert_called_once_with(
        "flows.get", {"workspace": "/w", "name": "tells"}, idem=None, seconds=None
    )


def test_the_backends_are_each_harness_with_its_accounts_and_models(
    client: mock.Mock,
) -> None:
    client.call.return_value = {
        "clis": {
            "claude": {
                "accounts": [
                    {
                        "name": "",
                        "models": [{"name": "opus", "efforts": ["low", "high"]}],
                        "asked": "2026-01-01",
                    },
                    {"name": "work", "models": [], "asked": ""},
                ]
            }
        },
        "installable": {"codex": [{"name": "gpt", "efforts": []}]},
        "envs": ["local", "ssh"],
    }

    backends = Flows(client).backends()

    assert backends.clis == {
        "claude": (
            Account("", (Model("opus", ("low", "high")),), "2026-01-01"),
            Account("work", (), ""),
        )
    }
    assert backends.installable == {"codex": (Model("gpt", ()),)}
    assert backends.envs == ("local", "ssh")
    client.call.assert_called_once_with("flows.backends", {}, idem=None, seconds=None)


def test_a_set_up_is_written_with_only_what_was_said(client: mock.Mock) -> None:
    client.call.return_value = DECLARED

    flow = Flows(client).setup(
        "/w",
        "tells",
        agents={"teller": "claude/opus"},
        budget={"cost": 5},
        profile_flow=True,
        backup=[],
        idem="k",
    )

    assert flow.name == "tells"
    client.call.assert_called_once_with(
        "flows.setup",
        {
            "workspace": "/w",
            "flow": "tells",
            "agents": {"teller": "claude/opus"},
            "budget": {"cost": 5},
            "profile_flow": True,
            "backup": [],
        },
        idem="k",
        seconds=None,
    )


def test_an_epic_is_checked_and_what_was_found_is_typed(client: mock.Mock) -> None:
    said = {
        "flow": "tells",
        "ref": "tells:tells",
        "declared": DECLARED,
        "names": {"teller": "claude-opus"},
        "budget": {"cost": 5.0},
        "backup": ["origin"],
        "unreadable": "",
    }
    client.call.return_value = said

    checked = Flows(client).check(
        "/w", "tells", params={"rounds": "4"}, budget={"cost": 5}, resume=True
    )

    assert (checked.flow, checked.ref) == ("tells", "tells:tells")
    assert checked.declared.agents[0].name == "teller"
    assert checked.names == {"teller": "claude-opus"}
    assert checked.budget == {"cost": 5.0}
    assert checked.backup == ("origin",)
    assert checked.unreadable == ""
    assert checked.answer == said
    client.call.assert_called_once_with(
        "flows.check",
        {
            "workspace": "/w",
            "flow": "tells",
            "params": {"rounds": "4"},
            "budget": {"cost": 5},
            "resume": True,
        },
        idem=None,
        seconds=None,
    )


def test_a_flow_is_forked_once_under_a_key(client: mock.Mock) -> None:
    client.call.return_value = {"said": "copied tells to /w/x", "at": "/w/x"}

    assert Flows(client).fork("/w", "tells", idem="k") == Forked(
        "copied tells to /w/x", "/w/x"
    )
    client.call.assert_called_once_with(
        "flows.fork", {"workspace": "/w", "flow": "tells"}, idem="k", seconds=None
    )


def test_the_flowverses_are_listed_with_what_is_installed_and_newer(
    client: mock.Mock,
) -> None:
    client.call.return_value = KEPT

    kept = Flowverses(client).list()

    assert kept.verses == (
        Verse(
            "team",
            "https://example.com/team.git",
            fetched=True,
            fixed=False,
            edited=False,
            installed=1,
        ),
    )
    assert kept.installed == (
        Installed("@team/review", "team", "review", "1.0.0", "acme/review", "abc"),
    )
    assert kept.updates == (Update("@team/review", "1.0.0", "1.1.0"),)
    assert kept.said == ""
    assert kept.answer == KEPT
    client.call.assert_called_once_with("flowverses.list", {}, idem=None, seconds=None)


def test_one_flowverse_is_every_flow_it_lists_and_every_release(
    client: mock.Mock,
) -> None:
    client.call.return_value = {
        "name": "team",
        "url": "",
        "fetched": True,
        "fixed": False,
        "edited": True,
        "flows": [
            {
                "listed": "review",
                "flow": "@team/review",
                "installed": "1.0.0",
                "releases": [
                    {
                        "version": "1.1.0-rc.1",
                        "description": "Reviews",
                        "prerelease": True,
                        "license": "MIT",
                        "repo": "acme/review",
                        "dependencies": {"plan": ">=1"},
                    }
                ],
            }
        ],
        "skipped": [{"at": "flows/x/flow.yaml", "why": "unreadable"}],
    }

    index = Flowverses(client).get("team")

    assert (index.name, index.url, index.fetched, index.fixed, index.edited) == (
        "team",
        "",
        True,
        False,
        True,
    )
    assert index.flows == (
        Listed(
            "review",
            "@team/review",
            "1.0.0",
            (
                Release(
                    "1.1.0-rc.1",
                    "Reviews",
                    prerelease=True,
                    license="MIT",
                    repo="acme/review",
                    dependencies={"plan": ">=1"},
                ),
            ),
        ),
    )
    assert index.skipped == (Skipped("flows/x/flow.yaml", "unreadable"),)
    client.call.assert_called_once_with(
        "flowverses.get", {"name": "team"}, idem=None, seconds=None
    )


@pytest.mark.parametrize(
    ("change", "given", "sent"),
    [
        ("add", ("acme/flows",), {"url": "acme/flows"}),
        ("add", ("acme/flows", "team"), {"url": "acme/flows", "name": "team"}),
        ("fetch", ("team",), {"name": "team"}),
        ("remove", ("team",), {"name": "team"}),
        ("install", ("@team/review",), {"flow": "@team/review"}),
        (
            "install",
            ("@team/review", "1.1.0"),
            {"flow": "@team/review", "version": "1.1.0"},
        ),
        ("uninstall", ("@team/review",), {"flow": "@team/review"}),
    ],
)
def test_a_change_to_the_flowverses_says_what_it_did(
    client: mock.Mock, change: str, given: tuple[str, ...], sent: dict[str, str]
) -> None:
    client.call.return_value = {"said": "done it"} | KEPT

    kept = getattr(Flowverses(client), change)(*given, idem="k")

    assert kept.said == "done it"
    assert kept.verses[0].name == "team"
    client.call.assert_called_once_with(
        f"flowverses.{change}", sent, idem="k", seconds=None
    )


def test_the_workspaces_are_listed_from_where_the_call_is_made(
    client: mock.Mock,
) -> None:
    client.call.return_value = KNOWN

    known = Workspaces(client).list("/here")

    assert known.here == "/here"
    assert known.workspaces == (
        Workspace(
            "/here",
            "here",
            2,
            1,
            "2026-01-01T00:00:00Z",
            running=True,
            here=True,
            there=True,
        ),
    )
    assert known.kept == ""
    assert known.answer == KNOWN
    client.call.assert_called_once_with(
        "workspaces.list", {"here": "/here"}, idem=None, seconds=None
    )


def test_a_workspace_is_added_and_forgotten(client: mock.Mock) -> None:
    client.call.return_value = {"kept": "/there"} | KNOWN

    assert Workspaces(client).add("~/there", idem="k").kept == "/there"
    client.call.assert_called_once_with(
        "workspaces.add", {"workspace": "~/there"}, idem="k", seconds=None
    )

    client.call.reset_mock()
    client.call.return_value = KNOWN

    assert Workspaces(client).forget("/there", "/here").workspaces[0].path == "/here"
    client.call.assert_called_once_with(
        "workspaces.forget",
        {"workspace": "/there", "here": "/here"},
        idem=None,
        seconds=None,
    )


def test_a_directory_is_listed_and_a_path_completed(client: mock.Mock) -> None:
    said = {
        "at": "~/code",
        "whole": "/home/me/code",
        "up": "~",
        "entries": [{"name": "app", "dir": True}, {"name": "notes", "dir": False}],
        "more": 3,
    }
    client.call.return_value = said

    found = Paths(client).list("~/code", files=True, env="ssh@box")

    assert (found.at, found.whole, found.up, found.more) == (
        "~/code",
        "/home/me/code",
        "~",
        3,
    )
    assert found.entries == (Entry("app", dir=True), Entry("notes", dir=False))
    assert found.answer == said
    client.call.assert_called_once_with(
        "paths.list",
        {"at": "~/code", "files": True, "env": "ssh@box"},
        idem=None,
        seconds=None,
    )

    client.call.reset_mock()
    client.call.return_value = {"paths": ["~/code/", "~/cold/"]}

    assert Paths(client).complete("~/co") == ["~/code/", "~/cold/"]
    client.call.assert_called_once_with(
        "paths.complete", {"typed": "~/co"}, idem=None, seconds=None
    )
