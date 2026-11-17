"""`hmz.coganchor.agents.pi`: one pi process in RPC mode, held open across turns."""

from __future__ import annotations

import errno
import json
from typing import TYPE_CHECKING, Any

import pytest

from hmz.coganchor import fence
from hmz.coganchor.agents import (
    Failed,
    PiAgent,
    PiAgentConfig,
    PiSession,
    driver,
)
from hmz.coganchor.agents.native import NativeCommand
from hmz.coganchor.agents.pi import listed
from hmz.coganchor.agents.skills import Loaded
from hmz.coganchor.fence import Fence

from .doubles_u4 import fenceable
from .doubles_u5 import (
    configured,
    heard,
    housed,
    line,
    option,
    routing,
    spawning,
)

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable
    from pathlib import Path

    from hmz.coganchor.agents.event import Event, Question


@pytest.fixture(autouse=True)
def _home(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """A home of the test's own, so that no `models.json` of whoever runs it is read."""
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.delenv("PI_CODING_AGENT_DIR", raising=False)
    monkeypatch.delenv("NODE_COMPILE_CACHE", raising=False)


def _agent(**said: Any) -> PiAgent:
    return PiAgent(PiAgentConfig(**configured("anthropic/sonnet", said)))


def _part(**event: Any) -> str:
    return line({"type": "message_update", "assistantMessageEvent": event})


def _ended(*content: dict[str, Any], **more: Any) -> str:
    return line(
        {
            "type": "message_end",
            "message": {
                "role": "assistant",
                "content": list(content),
                "usage": {"input": 5, "output": 2, "cacheRead": 1},
                **more,
            },
        }
    )


_SETTLED = line({"type": "agent_settled"})

#: What pi says in RPC mode for one prompt.
_SAID = (
    line({"type": "response", "command": "prompt", "success": True}),
    _part(type="thinking_end", content="hmm"),
    _part(type="toolcall_start", contentIndex=1, id="c1", toolName="bash"),
    _part(type="toolcall_delta", contentIndex=1, delta='{"command": "ls -la"'),
    _part(
        type="toolcall_end",
        contentIndex=1,
        toolCall={"id": "c1", "name": "bash", "arguments": {"command": "ls -la"}},
    ),
    _part(type="text_end", content="done"),
    "plain words pi printed\n",
    _ended({"type": "text", "text": "done"}),
    _SETTLED,
)


def _rpc(*said: str) -> Callable[[str], Iterable[str]]:
    """Answers every prompt with `said`, and every other line with nothing."""

    def answers(told: str) -> Iterable[str]:
        return said if json.loads(told).get("type") == "prompt" else ()

    return answers


def _told(told: list[str]) -> list[dict[str, Any]]:
    return [json.loads(one) for one in told]


def _turn(session: PiSession, prompt: str = "do it") -> list[Event]:
    return list(session.stream(prompt))


def test_pi_is_driven_by_its_own_classes() -> None:
    assert driver("pi") == (PiAgent, PiAgentConfig)
    agent = _agent()
    assert agent.backend == "pi"
    assert isinstance(agent.new(), PiSession)
    assert PiAgent.counts == {"input", "output", "cache_read", "cache_write"}
    assert PiSession.steers


@pytest.mark.parametrize("field", ["append_system_prompt", "skill_paths"])
def test_one_entry_where_a_sequence_belongs_is_refused(field: str) -> None:
    with pytest.raises(TypeError, match=field):
        PiAgentConfig(**configured("m", {field: "one entry"}))


@pytest.mark.parametrize("field", ["append_system_prompt", "skill_paths"])
def test_an_entry_saying_nothing_is_refused(field: str) -> None:
    with pytest.raises(ValueError, match=field):
        PiAgentConfig(**configured("m", {field: ("fine", "  ")}))


def test_a_turn_is_a_prompt_line_and_what_pi_says_until_it_settles(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    spawned = spawning(monkeypatch, answers=_rpc(*_SAID))
    agent = _agent()
    heard(agent)
    session = agent.new(tmp_path)
    assert session.named is None

    events = _turn(session, "hello")

    (process,) = spawned
    argv = process.args
    assert argv[:5] == ["pi", "--mode", "rpc", "--model", "anthropic/sonnet"]
    assert "--thinking" not in argv
    assert _told(process.told) == [{"type": "prompt", "message": "hello"}]
    assert [(one.kind, one.text) for one in events] == [
        ("reasoning", "hmm"),
        ("tool", "bash ls -la"),
        ("text", "done"),
        ("result", "done"),
    ]
    assert dict(events[-1].spent) == {"input": 5, "output": 2, "cache_read": 1}
    assert events[-1].tokens == {"anthropic/sonnet": 8}
    assert session.id == option(argv, "--session-id")
    assert session.named == session.id


def test_the_process_is_held_open_and_told_a_new_effort_in_line(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    spawned = spawning(monkeypatch, answers=_rpc(*_SAID))
    agent = _agent(effort="low")
    heard(agent)
    session = agent.new(tmp_path)

    _turn(session, "one")
    session.effort = "high"
    _turn(session, "two")

    (process,) = spawned
    assert option(process.args, "--thinking") == "low"
    assert _told(process.told) == [
        {"type": "prompt", "message": "one"},
        {"type": "set_thinking_level", "level": "high"},
        {"type": "prompt", "message": "two"},
    ]


@pytest.mark.parametrize(
    ("said", "flags"),
    [
        ({"effort": "medium"}, ["--thinking", "medium"]),
        (
            {"append_system_prompt": ("be brief", "be kind")},
            ["--append-system-prompt", "be brief", "--append-system-prompt", "be kind"],
        ),
        ({"skill_paths": ("/skills",)}, ["--skill", "/skills"]),
        ({"context_files": False}, ["--no-context-files"]),
        ({"extensions": False}, ["--no-extensions"]),
        ({"offline": True}, ["--offline"]),
    ],
)
def test_what_the_agent_is_configured_with_goes_on_the_command_line(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    said: dict[str, Any],
    flags: list[str],
) -> None:
    spawned = spawning(monkeypatch, answers=_rpc(*_SAID))
    agent = _agent(**said)
    heard(agent)

    _turn(agent.new(tmp_path))

    argv = spawned[0].args
    at = argv.index(flags[0])
    assert argv[at : at + len(flags)] == flags


@pytest.mark.parametrize(
    ("writes", "withheld"),
    [(None, None), (False, "edit,write"), (True, None)],
)
def test_a_fence_that_writes_nothing_withholds_the_writing_tools_and_keeps_the_shell(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    writes: bool | None,
    withheld: str | None,
) -> None:
    monkeypatch.setattr(fence, "enforceable", fenceable)
    spawned = spawning(monkeypatch, answers=_rpc(*_SAID))
    work = tmp_path / "work"
    work.mkdir()
    drawn = {
        None: None,
        False: Fence(read=("/",)),
        True: Fence(read=("/",), write=(str(work),)),
    }[writes]
    agent = _agent(fence=drawn)
    heard(agent)

    _turn(agent.new(work))

    assert option(spawned[0].args, "--exclude-tools") == withheld


@pytest.mark.parametrize(
    ("before", "after", "restarted"),
    [
        ("writes", "reads", "edit,write"),
        ("reads", "writes", None),
        (None, "reads", "edit,write"),
        ("reads", "reads", False),
    ],
)
def test_a_fence_moved_by_reconfiguring_is_a_process_given_the_tools_it_allows(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    before: str | None,
    after: str,
    restarted: str | bool | None,
) -> None:
    monkeypatch.setattr(fence, "enforceable", fenceable)
    spawned = spawning(monkeypatch, answers=_rpc(*_SAID))
    work = tmp_path / "work"
    work.mkdir()
    drawn = {
        None: None,
        "reads": Fence(read=("/",)),
        "writes": Fence(read=("/",), write=(str(work),)),
    }
    agent = _agent(fence=drawn[before])
    heard(agent)
    session = agent.new(work)
    _turn(session, "one")

    agent.reconfigure(
        PiAgentConfig(**configured("anthropic/sonnet", {"fence": drawn[after]}))
    )
    _turn(session, "two")

    if restarted is False:
        assert len(spawned) == 1
    else:
        _, second = spawned
        assert option(second.args, "--exclude-tools") == restarted


def test_a_fence_that_cuts_the_network_runs_pi_offline(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(fence, "enforceable", fenceable)
    spawned = spawning(monkeypatch, answers=_rpc(*_SAID))
    agent = _agent(fence=Fence(online=False))
    heard(agent)

    _turn(agent.new(tmp_path))

    assert "--offline" in spawned[0].args


def test_a_bare_agent_adds_nothing_to_the_command_line(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    spawned = spawning(monkeypatch, answers=_rpc(*_SAID))
    agent = _agent(compiled=False)
    heard(agent)

    _turn(agent.new(tmp_path))

    (process,) = spawned
    assert len(process.args) == 7  # pi --mode rpc --model M --session-id ID
    assert "NODE_COMPILE_CACHE" not in (process.env or {})


def test_a_prompt_pi_refuses_fails_the_turn(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    refused = {
        "type": "response",
        "command": "prompt",
        "success": False,
        "error": "no model by that name",
    }
    spawning(monkeypatch, answers=_rpc(line(refused)))
    agent = _agent()
    heard(agent)

    with pytest.raises(Failed) as failed:
        _turn(agent.new(tmp_path))

    assert failed.value.output == "no model by that name"


@pytest.mark.parametrize("refused", ["launch", "prompt", ""])
def test_a_session_is_named_only_once_pi_has_taken_a_prompt_into_it(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, refused: str
) -> None:
    no = {"type": "response", "command": "prompt", "success": False, "error": "no"}
    taken = {"type": "response", "command": "prompt", "success": True}
    answers = (
        _rpc(line(no))
        if refused == "prompt"
        else _rpc(line(taken), _ended(errorMessage="cut short"), _SETTLED)
    )
    spawned = spawning(monkeypatch, answers=answers)
    agent = _agent()
    heard(agent)
    session = agent.new(tmp_path)
    launching: list[str | None] = []
    if refused == "launch":

        def refuse(*_: object) -> list[str]:
            launching.append(session.named)
            raise FileNotFoundError(errno.ENOENT, "no pi here")

        monkeypatch.setattr(agent, "spawned", refuse)

    with pytest.raises(Failed):
        _turn(session)

    # The id a process is asked to open is no name of pi's until pi has taken a prompt into
    # it: not while it is starting, and not once a turn it never took has failed. One it took
    # is named, though the turn failed after it.
    assert launching == ([None] if refused == "launch" else [])
    if refused:
        assert session.named is None
    else:
        (process,) = spawned
        assert session.named == option(process.args, "--session-id")


def test_a_turn_that_errs_without_saying_anything_fails(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    spawning(
        monkeypatch,
        answers=_rpc(_ended(errorMessage="the request was cut short"), _SETTLED),
    )
    agent = _agent()
    heard(agent)

    with pytest.raises(Failed) as failed:
        _turn(agent.new(tmp_path))

    assert failed.value.output == "the request was cut short"


def _asking(method: str, **asked: Any) -> str:
    return line(
        {"type": "extension_ui_request", "id": "ui-1", "method": method, **asked}
    )


@pytest.mark.parametrize(
    ("method", "answer", "replied"),
    [
        ("confirm", "no", {"confirmed": False}),
        ("confirm", "yes", {"confirmed": True}),
        ("select", "b", {"value": "b"}),
        ("input", "typed", {"value": "typed"}),
        ("confirm", None, {"cancelled": True}),
    ],
)
def test_what_an_extension_asks_mid_turn_is_put_to_whoever_drives_the_agent(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    method: str,
    answer: str | None,
    replied: dict[str, Any],
) -> None:
    spawned = spawning(
        monkeypatch,
        answers=_rpc(_asking(method, title="go on?", options=["a", "b"]), *_SAID),
    )
    agent = _agent()
    heard(agent)
    questions: list[Question] = []

    def ask(question: Question) -> str | None:
        questions.append(question)
        return answer

    agent.ask = ask

    _turn(agent.new(tmp_path))

    assert questions[0].text == "go on?"
    replies = [
        one for one in _told(spawned[0].told) if one["type"] == "extension_ui_response"
    ]
    assert replies == [{"type": "extension_ui_response", "id": "ui-1", **replied}]


def test_a_notice_from_an_extension_is_not_answered(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    spawned = spawning(
        monkeypatch, answers=_rpc(_asking("notify", message="fyi"), *_SAID)
    )
    agent = _agent()
    heard(agent)

    _turn(agent.new(tmp_path))

    assert [one["type"] for one in _told(spawned[0].told)] == ["prompt"]


def test_a_word_put_in_with_no_turn_running_is_refused(tmp_path: Path) -> None:
    with pytest.raises(RuntimeError, match="no turn"):
        _agent().new(tmp_path).interject("hold on")


def _declared(tmp_path: Path, providers: dict[str, Any]) -> None:
    home = tmp_path / "home/.pi/agent"
    home.mkdir(parents=True)
    (home / "models.json").write_text(json.dumps({"providers": providers}))


def test_a_fence_lets_through_the_hosts_models_json_declares_for_the_model(
    tmp_path: Path,
) -> None:
    _declared(
        tmp_path,
        {
            "mine": {
                "baseUrl": "https://gw.example:8443/v1",
                "models": [{"id": "m", "baseUrl": "http://[::1]:9000"}],
            },
            "theirs": {"baseUrl": "https://elsewhere.example"},
        },
    )

    fence = _agent(model="mine/m", fence=Fence(online=False)).fenced()
    plain = _agent(model="nobody/m", fence=Fence(online=False)).fenced()

    assert fence is not None
    assert plain is not None
    assert set(fence.hosts) - set(plain.hosts) == {"gw.example:8443", "[::1]:9000"}


def test_a_bare_model_name_reaches_every_provider_declared(tmp_path: Path) -> None:
    _declared(
        tmp_path,
        {"a": {"baseUrl": "https://a.example"}, "b": {"baseUrl": "https://b.example"}},
    )

    fence = _agent(model="bare", fence=Fence(online=False)).fenced()

    assert fence is not None
    assert {"a.example", "b.example"} <= set(fence.hosts)


def test_an_agent_without_a_fence_has_none() -> None:
    assert _agent().fenced() is None


def test_a_turn_through_a_gateway_declares_it_in_a_copy_of_the_user_s_models(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    routing(monkeypatch, "pi")
    _declared(tmp_path, {"mine": {"baseUrl": "https://gw.example"}})
    models = tmp_path / "home/.pi/agent/models.json"
    before = models.read_bytes()
    spawned = spawning(monkeypatch, answers=_rpc(*_SAID))
    homes = housed(monkeypatch, "PI_CODING_AGENT_DIR")
    agent = _agent(model="openai/gpt-5", provider="gw")
    heard(agent)

    _turn(agent.new(tmp_path))

    (process,) = spawned
    (home,) = homes
    named = option(process.args, "--provider")
    assert named is not None
    assert json.loads(home["models.json"])["providers"] == {
        "mine": {"baseUrl": "https://gw.example"},
        named: {
            "baseUrl": "http://127.0.0.1:4321/v1",
            "api": "openai-completions",
            "apiKey": "$PI_GATEWAY_KEY",
            "models": [{"id": "openai/gpt-5"}],
        },
    }
    assert option(process.args, "--model") == "openai/gpt-5"
    env = process.env or {}
    assert env["PI_GATEWAY_KEY"] == "sk-master"
    assert "OPENAI_API_KEY" not in env
    assert "upstream-secret" not in json.dumps(env) + home["models.json"]
    assert models.read_bytes() == before


def test_the_flow_s_skills_are_lodged_in_the_virtual_home(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    skill = tmp_path / "flow/greet"
    skill.mkdir(parents=True)
    (skill / "SKILL.md").write_text("---\nname: greet\n---\n")
    spawning(monkeypatch, answers=_rpc(*_SAID))
    homes = housed(monkeypatch, "PI_CODING_AGENT_DIR")
    agent = _agent()
    agent.loads([Loaded("greet", skill)])
    heard(agent)
    work = tmp_path / "work"
    work.mkdir()

    _turn(agent.new(work))

    (home,) = homes
    assert "skills/greet/SKILL.md" in home
    assert list(work.iterdir()) == []


#: What pi lists for `get_commands`: a template, a skill and an extension's command.
_COMMANDS = [
    {"name": "fix-tests", "description": "Fix failing tests", "source": "prompt"},
    {"name": "skill:review", "description": "Review it", "source": "skill"},
    {"name": "deploy", "source": "extension"},
]


def _natively(told: str) -> Iterable[str]:
    """What `pi --mode rpc` answers each command a native turn may be served by with."""
    said: dict[str, Any] = json.loads(told)
    match said["type"]:
        case "get_commands":
            data: dict[str, Any] = {"commands": _COMMANDS}
        case "bash":
            data = {"output": "out\n", "exitCode": 2, "cancelled": False}
        case "compact":
            data = {"summary": "s", "tokensBefore": 900, "usage": {"input": 7}}
        case "prompt":
            return _SAID
        case _:
            return ()
    return (
        line(
            {
                "type": "response",
                "id": said.get("id"),
                "command": said["type"],
                "success": True,
                "data": data,
            }
        ),
    )


def _entries(session: PiSession) -> list[tuple[str, str, str]]:
    return [(one.sigil, one.name, one.how) for one in session.natives()]


def test_the_catalog_asked_for_has_the_next_process_list_its_commands(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    spawned = spawning(monkeypatch, answers=_natively)
    agent = _agent()
    heard(agent)
    session = agent.new(tmp_path)
    assert _entries(session) == [
        ("!", "", "call"),
        ("!", "!", "call"),
        ("/", "compact", "call"),
    ]

    _turn(session, "one")
    _turn(session, "two")

    assert [one["type"] for one in _told(spawned[0].told)] == [
        "get_commands",
        "prompt",
        "prompt",
    ]
    assert _entries(session) == [
        ("!", "", "call"),
        ("!", "!", "call"),
        ("/", "compact", "call"),
        ("/", "fix-tests", "pass"),
        ("/", "skill:review", "pass"),
        ("/", "deploy", "pass"),
    ]
    assert session.natives()[3].about == "Fix failing tests"


@pytest.mark.parametrize(
    ("typed", "told", "answer"),
    [
        (
            "!ls -la",
            {"type": "bash", "command": "ls -la", "id": "hmz-native"},
            "out\n(exit code 2)",
        ),
        (
            "!! ls",
            {
                "type": "bash",
                "command": "ls",
                "excludeFromContext": True,
                "id": "hmz-native",
            },
            "out\n(exit code 2)",
        ),
        (
            "/compact",
            {"type": "compact", "id": "hmz-native"},
            "compacted from 900 tokens",
        ),
        (
            "/compact keep the tests",
            {
                "type": "compact",
                "customInstructions": "keep the tests",
                "id": "hmz-native",
            },
            "compacted from 900 tokens",
        ),
        (
            "/skill:review now",
            {"type": "prompt", "message": "/skill:review now"},
            "done",
        ),
    ],
)
def test_a_native_turn_is_served_by_the_command_of_pis_own_for_it(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    typed: str,
    told: dict[str, Any],
    answer: str,
) -> None:
    spawned = spawning(monkeypatch, answers=_natively)
    agent = _agent()
    heard(agent)
    session = agent.new(tmp_path)
    _turn(session, "hello")

    events = list(session.stream(typed, native=True))

    assert _told(spawned[0].told)[-1] == told
    assert events[-1].kind == "result"
    assert events[-1].text == answer
    assert not session.native_turn


def test_a_compaction_is_charged_to_its_turn(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    spawned = spawning(monkeypatch, answers=_natively)
    agent = _agent()
    heard(agent)
    session = agent.new(tmp_path)

    (result,) = list(session.stream("/compact", native=True))

    assert dict(result.spent) == {"input": 7}
    assert result.tokens == {"anthropic/sonnet": 7}
    # The first turn, and the session it was taken into is the session's from here.
    assert session.id == option(spawned[0].args, "--session-id")


@pytest.mark.parametrize("typed", ["!ls", "/compact", "!!ls"])
def test_a_flows_prompt_is_never_read_as_native_input(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, typed: str
) -> None:
    spawned = spawning(monkeypatch, answers=_natively)
    agent = _agent()
    heard(agent)

    _turn(agent.new(tmp_path), typed)

    assert _told(spawned[0].told)[-1] == {"type": "prompt", "message": typed}


def test_a_native_command_pi_refuses_is_a_failed_turn(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    refused = line(
        {
            "type": "response",
            "id": "hmz-native",
            "command": "compact",
            "success": False,
            "error": "Already compacted",
        }
    )
    spawning(
        monkeypatch, answers=lambda told: (refused,) if '"compact"' in told else ()
    )
    agent = _agent()
    heard(agent)

    with pytest.raises(Failed, match="Already compacted"):
        list(agent.new(tmp_path).stream("/compact", native=True))


def test_a_prompt_pi_handles_itself_is_a_turn_over(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    handled = line(
        {
            "type": "response",
            "command": "prompt",
            "success": True,
            "data": {"disposition": "handled"},
        }
    )
    spawning(monkeypatch, answers=lambda told: (handled,) if '"prompt"' in told else ())
    agent = _agent()
    heard(agent)

    events = list(agent.new(tmp_path).stream("/deploy", native=True))

    assert [one.kind for one in events] == ["result"]


def test_listed_reads_names_and_aliases_and_leaves_compact_to_its_command() -> None:
    entries = listed(
        [
            {"name": "compact", "source": "builtin"},
            {"name": "plan", "aliases": ["p"], "description": "Plan it"},
            {"name": "ship", "aliases": "sh", "description": "Ship it"},
            "nonsense",
            {"description": "no name"},
        ]
    )

    assert entries == [
        NativeCommand("/", "plan", "Plan it", "pass"),
        NativeCommand("/", "p", "Plan it", "pass"),
        NativeCommand("/", "ship", "Ship it", "pass"),
    ]
    assert listed(None) == []
