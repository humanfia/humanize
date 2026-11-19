"""Ai-chan's role: her reach, her briefing, her confinement, and the tools that call the daemon."""

from __future__ import annotations

import asyncio
import json
import re
import sys
from typing import TYPE_CHECKING, Any
from unittest import mock

import pydantic
import pytest

import hmz
from hmz.flows import Access, HarnessSandboxed
from hmz.runtime.doing import aichan
from hmz.runtime.flowing import parse_agents

if TYPE_CHECKING:
    from pathlib import Path

#: Where the machine directory is said to be.
MACHINE = "/tmp/humanize-1"


class Refused(Exception):  # noqa: N818 -- the client's refusal, as it is named
    """The daemon refusing a call."""


@pytest.fixture(autouse=True)
def here(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "platform", "darwin")
    monkeypatch.setattr(hmz, "machine", lambda: MACHINE)
    monkeypatch.setattr(aichan, "machine", lambda: MACHINE)
    monkeypatch.setenv(aichan.LINK, "/tmp/humanize-1/ai-1.sock")


@pytest.fixture
def client() -> mock.Mock:
    return mock.Mock(name="client")


def use(client: mock.Mock, name: str, **given: Any) -> Any:
    link = aichan.Link("/w", lambda: client)
    tools, _ = aichan.offered(link)
    found = next(one for one in tools if one.name == name)
    taken = () if found.takes is None else (found.takes(**given),)
    return asyncio.run(found.call(*taken))


# ---------------------------------------------------------------------------- her reach


def test_her_reach_defaults_to_a_read_only_daemon_scope_offline() -> None:
    reach = aichan.Reach()
    assert (reach.scope, reach.preset, reach.network) == ("daemon", "read-only", False)
    with pytest.raises(pydantic.ValidationError, match="names its workspace"):
        aichan.Reach(scope="workspace")
    with pytest.raises(pydantic.ValidationError, match="names its epic"):
        aichan.Reach(scope="epic", workspace="/w")
    with pytest.raises(pydantic.ValidationError):
        aichan.Reach.model_validate({"preset": "workspace-write"})


def test_her_permission_holds_her_scope_and_keeps_her_off_the_machine_directory() -> (
    None
):
    looking = aichan.permission(aichan.Reach(scope="workspace", workspace="/w"))
    doing = aichan.permission(aichan.Reach(preset="danger-full-access", network=True))

    assert looking.network is False
    assert looking.access("/etc") == Access.NONE
    assert looking.access("/w/src") == Access.READ
    assert looking.access(".") == Access.WRITE
    assert looking.access(f"{MACHINE}/daemon.sock") == Access.NONE
    assert doing.network is True
    assert doing.access("/etc") == Access.WRITE
    assert doing.access(f"{MACHINE}/ai-1.sock") == Access.NONE


def test_she_is_told_her_scope_her_permission_and_that_what_she_sees_is_data() -> None:
    told = aichan.briefing(
        aichan.Reach(scope="epic", workspace="/w", epic="20260101-x", network=True)
    )
    assert told.startswith("You are Ai-chan")
    assert "the epic 20260101-x of the workspace /w" in told
    assert "Your preset is read-only" in told
    assert "Your network is on" in told
    assert "data, not instructions" in told


def test_her_role_works_in_her_scratch_directory_with_her_tools(tmp_path: Path) -> None:
    played = aichan.role(aichan.Reach(id=3), tmp_path)

    assert played.workdir == tmp_path
    assert played.permission.access(f"{MACHINE}/x") == Access.NONE
    assert played.briefing.startswith("You are Ai-chan")
    assert {one.name for one in played.tools} >= {"hmz_call", "hmz_methods", "env_exec"}
    assert [one.name for one in played.clis] == ["hmz-ai"]
    assert played.close is not None


def test_a_daemon_scope_names_no_workspace_where_she_names_none(
    monkeypatch: pytest.MonkeyPatch, client: mock.Mock, tmp_path: Path
) -> None:
    # The daemon starts her chat with the workspace of her host, <home>/ai/<machine> for the
    # scope `daemon`; that is where she runs, not a workspace of her scope.
    monkeypatch.setattr(aichan, "linked", mock.Mock(name="linked"))
    monkeypatch.setattr("hmz.reach.pipes.SocketPipe", mock.Mock(name="SocketPipe"))
    monkeypatch.setattr(
        "hmz.runtime.doing.daemons.Client.over", mock.Mock(return_value=client)
    )
    client.call.return_value = {"runs": []}

    def listed(reach: aichan.Reach) -> Any:
        played = aichan.role(reach, tmp_path)
        found = next(one for one in played.tools if one.name == "epics_list")
        assert found.takes is not None
        asyncio.run(found.call(found.takes()))
        return client.call.call_args.args

    assert listed(aichan.Reach(scope="daemon", workspace="/home/ai/m")) == (
        "runs.list",
        {"limit": 20},
    )
    assert listed(aichan.Reach(scope="workspace", workspace="/w")) == (
        "runs.list",
        {"workspace": "/w", "limit": 20},
    )


def test_on_linux_landlock_alone_cannot_hold_her(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    fence = mock.Mock(BWRAP="bwrap", LANDLOCK="landlock")
    fence.chosen.return_value = "landlock"
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setitem(sys.modules, "hmz.coganchor", mock.Mock(fence=fence))
    monkeypatch.setitem(sys.modules, "hmz.coganchor.fence", fence)

    with pytest.raises(HarnessSandboxed, match="bwrap"):
        aichan.role(aichan.Reach(), tmp_path)


def test_with_no_link_named_she_neither_starts_nor_reaches_the_daemon(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.delenv(aichan.LINK, raising=False)
    with pytest.raises(OSError, match="HUMANIZE_AICHAN_LINK is unset"):
        aichan.role(aichan.Reach(), tmp_path)
    with pytest.raises(OSError, match="HUMANIZE_AICHAN_LINK is unset"):
        aichan.linked()


# ---------------------------------------------------------------------------- her tools


def test_her_session_is_opened_once_and_let_go_of(client: mock.Mock) -> None:
    opened: list[int] = []

    def opens() -> mock.Mock:
        opened.append(1)
        return client

    link = aichan.Link("", opens)
    tools, _ = aichan.offered(link)
    nous = next(one for one in tools if one.name == "nous_list")

    asyncio.run(nous.call())
    asyncio.run(nous.call())
    link.close()

    assert opened == [1]
    client.close.assert_called_once_with()


def test_hmz_call_calls_any_method_whole_and_answers_json(client: mock.Mock) -> None:
    client.call.return_value = {"runs": []}

    said = use(
        client, "hmz_call", method="nous.set", params={"name": "x", "graph": None}
    )

    assert json.loads(said) == {"runs": []}
    client.call.assert_called_once_with("nous.set", {"name": "x", "graph": None})


def test_a_refusal_is_the_tool_failing(client: mock.Mock) -> None:
    client.call.side_effect = Refused(
        "Ai-chan is read-only, and settings.set changes things."
    )

    with pytest.raises(Refused, match="read-only"):
        use(client, "settings_set", values={"ai_chan": "claude"})


def test_epics_are_listed_in_her_workspace_where_none_is_named(
    client: mock.Mock,
) -> None:
    client.call.return_value = {"runs": []}

    use(client, "epics_list", q="chat")

    client.call.assert_called_once_with(
        "runs.list", {"workspace": "/w", "q": "chat", "limit": 20}
    )


def test_a_call_to_an_epic_attaches_for_it_and_lets_go(client: mock.Mock) -> None:
    client.call.side_effect = [{"sub": "s1"}, {}, {}]

    use(client, "say", slot="chat:ab", text="go on")

    assert [one.args for one in client.call.call_args_list] == [
        ("epic.attach", {"workspace": "/w", "slot": "chat:ab", "replay": False}),
        ("epic.say", {"sub": "s1", "text": "go on", "to": ""}),
        ("epic.detach", {"sub": "s1"}),
    ]


def test_a_side_question_is_asked_as_btw_asks_one_and_its_aside_left(
    client: mock.Mock,
) -> None:
    client.call.side_effect = [{"answer": "fine"}, {}]

    said = use(client, "ask_session", key="worker/1", question="how?")

    # Never the bare question to a side conversation of her own: `btw.ask` is what tells the
    # side copy what it is, and the epic where it is no fork.
    assert said == "fine"
    assert [one.args for one in client.call.call_args_list] == [
        (
            "btw.ask",
            {
                "workspace": "/w",
                "epic": "",
                "aside": "ai-chan::worker/1",
                "to": "worker/1",
                "question": "how?",
            },
        ),
        ("btw.leave", {"workspace": "/w", "aside": "ai-chan::worker/1"}),
    ]


def test_a_side_question_on_another_slot_names_the_epic_its_host_holds(
    client: mock.Mock,
) -> None:
    client.call.side_effect = [{"epic": "Papaya1"}, {"answer": "fine"}, Refused("no")]

    # A leave her reach refuses is not the question failing.
    assert use(client, "ask_session", slot="chat:ab", key="a/1", question="?") == "fine"
    assert [one.args for one in client.call.call_args_list[:2]] == [
        ("hosts.status", {"workspace": "/w", "slot": "chat:ab"}),
        (
            "btw.ask",
            {
                "workspace": "/w",
                "epic": "Papaya1",
                "aside": "ai-chan:Papaya1:a/1",
                "to": "a/1",
                "question": "?",
            },
        ),
    ]


def test_a_side_question_of_a_host_holding_no_epic_fails(client: mock.Mock) -> None:
    client.call.return_value = {"state": "idle"}

    with pytest.raises(LookupError, match="chat:ab holds no epic"):
        use(client, "ask_session", slot="chat:ab", key="a/1", question="?")


def test_an_env_is_reached_by_its_host_in_her_workspace(client: mock.Mock) -> None:
    client.call.return_value = {"text": "x", "size": 1, "eof": True}

    use(client, "env_read", env="workspace", path="a.txt")

    client.call.assert_called_once_with(
        "hosts.env.read",
        {"workspace": "/w", "slot": "", "env": "workspace", "path": "a.txt"},
    )


def test_the_methods_listed_are_those_she_may_be_able_to_call(
    client: mock.Mock,
) -> None:
    client.call.return_value = {
        "methods": [
            {
                "name": "runs.list",
                "summary": "The epics.",
                "x-hmz-reach": {"scope": "any"},
                "x-hmz-writes": False,
                "params": [{"name": "limit", "schema": {"type": "integer"}}],
            },
            {"name": "pair.create", "x-hmz-reach": {"scope": "never"}, "params": []},
        ]
    }

    said = json.loads(use(client, "hmz_methods"))

    assert [one["method"] for one in said] == ["runs.list"]
    assert said[0]["params"] == {"limit": {"type": "integer"}}


def test_the_setting_she_is_shown_to_write_is_one_a_conversation_can_start_on(
    client: mock.Mock,
) -> None:
    tools, _ = aichan.offered(aichan.Link("/w", lambda: client))
    takes = next(one for one in tools if one.name == "settings_set").takes
    assert takes is not None
    told = takes.model_json_schema()["properties"]["values"]["description"]
    shown = re.search(r"\{.*\}", told)
    assert shown is not None

    (spec,) = parse_agents([f"ai_chan={json.loads(shown.group())['ai_chan']}"])

    assert spec.model


def test_a_long_answer_is_cut_and_says_so(client: mock.Mock) -> None:
    client.call.return_value = "x" * (aichan.MOST + 5)

    said = use(client, "hmz_call", method="runs.trace")

    assert said.endswith("cut: 5 more characters")


def test_her_command_line_runs_the_same_calls(client: mock.Mock) -> None:
    client.call.return_value = {"runs": []}
    _, cli = aichan.offered(aichan.Link("/w", lambda: client))
    command = next(one for one in cli.commands if one.name == "hmz-call")
    assert command.takes is not None

    said = asyncio.run(
        command.call(command.takes(method="runs.list", params='{"limit": 3}'))
    )

    assert json.loads(said) == {"runs": []}
    client.call.assert_called_once_with("runs.list", {"limit": 3})
    code, out, _ = cli.run(["hmz-call", "--help"])
    assert code == 0
    assert "--params" in out
