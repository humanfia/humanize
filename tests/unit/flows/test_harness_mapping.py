"""What the harness drivers decide before any CLI is started.

Which rung a permission comes to on each harness, what a hook's answer tells coganchor, which
error a failed turn is, what an answer is read as, and that every harness's driver serves
exactly the capabilities its protocol declares -- each of them read off the tables in
:mod:`hmz.runtime.flowing.harnessing` and the driver built by `open_agent`, with nothing spawned.
"""

from __future__ import annotations

import subprocess
from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING, Any

import pydantic
import pytest

from hmz.coganchor import backends
from hmz.coganchor.agents import (
    AgentBase,
    CodexAgent,
    CodexAgentConfig,
    Failed,
    Moment,
    Occasion,
    Stopped,
    Unrecoverable,
    Verdict,
    driver,
)
from hmz.coganchor.agents.claude import _project
from hmz.coganchor.agents.codex import strict
from hmz.coganchor.anchor import NotInstalled
from hmz.flows import (
    AskUserHookAgentMixin,
    AskUserHookResult,
    EnvBackendKind,
    GoalCommandAgentMixin,
    HarnessContended,
    HarnessDropped,
    HarnessKilled,
    HarnessKind,
    HarnessMissing,
    HarnessNotInstalled,
    HarnessRefused,
    HarnessSandboxed,
    HarnessThrottled,
    HarnessUnrecoverable,
    HookKind,
    ModelUnavailable,
    OutputSchemaError,
    OutworlderAway,
    Permission,
    PermissionKind,
    PermissionRequestHookAgentMixin,
    PermissionRequestHookResult,
    PreToolUseHookResult,
    SessionError,
    SteeringAgentMixin,
    StopHookResult,
    SubagentStartHookAgentMixin,
    SubagentStopHookAgentMixin,
    UnsupportedOperation,
)
from hmz.runtime.flowing import harnessing
from hmz.runtime.flowing.harnesses import away_answer, open_agent, settled
from hmz.runtime.flowing.specs import AgentSpec
from hmz.runtime.flowing.spi import HARNESS_CAPABILITIES, HookTable, Placement

if TYPE_CHECKING:
    from hmz.flows import HarnessError

NONE, READ, ALL = PermissionKind.NONE, PermissionKind.READ, PermissionKind.ALL

#: The permissions the table is read at: looking only, the workdir alone, the whole machine.
LOOKING = Permission(local=READ, user=READ, system=READ)
WORKDIR = Permission(local=ALL, user=READ, system=NONE)
EVERYTHING = Permission(local=ALL, user=ALL, system=ALL, online=ALL)

#: The rung each harness runs at for each of them, with no hook hung.
RUNGS: dict[HarnessKind, tuple[str, str, str]] = {
    HarnessKind.CLAUDE: ("read-only", "bypass", "bypass"),
    HarnessKind.CODEX: ("read-only", "bypass", "bypass"),
    HarnessKind.CURSOR_AGENT: ("read-only", "bypass", "bypass"),
    HarnessKind.OPENCODE: ("read-only", "bypass", "bypass"),
    HarnessKind.MIMO: ("read-only", "bypass", "bypass"),
    HarnessKind.QWEN: ("read-only", "bypass", "bypass"),
    HarnessKind.KIMI: ("read-only", "bypass", "bypass"),
    HarnessKind.GROK: ("read-only", "bypass", "bypass"),
    HarnessKind.PI: ("read-only", "bypass", "bypass"),
    HarnessKind.ZCODE: ("read-only", "bypass", "bypass"),
    HarnessKind.AGY: ("read-only", "bypass", "bypass"),
    HarnessKind.DSH: ("bypass", "bypass", "bypass"),
    HarnessKind.ACP: ("bypass", "bypass", "bypass"),
}

#: The CLI an added ACP harness is, in these tests.
ADDED = "acme"


def _spec(harness: HarnessKind, model: str = "m", effort: str = "") -> AgentSpec:
    cli = ADDED if harness is HarnessKind.ACP else harness.value
    return AgentSpec("coder", harness, "", model, effort, cli)


@pytest.fixture(autouse=True)
def _acp_added() -> None:
    """Adds a CLI spoken to over ACP, under the suite's own home."""
    backends.remember(ADDED, [ADDED, "--acp"])


def _kind(harness: HarnessKind) -> type[AgentBase]:
    return driver(ADDED if harness is HarnessKind.ACP else harness.value)[0]


# --------------------------------------------------------------------------------- rungs


@pytest.mark.parametrize("harness", sorted(RUNGS), ids=str)
def test_each_permission_comes_to_the_rung_the_table_says(harness: HarnessKind) -> None:
    rungs = _kind(harness).rungs
    said = tuple(
        harnessing.rung(harness, permission, rungs=rungs)
        for permission in (LOOKING, WORKDIR, EVERYTHING)
    )
    assert said == RUNGS[harness]


@pytest.mark.parametrize("harness", sorted(RUNGS), ids=str)
def test_no_rung_is_ever_a_model_reviewing_itself(harness: HarnessKind) -> None:
    rungs = _kind(harness).rungs
    for permission in (LOOKING, WORKDIR, EVERYTHING):
        for hung in (frozenset[HookKind](), frozenset(HookKind)):
            said = harnessing.rung(harness, permission, rungs=rungs, hung=hung)
            if said == harnessing.ASKING:
                assert harness in harnessing.ASKS, (harness, permission, hung)
            assert said in rungs


@pytest.mark.parametrize("harness", sorted(RUNGS), ids=str)
def test_a_session_that_may_write_its_workdir_is_fenced_nowhere(
    harness: HarnessKind,
) -> None:
    # Pinned on purpose: `user` and `system` are not held below ALL once `local` is, since
    # the only fences there are -- Codex's and cursor-agent's sandboxes -- cannot start where
    # there is no user namespace, and the flow API calls Codex's BYPASS full access.
    assert frozenset() == harnessing.FENCED
    rungs = _kind(harness).rungs
    for user in (NONE, READ, ALL):
        narrow = Permission(local=ALL, user=user, system=NONE)
        assert harnessing.rung(harness, narrow, rungs=rungs) == "bypass"


@pytest.mark.parametrize(
    ("harness", "hook", "rung"),
    [
        (HarnessKind.CODEX, HookKind.PERMISSION_REQUEST, "bypass"),
        (HarnessKind.CODEX, HookKind.ASK_USER, "bypass"),
        (HarnessKind.KIMI, HookKind.PERMISSION_REQUEST, "auto"),
        (HarnessKind.KIMI, HookKind.ASK_USER, "auto"),
        (HarnessKind.ZCODE, HookKind.PERMISSION_REQUEST, "auto"),
        (HarnessKind.ZCODE, HookKind.ASK_USER, "auto"),
        (HarnessKind.CLAUDE, HookKind.PERMISSION_REQUEST, "bypass"),
        (HarnessKind.GROK, HookKind.PERMISSION_REQUEST, "bypass"),
        (HarnessKind.KIMI, HookKind.PRE_TOOL_USE, "bypass"),
    ],
)
def test_a_harness_asks_only_while_a_hook_is_hung_on_what_it_asks(
    harness: HarnessKind, hook: HookKind, rung: str
) -> None:
    rungs = _kind(harness).rungs
    assert harnessing.rung(
        harness, EVERYTHING, rungs=rungs, hung=frozenset({hook})
    ) == (rung)
    assert (
        harnessing.rung(harness, LOOKING, rungs=rungs, hung=frozenset({hook}))
        == (RUNGS[harness][0])
    )


def test_codex_asks_every_command_while_a_permission_hook_is_hung() -> None:
    asking = frozenset({HookKind.PERMISSION_REQUEST})
    assert harnessing.approvals(HarnessKind.CODEX, asking) == "untrusted"
    assert harnessing.approvals(HarnessKind.CODEX, frozenset()) == ""
    assert harnessing.approvals(HarnessKind.CLAUDE, asking) == ""


def test_the_web_is_said_where_the_cli_can_be_told_and_left_where_it_cannot() -> None:
    assert harnessing.searching(EVERYTHING, tellable=True) is True
    assert harnessing.searching(WORKDIR, tellable=True) is False
    assert harnessing.searching(WORKDIR, tellable=False) is None


def test_a_session_config_carries_the_rung_the_web_and_codex_asking() -> None:
    config = CodexAgentConfig(model="m", effort="low", features=(("undo", True),))
    plain = settled(
        config, HarnessKind.CODEX, CodexAgent, WORKDIR, frozenset(), tellable=True
    )
    assert (plain.permission, plain.web_search) == ("bypass", False)
    assert isinstance(plain, CodexAgentConfig)
    assert plain.features == (("undo", True),)
    assert plain.approvals == ""
    asking = settled(
        config,
        HarnessKind.CODEX,
        CodexAgent,
        EVERYTHING,
        frozenset({HookKind.ASK_USER, HookKind.PERMISSION_REQUEST}),
        tellable=True,
    )
    assert (asking.permission, asking.web_search) == ("bypass", True)
    assert isinstance(asking, CodexAgentConfig)
    assert asking.approvals == "untrusted"
    assert asking.features == (
        ("undo", True),
        ("default_mode_request_user_input", True),
    )


# ---------------------------------------------------------------------------- capabilities


@pytest.mark.parametrize("harness", sorted(HarnessKind), ids=str)
def test_every_driver_serves_exactly_its_harness_capabilities(
    harness: HarnessKind,
) -> None:
    made = open_agent(_spec(harness))
    assert made.harness is harness
    assert made.capabilities == HARNESS_CAPABILITIES[harness]
    assert (made.model, made.effort, made.provider) == ("m", "", "")


@pytest.mark.parametrize("harness", sorted(HarnessKind), ids=str)
def test_each_capability_is_one_the_coganchor_driver_has(harness: HarnessKind) -> None:
    kind = _kind(harness)
    capabilities = HARNESS_CAPABILITIES[harness]
    moments = kind.moments
    assert (GoalCommandAgentMixin in capabilities) == kind.pursues
    assert (PermissionRequestHookAgentMixin in capabilities) <= (
        Moment.PERMISSION_REQUEST in moments
    )
    assert (SubagentStartHookAgentMixin in capabilities) == (
        Moment.SUBAGENT_START in moments
    )
    assert (SubagentStopHookAgentMixin in capabilities) == (
        Moment.SUBAGENT_STOP in moments
    )


@pytest.mark.parametrize(
    ("harness", "steers", "asks"),
    [
        (HarnessKind.CLAUDE, True, True),
        (HarnessKind.CODEX, True, True),
        (HarnessKind.KIMI, True, True),
        (HarnessKind.PI, True, True),
        (HarnessKind.ZCODE, False, True),
        (HarnessKind.GROK, False, False),
        (HarnessKind.QWEN, False, False),
        (HarnessKind.CURSOR_AGENT, False, False),
    ],
)
def test_steering_and_asking_are_where_the_coganchor_driver_has_them(
    harness: HarnessKind, steers: bool, asks: bool
) -> None:
    capabilities = HARNESS_CAPABILITIES[harness]
    assert (SteeringAgentMixin in capabilities) == steers
    assert (AskUserHookAgentMixin in capabilities) == asks
    agent = open_agent(_spec(harness))
    kind = _kind(harness)
    session = kind(agent._config).new()
    assert type(session).steers == steers


def test_an_effort_the_cli_has_no_word_for_is_refused_where_the_agent_is_named() -> (
    None
):
    with pytest.raises(HarnessUnrecoverable):
        open_agent(_spec(HarnessKind.CLAUDE, effort="ludicrous"))


def test_a_cli_nobody_added_is_not_installed() -> None:
    spec = AgentSpec("coder", HarnessKind.ACP, "", "m", "", "nobody-added-this")
    with pytest.raises(HarnessNotInstalled):
        open_agent(spec)


async def test_a_session_cannot_be_opened_in_a_workdir_that_is_not_there(
    tmp_path: Path,
) -> None:
    made = open_agent(_spec(HarnessKind.CLAUDE))
    made._installed = True
    with pytest.raises(SessionError):
        await made.open(
            Placement(EnvBackendKind.LOCAL, "", PurePosixPath(str(tmp_path / "gone"))),
            permission=Permission(),
            skills=(),
            hooks=HookTable(),
        )


async def test_a_session_opens_without_starting_its_cli(tmp_path: Path) -> None:
    made = open_agent(_spec(HarnessKind.CURSOR_AGENT))
    made._installed = True
    placement = Placement(EnvBackendKind.LOCAL, "", PurePosixPath(str(tmp_path)))
    handle = await made.open(
        placement, permission=WORKDIR, skills=(), hooks=HookTable()
    )
    assert handle.id is None
    assert handle.usage.output_tokens == 0
    assert handle.agent.config.permission == "bypass"
    with pytest.raises(UnsupportedOperation):
        await handle.steer("anything", queued=True)
    handle.interrupt()
    with pytest.raises(SessionError):
        await made.open(
            placement, permission=WORKDIR, skills=(), hooks=HookTable(), fork_of=handle
        )
    await made.close()
    assert handle.closed
    with pytest.raises(SessionError):
        await made.open(placement, permission=WORKDIR, skills=(), hooks=HookTable())


# ---------------------------------------------------------------------------------- hooks


def _occasion(moment: Moment, **said: Any) -> Occasion:
    return Occasion(moment=moment, agent="coder", **said)


def test_a_tool_is_told_with_what_it_was_called_with_or_the_line_it_was_shown_as() -> (
    None
):
    called = _occasion(Moment.PRE_TOOL_USE, tool="Bash", input={"command": "ls"})
    shown = _occasion(Moment.PRE_TOOL_USE, tool="Bash", about="git push --force")
    assert harnessing.fields(HookKind.PRE_TOOL_USE, called) == {
        "tool": "Bash",
        "input": {"command": "ls"},
    }
    assert harnessing.fields(HookKind.PRE_TOOL_USE, shown) == {
        "tool": "Bash",
        "input": {"about": "git push --force"},
    }
    assert harnessing.fields(
        HookKind.NOTIFICATION, _occasion(Moment.NOTIFICATION, said="Which way?")
    ) == {"message": "Which way?"}
    assert harnessing.fields(
        HookKind.SUBAGENT_START,
        _occasion(Moment.SUBAGENT_START, tool="Task", about="look around"),
    ) == {"subagent": "Task", "task": "look around"}


def test_a_refusing_hook_is_a_refusing_verdict_and_nothing_else_is() -> None:
    assert harnessing.verdict(
        HookKind.PRE_TOOL_USE, PreToolUseHookResult(block=True, reason="no")
    ) == Verdict(refused=True, because="no")
    assert harnessing.verdict(HookKind.PRE_TOOL_USE, PreToolUseHookResult()) is None
    assert harnessing.verdict(
        HookKind.PERMISSION_REQUEST, PermissionRequestHookResult(allow=False)
    ) == Verdict(refused=True, because="refused by a hook")
    assert (
        harnessing.verdict(HookKind.PERMISSION_REQUEST, PermissionRequestHookResult())
        is None
    )
    assert harnessing.verdict(HookKind.STOP, StopHookResult(block=True)) is None
    assert harnessing.answer(AskUserHookResult(answer="left")) == "left"
    assert harnessing.answer(StopHookResult()) is None


# --------------------------------------------------------------------------------- errors


def _failed(fault: str = "", status: int = 1) -> Failed:
    return Failed(status, ["cli"], "", "it went wrong", fault=fault)


@pytest.mark.parametrize(
    ("error", "leaf"),
    [
        (_failed("contended"), HarnessContended),
        (_failed("throttled"), HarnessThrottled),
        (_failed("refused"), HarnessRefused),
        (_failed("unlisted"), ModelUnavailable),
        (_failed("retired"), ModelUnavailable),
        (_failed("missing"), HarnessMissing),
        (_failed("missing", 127), HarnessNotInstalled),
        (_failed("sandboxed"), HarnessSandboxed),
        (_failed("killed"), HarnessKilled),
        (_failed("dropped"), HarnessDropped),
        (_failed(), HarnessUnrecoverable),
        (Unrecoverable(1, ["cli"], "", "too long"), HarnessUnrecoverable),
        (NotInstalled("claude is not on the target"), HarnessNotInstalled),
        (Stopped("coder was stopped"), SessionError),
        (ConnectionResetError("reset"), HarnessDropped),
        (RuntimeError("forked from somewhere else"), SessionError),
        (ValueError("no such provider"), HarnessUnrecoverable),
        (
            subprocess.CalledProcessError(1, ["cli"], "", "429 Too Many Requests"),
            HarnessThrottled,
        ),
    ],
    ids=lambda one: type(one).__name__ if isinstance(one, type) else repr(one)[:40],
)
def test_a_failed_turn_is_the_leaf_for_why(
    error: BaseException, leaf: type[HarnessError]
) -> None:
    said = harnessing.harness_error(error, "claude")
    assert type(said) is leaf
    assert str(said)


def test_a_bug_is_not_a_failed_turn() -> None:
    assert harnessing.harness_error(KeyError("oops"), "claude") is None


# -------------------------------------------------------------------------------- answers


class Verdicted(pydantic.BaseModel):
    """A shape an answer is read as."""

    done: bool
    why: str = ""


@pytest.mark.parametrize(
    "said",
    [
        '{"done": true}',
        'Here it is:\n```json\n{"done": true}\n```',
        'Sure. {"done": true} -- hope that helps',
    ],
)
def test_an_answer_is_read_as_its_shape_wherever_in_it_the_object_is(said: str) -> None:
    assert harnessing.read_shape(said, Verdicted) == Verdicted(done=True)


def test_an_answer_that_is_not_its_shape_is_an_output_schema_error() -> None:
    with pytest.raises(OutputSchemaError) as raised:
        harnessing.read_shape('{"finished": true}', Verdicted)
    assert isinstance(raised.value, ValueError)
    assert isinstance(raised.value.__cause__, pydantic.ValidationError)


def test_an_away_outworlder_answers_what_nothing_has_to_be_asked_for() -> None:
    class Loose(pydantic.BaseModel):
        far: int = 2

    assert away_answer(None) == ""
    assert away_answer(Loose) == Loose()
    with pytest.raises(OutworlderAway):
        away_answer(Verdicted)


# -------------------------------------------------------------------- coganchor's own parts


def test_claude_names_a_project_directory_as_claude_code_does() -> None:
    long = "/tmp/" + "a-very-long-directory-name/" * 9 + "ü\U0001f600end"
    assert _project("/home/me/my repo") == "-home-me-my-repo"
    assert _project("/tmp/x/ü\U0001f600end") == "-tmp-x----end"
    # What Claude Code 2.1.282's own function answers for the same path.
    assert _project(long) == (
        "-tmp" + "-a-very-long-directory-name" * 7 + "-a-very-qz2e4t"
    )


def test_codex_is_held_to_a_schema_its_models_will_take() -> None:
    class Inner(pydantic.BaseModel):
        default: int = 1

    class Outer(pydantic.BaseModel):
        inner: Inner
        tags: list[str] = pydantic.Field(default_factory=list[str])

    held = strict(Outer.model_json_schema())
    assert held["required"] == ["inner", "tags"]
    assert held["additionalProperties"] is False
    inner = held["$defs"]["Inner"]
    assert inner["required"] == ["default"]
    assert "default" in inner["properties"]
    assert "default" not in inner["properties"]["default"]


def test_codex_takes_only_an_approval_policy_it_has() -> None:
    assert CodexAgentConfig(model="m", effort="low", approvals="untrusted").approvals
    with pytest.raises(ValueError, match="approvals"):
        CodexAgentConfig(model="m", effort="low", approvals="auto-review")


def test_a_conversation_is_forked_only_where_its_backend_can_carry_it(
    tmp_path: Path,
) -> None:
    claude, _ = driver("claude")
    opencode, _ = driver("opencode")
    held = claude(open_agent(_spec(HarnessKind.CLAUDE))._config).new(tmp_path)
    other = opencode(open_agent(_spec(HarnessKind.OPENCODE))._config)
    with pytest.raises(ValueError, match="same backend"):
        held.fork(into=other)
    with pytest.raises(RuntimeError):
        held.fork(cwd=tmp_path / "elsewhere")  # nothing has landed to carry
    stays = other.new(tmp_path)
    with pytest.raises(NotImplementedError):
        stays.fork(cwd=tmp_path / "elsewhere")


async def test_a_change_of_hooks_is_settled_until_a_turn_has_settled_it(
    tmp_path: Path,
) -> None:
    made = open_agent(_spec(HarnessKind.CODEX, model="gpt-5.5", effort="low"))
    made._installed = True
    hooks = HookTable()
    handle = await made.open(
        Placement(EnvBackendKind.LOCAL, "", PurePosixPath(str(tmp_path))),
        permission=EVERYTHING,
        skills=(),
        hooks=hooks,
    )

    async def refuses(one: Any, fields: dict[str, Any]) -> Any:
        del one, fields
        return PermissionRequestHookResult(allow=False)

    hooks.set(HookKind.PERMISSION_REQUEST, refuses)
    assert handle._settling() is not None
    # A turn that never got as far as settling leaves the next one to settle it.
    settle = handle._settling()
    assert settle is not None
    settle()
    config = handle.agent.config
    assert isinstance(config, CodexAgentConfig)
    assert config.approvals == "untrusted"
    assert handle._settling() is None
    await made.close()


async def test_a_tool_asked_about_while_the_turn_is_cut_off_is_refused(
    tmp_path: Path,
) -> None:
    made = open_agent(_spec(HarnessKind.CLAUDE))
    made._installed = True
    hooks = HookTable()

    async def allows(one: Any, fields: dict[str, Any]) -> Any:
        del one, fields
        return PermissionRequestHookResult()

    hooks.set(HookKind.PERMISSION_REQUEST, allows)
    handle = await made.open(
        Placement(EnvBackendKind.LOCAL, "", PurePosixPath(str(tmp_path))),
        permission=EVERYTHING,
        skills=(),
        hooks=hooks,
    )
    asked = _occasion(Moment.PERMISSION_REQUEST, tool="Bash")
    handle._flying = True
    handle._interrupted = True
    said = handle._moment(asked)
    assert said is not None
    assert said.refused
    await made.close()
