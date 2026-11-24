"""`hmz.coganchor.agents.agy`: Antigravity's CLI held open on stream-json, or one `--print`."""

from __future__ import annotations

import dataclasses
import itertools
import json
import math
import os
import pathlib
import sys
import tempfile
from typing import TYPE_CHECKING, Any

import pytest

from hmz.coganchor import fence, gateway, providers
from hmz.coganchor.agents import (
    AntigravityCLIAgent,
    AntigravityCLIAgentConfig,
    AntigravityCLISession,
    Failed,
    FakeTool,
    Toolbox,
    driver,
)
from hmz.coganchor.agents.config import Unserved
from hmz.coganchor.fence import Fence
from hmz.coganchor.homes import build
from hmz.coganchor.providers import Provider

from .doubles_u4 import fenceable
from .doubles_u5 import afar, carried, configured, heard, line, option, spawning

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable
    from pathlib import Path

    from hmz.coganchor.agents.event import Event


@pytest.fixture(autouse=True)
def _home(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """A home of the test's own: the agents agy is held to are files written into it."""
    monkeypatch.setenv("HOME", str(tmp_path / "home"))


@pytest.fixture(autouse=True)
def admin(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """Where agy's admin settings are read: a file of the test's own, which none writes."""
    where = tmp_path / "admin_settings.json"
    monkeypatch.setattr(AntigravityCLIAgent, "admin", where)
    return where


def _agent(**said: Any) -> AntigravityCLIAgent:
    return AntigravityCLIAgent(
        AntigravityCLIAgentConfig(**configured("gemini-3-pro", said))
    )


def _step(**told: Any) -> str:
    return line({"event": "step_update", "step_update": told})


def _result(usage: dict[str, int] | None = None, **told: Any) -> str:
    said = {"response": "done", "status": "SUCCESS", "usage": usage or {}} | told
    return line({"event": "result", "conversation_id": "cv-1", "result": said})


_USAGE = {"input_tokens": 5, "output_tokens": 3, "thinking_tokens": 2}

#: What agy says, a turn at a time, with `--output-format stream-json`.
_SAID = (
    _step(text_delta="hmm", step_type="THINKING"),
    _step(tool_name="view_file", state="RUNNING", tool_info={"path": "a.py"}),
    _step(tool_name="view_file", state="DONE", tool_info={"path": "a.py"}),
    _step(text_delta="do", step_type="TEXT"),
    _step(text_delta="ne", step_type="TEXT"),
    "a plain line\n",
    _result(_USAGE),
)


def _answering(*said: str) -> Callable[[str], Iterable[str]]:
    def answers(told: str) -> Iterable[str]:
        del told
        return said

    return answers


def _turn(session: AntigravityCLISession, prompt: str = "do it") -> list[Event]:
    return list(session.stream(prompt))


def test_agy_is_driven_by_its_own_classes() -> None:
    assert driver("agy") == (AntigravityCLIAgent, AntigravityCLIAgentConfig)
    agent = _agent()
    assert agent.backend == "agy"
    assert isinstance(agent.new(), AntigravityCLISession)
    assert AntigravityCLIAgent.counts == {"input", "output", "reasoning", "cache_read"}


@pytest.mark.parametrize("seconds", [0.0, -1.0, math.inf, math.nan, 1e12])
def test_a_print_timeout_that_is_no_number_of_seconds_is_refused(
    seconds: float,
) -> None:
    with pytest.raises(ValueError, match="print_timeout"):
        AntigravityCLIAgentConfig(model="m", effort="", print_timeout=seconds)


def _held(*, writes: bool = False, online: bool = True) -> Fence:
    """A fence drawn from one rule over the working directory, which writes it or reads it."""
    return Fence.of(
        rules=[(".", "write" if writes else "read")],
        online=online,
        workdir="/work",
        home="/home/someone",
    )


@pytest.fixture(autouse=True)
def _fenceable(monkeypatch: pytest.MonkeyPatch) -> None:
    """A machine that can put up any fence."""
    monkeypatch.setattr(fence, "enforceable", fenceable)


def test_a_fence_writing_nothing_is_served_without_slash_commands() -> None:
    config = AntigravityCLIAgentConfig(
        **configured("gemini-3-pro", {"fence": _held(), "disable_slash_commands": True})
    )
    assert AntigravityCLIAgent(config).config is config


def test_a_fence_is_held_from_outside_whatever_it_is() -> None:
    fence = Fence(online=False)
    assert _agent().natively(fence) is fence


def test_a_turn_is_a_user_line_and_the_steps_it_answers_with(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    spawned = spawning(monkeypatch, answers=_answering(*_SAID))
    agent = _agent()
    heard(agent)
    session = agent.new(tmp_path)

    events = _turn(session, "hello")

    (process,) = spawned
    named, _, home = process.args[1].partition("=")
    assert named == "--app_data_dir"
    assert not home.startswith("/")  # agy takes it relative to ~/.gemini, and only so
    assert [process.args[0], *process.args[2:]] == [
        "agy",
        "--output-format",
        "stream-json",
        "--model",
        "gemini-3-pro",
        "--print-timeout",
        "86400.000s",
        "--add-dir",
        str(tmp_path),
        "--input-format",
        "stream-json",
    ]
    assert [json.loads(one) for one in process.told] == [
        {"event": "user", "message": {"content": "hello"}}
    ]
    assert [(one.kind, one.text) for one in events] == [
        ("reasoning", "hmm"),
        ("tool", "view_file a.py"),
        ("text", "done"),
        ("result", "done"),
    ]
    assert dict(events[-1].spent) == {"input": 5, "output": 3, "reasoning": 2}
    assert events[-1].tokens == {"gemini-3-pro": 10}
    assert session.id == "cv-1"


def test_what_a_turn_cost_is_what_the_running_total_rose_by(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    totals = iter(
        [_USAGE, {"input_tokens": 9, "output_tokens": 4, "thinking_tokens": 2}]
    )

    def answers(told: str) -> Iterable[str]:
        del told
        return [_result(next(totals))]

    spawned = spawning(monkeypatch, answers=answers)
    agent = _agent()
    heard(agent)
    session = agent.new(tmp_path)

    _turn(session)
    second = _turn(session)[-1]

    assert len(spawned) == 1
    assert dict(second.spent) == {"input": 4, "output": 1, "reasoning": 0}


@pytest.mark.parametrize(
    ("said", "flags"),
    [
        ({"fence": _held()}, ["--dangerously-skip-permissions"]),
        ({"fence": _held(writes=True)}, ["--dangerously-skip-permissions"]),
        ({"effort": "high"}, ["--effort", "high"]),
        ({"sandbox": True}, ["--sandbox"]),
        ({"disable_slash_commands": True}, ["--disable-slash-commands"]),
        ({"print_timeout": 90.5}, ["--print-timeout", "90.500s"]),
    ],
)
def test_what_the_agent_is_configured_with_goes_on_the_command_line(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    said: dict[str, Any],
    flags: list[str],
) -> None:
    spawned = spawning(monkeypatch, answers=_answering(*_SAID))
    agent = _agent(**said)
    heard(agent)

    _turn(agent.new(tmp_path))

    argv = spawned[0].args
    at = argv.index(flags[0])
    assert argv[at : at + len(flags)] == flags


def test_a_model_carrying_its_effort_is_not_told_another(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    spawned = spawning(monkeypatch, answers=_answering(*_SAID))
    agent = _agent(model="gemini-3-pro-low", effort="high")
    heard(agent)

    _turn(agent.new(tmp_path))

    assert "--effort" not in spawned[0].args


def test_without_the_workspace_added_no_directory_is(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    spawned = spawning(monkeypatch, answers=_answering(*_SAID))
    agent = _agent(add_workspace=False)
    heard(agent)

    _turn(agent.new(tmp_path))

    assert "--add-dir" not in spawned[0].args


@pytest.mark.parametrize(
    ("said", "named", "tools"),
    [
        (
            {"fence": _held()},
            "hmz-read-only",
            "view_file, grep_search, find_by_name, list_dir, run_command]",
        ),
        (
            {"fence": _held(), "web_search": True},
            "hmz-read-only-web",
            "run_command, read_url_content, search_web]",
        ),
        (
            {"fence": _held(online=False), "web_search": True},
            "hmz-read-only",
            "run_command]",
        ),
        ({"web_search": False}, "hmz-offline", "run_command"),
        ({"fence": _held(writes=True, online=False)}, "hmz-offline", "write_to_file"),
    ],
)
def test_what_it_may_reach_is_an_agent_of_humanize_written_into_its_virtual_home(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    said: dict[str, Any],
    named: str,
    tools: str,
) -> None:
    real = tmp_path / "home/.gemini/antigravity-cli"
    _card(real / "agents" / "mine.md", "the user's own")
    spawned = spawning(monkeypatch, answers=_answering(*_SAID))
    agent = _agent(**said)
    heard(agent)
    session = agent.new(tmp_path)

    _turn(session)

    argv = spawned[0].args
    argv = argv[argv.index("agy") :]  # past the fence it is started in, if any
    assert option(argv, "--agent") == named
    home = (tmp_path / "home/.gemini" / argv[1].partition("=")[2]).resolve()
    defined = home / "agents" / f"{named}.md"
    assert f"name: {named}" in defined.read_text()
    assert tools in defined.read_text()
    # Beside the user's own, which are linked rather than written to.
    assert (home / "agents" / "mine.md").read_text() == "the user's own"
    assert sorted(one.name for one in (real / "agents").iterdir()) == ["mine.md"]
    session.close()
    assert not home.exists()


def test_a_harness_on_another_machine_has_humanize_s_agents_written_there(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    spawned = spawning(monkeypatch, answers=_answering(*_SAID))
    agent = _agent(machine=afar(monkeypatch, tmp_path))
    heard(agent)

    _turn(agent.new(tmp_path))

    told = carried(spawned[0].args)
    assert told.flag == "--app_data_dir"
    far = tmp_path / "far"
    _card(far / ".gemini/antigravity-cli/agents/mine.md", "the user's own")
    home = build(told, {"HOME": str(far)}, under=tmp_path)
    assert home.argv[0].startswith("--app_data_dir=")
    assert sorted(one.name for one in (home.at / "agents").iterdir()) == [
        "hmz-offline.md",
        "hmz-read-only-web.md",
        "hmz-read-only.md",
        "mine.md",
    ]
    home.drop()
    assert [one.name for one in (far / ".gemini/antigravity-cli/agents").iterdir()] == [
        "mine.md"
    ]


def test_humanize_s_agents_hold_it_on_another_machine_whose_home_carries_them(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from hmz.coganchor.anchor import AnchorConfig
    from hmz.coganchor.machines import AnchoredConfig

    for machine in (
        afar(monkeypatch, tmp_path),
        AnchoredConfig(
            anchor=AnchorConfig(target="ssh://box", workspace=str(tmp_path))
        ),
    ):
        assert _agent(machine=machine, web_search=False).config.machine is machine


@pytest.mark.parametrize("said", [{"fence": _held()}, {"web_search": False}])
def test_a_native_turn_cannot_be_held_by_humanize_s_agents(
    tmp_path: Path, said: dict[str, Any]
) -> None:
    from hmz.coganchor.anchor import AnchorConfig
    from hmz.coganchor.machines import AnchoredConfig

    anchor = AnchorConfig(target="ssh://box", workspace=str(tmp_path), native=True)
    _agent(
        machine=AnchoredConfig(anchor=anchor)
    )  # unfenced, on the web: nothing to hold it
    with pytest.raises(Unserved, match="natively"):
        _agent(machine=AnchoredConfig(anchor=anchor), **said)


def _card(at: Path, text: str) -> None:
    at.parent.mkdir(parents=True, exist_ok=True)
    at.write_text(text, encoding="utf-8")


def _own(agent: AntigravityCLIAgent, monkeypatch: pytest.MonkeyPatch) -> None:
    """Puts the agent on an account that names a home of its own."""
    held = Provider("agy", "mine", way="login", args=("--app_data_dir=other",))
    monkeypatch.setattr(agent, "node", lambda: held)


def test_an_account_naming_its_own_home_runs_there(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    spawned = spawning(monkeypatch, answers=_answering(*_SAID))
    agent = _agent()
    _own(agent, monkeypatch)
    heard(agent)

    _turn(agent.new(tmp_path))

    assert agent.homed() is None
    named = [one for one in spawned[0].args if one.startswith("--app_data_dir")]
    assert named == ["--app_data_dir=other"]  # the account's, and no other


def test_an_account_naming_its_own_home_cannot_be_held_to_reading(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    agent = _agent(fence=_held())
    _own(agent, monkeypatch)

    with pytest.raises(Unserved, match="app_data_dir"):
        agent.homed()


@pytest.mark.parametrize("said", [{"fence": _held()}, {"web_search": False}])
def test_an_account_naming_its_own_home_is_refused_before_its_first_turn(
    monkeypatch: pytest.MonkeyPatch, said: dict[str, Any]
) -> None:
    held = Provider("agy", "mine", way="login", args=("--app_data_dir=other",))

    def find(cli: str, name: str) -> Provider:
        del cli, name
        return held

    monkeypatch.setattr(providers, "find", find)

    assert _agent(provider="mine").config.provider == "mine"
    with pytest.raises(Unserved, match="app_data_dir"):
        _agent(provider="mine", **said)


def test_the_plugin_carrying_the_flow_s_callbacks_is_let_through_its_fence(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    def address(_box: Toolbox) -> str:
        return str(tmp_path / "sock")

    def config(_box: Toolbox, named: str = "humanize") -> dict[str, Any]:
        del named
        return {}

    monkeypatch.setattr(Toolbox, "address", address)
    monkeypatch.setattr(Toolbox, "config", config)
    spawned = spawning(monkeypatch, answers=_answering(*_SAID))
    (tmp_path / "a").mkdir()
    (tmp_path / "t").mkdir()
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path / "t"))
    agent = _agent()
    heard(agent)
    session = agent.new(tmp_path / "a")
    session.offers([FakeTool("secret", "Says the secret word.", lambda: "")])

    _turn(session)

    argv = spawned[0].args
    plugin = [b for a, b in itertools.pairwise(argv) if a == "--add-dir"][-1]
    held = Fence(online=False)
    agent.reconfigure(dataclasses.replace(agent.config, fence=held))
    fenced = agent.fenced()
    assert fenced is not None
    assert fenced.allows(plugin)
    assert not fenced.allows(plugin, write=True)
    unplugged = _agent(fence=held).fenced()
    assert unplugged is not None
    assert not unplugged.allows(plugin)  # nothing of the temporary directory otherwise
    session.close()


@pytest.mark.parametrize("said", [{}, {"fence": _held(writes=True)}])
def test_an_agent_on_the_web_that_writes_or_is_unfenced_is_held_to_no_agent(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, said: dict[str, Any]
) -> None:
    spawned = spawning(monkeypatch, answers=_answering(*_SAID))
    agent = _agent(web_search=True, **said)
    heard(agent)

    _turn(agent.new(tmp_path))

    argv = spawned[0].args
    assert "--agent" not in argv
    assert "--mode" not in argv
    assert ("--dangerously-skip-permissions" in argv) == bool(said)


def test_a_slash_command_is_a_print_of_its_own(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    spawned = spawning(monkeypatch, opening=_SAID)
    agent = _agent()
    heard(agent)

    events = _turn(agent.new(tmp_path), "/review:quick now")

    (process,) = spawned
    assert process.args[-2:] == ["--print", "/review:quick now"]
    assert "--input-format" not in process.args
    assert events[-1].text == "done"


@pytest.mark.parametrize(
    ("told", "why"),
    [
        ({"status": "FAILED"}, "FAILED"),
        (
            {"status": "FAILED", "error": "the model is not here"},
            "the model is not here",
        ),
    ],
)
def test_a_result_that_did_not_succeed_fails_the_turn(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, told: dict[str, str], why: str
) -> None:
    spawning(monkeypatch, answers=_answering(_result(None, **told)))
    agent = _agent()
    heard(agent)

    with pytest.raises(Failed) as failed:
        _turn(agent.new(tmp_path))

    assert failed.value.stderr == why


# --------------------------------------------------------------- through a LiteLLM gateway


class _Gateway:
    """A gateway that starts nothing: where it would be, and the key it takes."""

    def __init__(self, provider: Provider) -> None:
        self.account = provider
        self.port = 4321
        self.url = "http://127.0.0.1:4321"
        self.key = "sk-master"
        self.running = True

    def stop(self) -> None:
        self.running = False


_ROUTED = Provider(
    cli="agy",
    name="gw",
    way="litellm-openai-key",
    env={"OPENAI_API_KEY": "upstream-secret"},
)


@pytest.fixture
def routed(monkeypatch: pytest.MonkeyPatch) -> None:
    """An account litellm holds, and a gateway that is only pretended."""

    def find(cli: str, name: str) -> Provider | None:
        return _ROUTED if name == "gw" else Provider(cli, name, way="")

    monkeypatch.setattr(providers, "find", find)
    monkeypatch.setattr(gateway, "Gateway", _Gateway)


@pytest.mark.usefixtures("routed")
def test_a_turn_through_a_gateway_is_its_openai_gateway_serving_the_model_named(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    spawned = spawning(monkeypatch, answers=_answering(*_SAID))
    agent = _agent(provider="gw", model="openai/gpt-5", effort="high")
    heard(agent)

    _turn(agent.new(tmp_path))

    (process,) = spawned
    env = process.env
    assert env is not None
    # Bare: agy adds `/v1/chat/completions` itself.
    assert env["AGY_LLM_GATEWAY_URL"] == "http://127.0.0.1:4321"
    assert env["AGY_LLM_GATEWAY_API_KEY"] == "sk-master"
    assert env["AGY_LLM_GATEWAY_WIRE_PROTOCOL"] == "openai"
    assert env["AGY_LLM_GATEWAY_MODELS"] == "openai/gpt-5"
    assert "upstream-secret" not in env.values()
    assert option(process.args, "--model") == "openai/gpt-5"
    assert "--effort" not in process.args


@pytest.mark.usefixtures("routed")
def test_a_turn_not_through_a_gateway_is_told_no_model_it_serves(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    spawned = spawning(monkeypatch, answers=_answering(*_SAID))
    agent = _agent(provider="mine")
    heard(agent)

    _turn(agent.new(tmp_path))

    env = spawned[0].env or {}
    assert "AGY_LLM_GATEWAY_MODELS" not in env


# --------------------------------------------------------------- an organization's admin settings


def _administered(where: Path, **said: Any) -> None:
    where.write_text(json.dumps(said), encoding="utf-8")


def _withheld() -> bool:
    """Whether this machine withholds the user namespaces agy's terminal sandbox starts in."""
    if sys.platform != "linux":
        return False
    for knob, forbids in (
        ("kernel/apparmor_restrict_unprivileged_userns", "1"),
        ("kernel/unprivileged_userns_clone", "0"),
        ("user/max_user_namespaces", "0"),
    ):
        try:
            if pathlib.Path("/proc/sys", knob).read_text().strip() == forbids:
                return True
        except OSError:
            continue
    return False


@pytest.mark.parametrize(
    "policy",
    ["require_review", "TERMINAL_COMMAND_AUTO_EXECUTION_POLICY_REQUIRE_REVIEW"],
)
def test_settings_holding_every_command_for_review_refuse_a_fenced_agent_at_once(
    admin: Path, policy: str
) -> None:
    _administered(admin, adminControls={"terminalCommandAutoExecutionPolicy": policy})

    with pytest.raises(Unserved, match="REQUIRE_REVIEW") as refused:
        _agent(fence=_held(writes=True))

    assert str(admin) in str(refused.value)
    assert _agent().config.fence is None  # one nobody fenced runs at agy's own defaults


@pytest.mark.parametrize(
    ("said", "instead"),
    [
        (
            {"terminalCommandAutoExecutionPolicy": "proceed_in_sandbox"},
            "terminal sandbox",
        ),
        ({"outsideWorkspaceFileAccessPolicy": "deny"}, "outside its workspace"),
        ({"outsideWorkspaceFileAccessPolicy": "ALWAYS_ASK"}, "outside its workspace"),
    ],
)
def test_settings_holding_less_are_run_under_and_said_once(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    admin: Path,
    said: dict[str, str],
    instead: str,
) -> None:
    _administered(admin, adminControls=said)
    spawned = spawning(monkeypatch, answers=_answering(*_SAID))
    if instead == "terminal sandbox" and _withheld():
        # Where agy's own sandbox cannot start, every command would be held: refused instead.
        with pytest.raises(Unserved, match="user namespaces"):
            _agent(fence=_held(writes=True))
        return
    agent = _agent(fence=_held(writes=True))
    told = heard(agent)
    session = agent.new(tmp_path)

    _turn(session)
    _turn(session)

    notices = [one.text for one in told if one.kind == "notice"]
    assert len(notices) == 1
    assert instead in notices[0]
    assert str(admin) in notices[0]
    assert "--dangerously-skip-permissions" in spawned[0].args
    session.close()


@pytest.mark.parametrize(
    ("said", "named"),
    [
        ({"pluginControls": {"pluginsDisabled": True}}, "pluginsDisabled"),
        ({"mcpControls": {"mcpEnabled": False}}, "mcpEnabled"),
    ],
)
def test_settings_turning_plugins_off_refuse_the_flow_s_tools_where_offered(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    admin: Path,
    said: dict[str, Any],
    named: str,
) -> None:
    _administered(admin, **said)
    spawned = spawning(monkeypatch, answers=_answering(*_SAID))
    agent = _agent()
    heard(agent)
    session = agent.new(tmp_path)

    with pytest.raises(Unserved, match=named):
        session.offers([FakeTool("secret", "Says the secret word.", lambda: "")])

    session.offers(None)  # taking back nothing is no tool to refuse
    _turn(session)
    assert len(spawned) == 1
    session.close()


def test_what_agy_still_refuses_a_fenced_turn_is_said(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    denied = [{"tool_name": "run_command", "reason": "held for review"}]
    spawning(monkeypatch, answers=_answering(_result(_USAGE, denied_actions=denied)))
    agent = _agent(fence=_held(writes=True))
    told = heard(agent)

    _turn(agent.new(tmp_path))

    notices = [one.text for one in told if one.kind == "notice"]
    assert len(notices) == 1
    assert "run_command (held for review)" in notices[0]
    assert "admin controls" in notices[0]


def test_settings_that_are_no_json_hold_it_to_nothing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, admin: Path
) -> None:
    admin.write_text("{not json", encoding="utf-8")
    spawning(monkeypatch, answers=_answering(*_SAID))
    agent = _agent(fence=_held(writes=True))
    told = heard(agent)

    _turn(agent.new(tmp_path))

    assert not [one for one in told if one.kind == "notice"]


def test_settings_changed_while_running_are_read_again(admin: Path) -> None:
    _administered(admin, adminControls={})
    _agent(fence=_held(writes=True))

    _administered(
        admin, adminControls={"terminalCommandAutoExecutionPolicy": "REQUIRE_REVIEW"}
    )
    os.utime(admin, ns=(1, 1))

    with pytest.raises(Unserved, match="REQUIRE_REVIEW"):
        _agent(fence=_held(writes=True))
