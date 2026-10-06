"""The agent drivers, over a coganchor agent stood in for: no CLI is started."""

from __future__ import annotations

import asyncio
import dataclasses
import time
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING, Any

import pydantic
import pytest

from hmz.coganchor import agents as coganchor_agents
from hmz.coganchor import backends
from hmz.coganchor.agents import Question
from hmz.coganchor.agents import base as coganchor_base
from hmz.flows import (
    AskUserHookAgentMixin,
    CostExceeded,
    DurationExceeded,
    EnvBackendKind,
    HarnessDropped,
    HarnessKind,
    HarnessNotInstalled,
    HarnessUnrecoverable,
    HookKind,
    OutputTokensExceeded,
    OutworlderAway,
    Permission,
    PermissionKind,
    SessionError,
    SessionStartHookResult,
    StopHookResult,
    UnsupportedOperation,
    UserPromptSubmitHookResult,
)
from hmz.runtime.flowing import harnessing
from hmz.runtime.flowing.harnesses import (
    HarnessDriver,
    HarnessSession,
    away_answer,
    open_agent,
    open_outworlder,
    settled,
)
from hmz.runtime.flowing.specs import AgentSpec
from hmz.runtime.flowing.spi import (
    HARNESS_CAPABILITIES,
    HookTable,
    Limits,
    Placement,
    SessionHandle,
    Skill,
    TurnRequest,
)
from tests.unit.runtime.flowing.doubles_u11 import returning

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator

# ------------------------------------------------------------------------- coganchor, stood in


@dataclass(frozen=True)
class Config:
    """What a coganchor agent is configured with, as far as the driver sets it."""

    model: str = ""
    effort: str = ""
    provider: str = ""
    permission: str = ""
    web_search: bool | None = None
    machine: Any = None
    fence: Any = None


@dataclass
class Said:
    """One event a CLI says as a turn goes."""

    kind: str
    text: str = ""
    spent: dict[str, float] = field(default_factory=dict[str, float])


class Conversation:
    """coganchor's conversation with a CLI, answering from a function of the prompt."""

    forks_elsewhere = True

    def __init__(self, agent: CLI, cwd: str | None) -> None:
        self.agent = agent
        self.cwd = cwd
        self.named: str | None = None
        self.prompts: list[str] = []
        self.pursued: list[str] = []
        self.closed = 0
        self.cuts: list[str] = []

    def stream(self, body: str, *, schema: Any = None) -> Iterator[Said]:
        self.prompts.append(body)
        self.named = "conversation-1"
        said = self.agent.reply(body)
        yield Said("text", "thinking")
        yield Said("result", f"  {said}  ")

    def pursue(self, body: str) -> str:
        self.pursued.append(body)
        self.named = "conversation-1"
        return "pursued"

    def spent(self) -> dict[str, float]:
        return {}

    def cut(self, *, why: str) -> None:
        self.cuts.append(why)

    def interject(self, prompt: str) -> None:
        raise RuntimeError("no turn")

    def close(self) -> None:
        self.closed += 1

    def fork(self, *, into: CLI, cwd: str | None) -> Conversation:
        forked = Conversation(into, cwd)
        forked.named = "conversation-2"
        return forked


class Hooks:
    """The moments a CLI fires itself; this one fires none."""

    moments: tuple[Any, ...] = ()

    def on(self, moment: Any, fn: Any) -> Any:
        raise AssertionError("nothing is hung on a CLI that fires nothing")


def _echo(prompt: str) -> str:
    return f"re: {prompt}"


class CLI:
    """coganchor's agent for one CLI."""

    rungs = ("read-only", "workspace-write", "auto", "bypass")
    built: list[CLI] = []  # noqa: RUF012 -- emptied per test
    reply: Callable[[str], str] = staticmethod(_echo)

    def __init__(self, config: Config) -> None:
        if config.model == "refused":
            raise ValueError("no such model")
        self.config = config
        self.backend = "claude"
        self.id = "coder"
        self.hooks = Hooks()
        self.ask: Any = None
        self.loaded: list[Any] = []
        self.watched: list[Any] = []
        self.conversations: list[Conversation] = []
        self.stopped = 0
        CLI.built.append(self)

    def loads(self, skills: Any) -> None:
        self.loaded.extend(skills)

    def watch(self, listener: Any) -> None:
        self.watched.append(listener)

    def new(self, cwd: str | None) -> Conversation:
        conversation = Conversation(self, cwd)
        self.conversations.append(conversation)
        return conversation

    def reconfigure(self, config: Config) -> None:
        self.config = config

    def stop(self) -> None:
        self.stopped += 1


@dataclass
class Profile:
    name: str = "claude"
    searches: bool = True
    forks: bool = True


def _cli(session: HarnessSession) -> CLI:
    """The coganchor agent a session runs, which here is always a :class:`CLI`."""
    agent: Any = session.agent
    assert isinstance(agent, CLI)
    return agent


def _config(config: Config) -> Any:
    """A config, as the driver's signature takes one."""
    return config


@pytest.fixture
def coganchor(monkeypatch: pytest.MonkeyPatch) -> type[CLI]:
    """Every CLI is :class:`CLI`, installed, and fenced by nothing."""
    CLI.built = []
    CLI.reply = staticmethod(_echo)

    def make(**said: Any) -> Config:
        return Config(**said)

    def driver(cli: str) -> tuple[type[CLI], Callable[..., Config]]:
        if cli == "nobody":
            raise KeyError(cli)
        return CLI, make

    monkeypatch.setattr(coganchor_agents, "driver", driver)

    def named(cli: str) -> Profile:
        return Profile(name=cli)

    def program(command: str) -> str:
        return f"/usr/bin/{command}"

    def installing(cli: str) -> str:
        return f"install {cli}"

    monkeypatch.setattr(coganchor_base, "identifying", returning({}))
    monkeypatch.setattr(backends, "named", named)
    monkeypatch.setattr(backends, "program", program)
    monkeypatch.setattr(backends, "speaking", dict)
    monkeypatch.setattr(backends, "installing", installing)
    monkeypatch.setattr(harnessing, "fenced", returning(None))
    return CLI


def _spec(harness: HarnessKind = HarnessKind.CLAUDE, model: str = "opus") -> AgentSpec:
    return AgentSpec("coder", harness, "", model, "high", str(harness))


def _placed(workdir: Path) -> Placement:
    return Placement(EnvBackendKind.LOCAL, "", PurePosixPath(workdir))


class Sink:
    def __init__(self) -> None:
        self.added: list[tuple[float, int, float]] = []

    def add(self, *, cost: float, output_tokens: int, duration: float) -> None:
        self.added.append((cost, output_tokens, duration))


async def _session(
    driver: HarnessDriver, workdir: Path, hooks: HookTable | None = None
) -> HarnessSession:
    return await driver.open(
        _placed(workdir), permission=Permission(), skills=(), hooks=hooks or HookTable()
    )


# ------------------------------------------------------------------------------- the driver


def test_an_agent_is_its_spec_and_serves_exactly_its_harness(
    coganchor: type[CLI],
) -> None:
    driver = open_agent(_spec(HarnessKind.CODEX))

    assert (driver.harness, driver.model, driver.effort, driver.provider) == (
        HarnessKind.CODEX,
        "opus",
        "high",
        "",
    )
    assert driver.capabilities == HARNESS_CAPABILITIES[HarnessKind.CODEX]
    assert driver.spec == _spec(HarnessKind.CODEX)
    assert driver.profile == Profile(name="codex")
    assert driver.tellable
    assert len(coganchor.built) == 1, "built once, to be refused now rather than later"


def test_a_cli_nobody_added_is_not_installed(coganchor: type[CLI]) -> None:
    with pytest.raises(HarnessNotInstalled, match="nobody"):
        open_agent(AgentSpec("coder", HarnessKind.ACP, "", "m", "", "nobody"))


def test_a_model_the_cli_cannot_run_is_unrecoverable(coganchor: type[CLI]) -> None:
    with pytest.raises(HarnessUnrecoverable, match="no such model"):
        open_agent(_spec(model="refused"))


async def test_a_session_opens_in_its_workdir_with_its_skills(
    coganchor: type[CLI], tmp_path: Path
) -> None:
    driver = open_agent(_spec())
    heard: list[Any] = []
    driver.watch(lambda agent, conversation, event: heard.append(event))

    session = await driver.open(
        _placed(tmp_path),
        permission=Permission(local=PermissionKind.READ),
        skills=(Skill("review", tmp_path / "review"),),
        hooks=HookTable(),
    )

    agent = _cli(session)
    assert agent.config.permission == harnessing.READ_ONLY
    assert agent.config.web_search is True
    assert [one.name for one in agent.loaded] == ["review"]
    assert len(agent.watched) == 2, "the run's listener, and the session's own"
    assert isinstance(session.coganchor, Conversation)
    assert session.coganchor.cwd == str(tmp_path)
    assert (session.id, session.driver, session.closed) == (None, driver, False)
    assert session.placement == _placed(tmp_path)


async def test_a_session_is_refused_where_it_cannot_open(
    coganchor: type[CLI], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    driver = open_agent(_spec())

    with pytest.raises(SessionError, match="not a directory"):
        await _session(driver, tmp_path / "gone")
    monkeypatch.setattr(backends, "program", returning(None))
    with pytest.raises(HarnessNotInstalled, match="install claude"):
        await _session(driver, tmp_path)


async def test_a_session_is_forked_only_from_one_of_its_own_that_took_a_turn(
    coganchor: type[CLI], tmp_path: Path
) -> None:
    driver = open_agent(_spec())
    other = open_agent(_spec())
    session = await _session(driver, tmp_path)
    stranger: Any = object()

    def opened(fork_of: Any) -> Any:
        return driver.open(
            _placed(tmp_path),
            permission=Permission(),
            skills=(),
            hooks=HookTable(),
            fork_of=fork_of,
        )

    with pytest.raises(SessionError, match="taken no turn"):
        await opened(session)
    with pytest.raises(SessionError, match="only by the agent"):
        await opened(stranger)
    with pytest.raises(SessionError, match="only by the agent"):
        await opened(await _session(other, tmp_path))
    await session.turn(TurnRequest("hi"), Sink())
    forked = await opened(session)

    assert forked.id == "conversation-2"


async def test_a_harness_that_cannot_fork_refuses_to(
    coganchor: type[CLI], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(backends, "named", returning(Profile(forks=False)))
    driver = open_agent(_spec())
    session = await _session(driver, tmp_path)
    await session.turn(TurnRequest("hi"), Sink())

    with pytest.raises(UnsupportedOperation, match="cannot fork"):
        driver.cut_from(session, _placed(tmp_path), doing="fork")
    await session.close()
    with pytest.raises(SessionError, match="closed"):
        driver.cut_from(session, _placed(tmp_path), doing="fork")


async def test_closing_the_driver_closes_its_sessions_and_opens_no_more(
    coganchor: type[CLI], tmp_path: Path
) -> None:
    driver = open_agent(_spec())
    session = await _session(driver, tmp_path)

    await driver.close()
    await driver.close()

    assert session.closed
    assert _cli(session).stopped == 1
    with pytest.raises(SessionError, match="closed"):
        await _session(driver, tmp_path)


# --------------------------------------------------------------------------------- a turn


async def test_a_turn_answers_what_the_cli_said_and_reports_its_time(
    coganchor: type[CLI], tmp_path: Path
) -> None:
    session = await _session(open_agent(_spec()), tmp_path)
    sink = Sink()

    said = await session.turn(TurnRequest("fix it"), sink)

    assert said == "re: fix it"
    assert session.id == "conversation-1"
    assert sink.added
    assert all(cost == 0 and tokens == 0 for cost, tokens, _ in sink.added)
    assert session.usage.cost == 0


class Fix(pydantic.BaseModel):
    done: bool


async def test_a_turn_asked_for_a_schema_answers_an_instance_of_it(
    coganchor: type[CLI], tmp_path: Path
) -> None:
    coganchor.reply = staticmethod(returning('Here: {"done": true}'))
    session = await _session(open_agent(_spec()), tmp_path)

    said = await session.turn(TurnRequest("fix it", Fix), Sink())

    assert said == Fix(done=True)


@pytest.mark.parametrize(
    ("harness", "pursued"),
    [(HarnessKind.CLAUDE, True), (HarnessKind.ACP, False)],
)
async def test_a_goal_is_the_harness_own_where_it_has_one(
    coganchor: type[CLI], tmp_path: Path, harness: HarnessKind, pursued: bool
) -> None:
    session = await _session(open_agent(_spec(harness)), tmp_path)

    said = await session.turn(TurnRequest("/goal ship it"), Sink())

    conversation = session.coganchor
    assert isinstance(conversation, Conversation)
    if pursued:
        assert (said, conversation.pursued) == ("pursued", ["ship it"])
    else:
        assert conversation.prompts == ["/goal ship it"]


async def test_the_hooks_around_a_turn_shape_what_the_cli_is_told(
    coganchor: type[CLI], tmp_path: Path
) -> None:
    hooks = HookTable()
    fired: list[HookKind] = []

    async def start(handle: SessionHandle, fields: dict[str, Any]) -> Any:
        fired.append(HookKind.SESSION_START)
        return SessionStartHookResult(context="the repo is python")

    async def submit(handle: SessionHandle, fields: dict[str, Any]) -> Any:
        fired.append(HookKind.USER_PROMPT_SUBMIT)
        return UserPromptSubmitHookResult(context="be brief")

    async def stop(handle: SessionHandle, fields: dict[str, Any]) -> Any:
        fired.append(HookKind.STOP)
        if fields["again"] == 0:
            return StopHookResult(block=True, reason="now the tests")
        return StopHookResult()

    async def end(handle: SessionHandle, fields: dict[str, Any]) -> Any:
        fired.append(HookKind.SESSION_END)
        return None

    hooks.set(HookKind.SESSION_START, start)
    hooks.set(HookKind.USER_PROMPT_SUBMIT, submit)
    hooks.set(HookKind.STOP, stop)
    hooks.set(HookKind.SESSION_END, end)
    session = await _session(open_agent(_spec()), tmp_path, hooks)

    said = await session.turn(TurnRequest("fix it"), Sink())
    await session.turn(TurnRequest("again"), Sink())
    await session.close()
    await session.close()

    conversation = session.coganchor
    assert isinstance(conversation, Conversation)
    assert conversation.prompts[:2] == [
        "the repo is python\n\nfix it\n\nbe brief",
        "now the tests",
    ]
    assert conversation.prompts[2] == "again\n\nbe brief"
    assert said == "re: now the tests"
    assert fired.count(HookKind.SESSION_START) == 1
    assert fired.count(HookKind.SESSION_END) == 1
    assert conversation.closed == 1


async def test_a_prompt_a_hook_refused_is_never_taken(
    coganchor: type[CLI], tmp_path: Path
) -> None:
    hooks = HookTable()

    async def refuse(handle: SessionHandle, fields: dict[str, Any]) -> Any:
        return UserPromptSubmitHookResult(block=True, reason="not that")

    hooks.set(HookKind.USER_PROMPT_SUBMIT, refuse)
    session = await _session(open_agent(_spec()), tmp_path, hooks)

    with pytest.raises(SessionError, match="not that"):
        await session.turn(TurnRequest("rm -rf /"), Sink())
    conversation = session.coganchor
    assert isinstance(conversation, Conversation)
    assert conversation.prompts == []


@pytest.mark.parametrize(
    ("limits", "kind"),
    [
        (Limits(cost=0.0), CostExceeded),
        (Limits(output_tokens=0), OutputTokensExceeded),
        (Limits(deadline=0.0), DurationExceeded),
    ],
)
async def test_a_turn_with_nothing_left_to_spend_is_refused(
    coganchor: type[CLI], tmp_path: Path, limits: Limits, kind: type[Exception]
) -> None:
    session = await _session(open_agent(_spec()), tmp_path)

    with pytest.raises(kind):
        await session.turn(TurnRequest("x", limits=limits), Sink())


async def test_a_turn_with_time_to_spare_is_taken(
    coganchor: type[CLI], tmp_path: Path
) -> None:
    session = await _session(open_agent(_spec()), tmp_path)
    limits = Limits(
        cost=1.0, output_tokens=10, deadline=time.monotonic() + 60, graceful=False
    )

    assert await session.turn(TurnRequest("x", limits=limits), Sink()) == "re: x"


async def test_a_cli_that_failed_is_the_harness_error_it_is_and_a_bug_stays_one(
    coganchor: type[CLI], tmp_path: Path
) -> None:
    def failing(prompt: str) -> str:
        if prompt == "bug":
            raise KeyError("bug")
        raise ConnectionResetError("the CLI went away")

    coganchor.reply = staticmethod(failing)
    session = await _session(open_agent(_spec()), tmp_path)

    with pytest.raises(HarnessDropped, match="went away"):
        await session.turn(TurnRequest("x"), Sink())
    with pytest.raises(KeyError):
        await session.turn(TurnRequest("bug"), Sink())


async def test_a_closed_session_takes_no_turn_and_steers_nothing(
    coganchor: type[CLI], tmp_path: Path
) -> None:
    session = await _session(open_agent(_spec()), tmp_path)
    await session.close()

    with pytest.raises(SessionError, match="closed"):
        await session.turn(TurnRequest("x"), Sink())
    with pytest.raises(SessionError, match="closed"):
        await session.steer("x", queued=True)
    with pytest.raises(SessionError, match="closed"):
        await session.move(_placed(tmp_path))


async def test_steering_needs_a_harness_that_steers_and_a_turn_in_flight(
    coganchor: type[CLI], tmp_path: Path
) -> None:
    acp = await _session(open_agent(_spec(HarnessKind.ACP)), tmp_path)
    claude = await _session(open_agent(_spec()), tmp_path)

    with pytest.raises(UnsupportedOperation, match="cannot be steered"):
        await acp.steer("x", queued=True)
    with pytest.raises(SessionError, match="no turn"):
        await claude.steer("x", queued=False)
    claude.interrupt()
    claude.interrupt()


async def test_a_session_moved_nowhere_stays_and_one_moved_elsewhere_starts_there(
    coganchor: type[CLI], tmp_path: Path
) -> None:
    (tmp_path / "other").mkdir()
    session = await _session(open_agent(_spec()), tmp_path)
    first = _cli(session)

    assert not await session.move(_placed(tmp_path))
    assert await session.move(_placed(tmp_path / "other"))

    assert _cli(session) is not first
    assert session.placement == _placed(tmp_path / "other")
    await session.close()
    assert first.stopped == 1


async def test_a_question_is_put_to_the_ask_user_hook(
    coganchor: type[CLI], tmp_path: Path
) -> None:
    from hmz.flows import AskUserHookResult

    hooks = HookTable()

    async def ask(handle: SessionHandle, fields: dict[str, Any]) -> Any:
        return AskUserHookResult(answer=f"yes to {fields['question']}")

    hooks.set(HookKind.ASK_USER, ask)
    session = await _session(open_agent(_spec()), tmp_path, hooks)
    asked: Callable[[Question], str | None] = _cli(session).ask

    assert AskUserHookAgentMixin in HARNESS_CAPABILITIES[HarnessKind.CLAUDE]
    said = await asyncio.to_thread(asked, Question(text="push?"))
    assert said == "yes to push?"


# -------------------------------------------------------------------------------- settled


def test_a_sessions_config_is_settled_for_its_permission_and_hooks(
    coganchor: type[CLI],
) -> None:
    config = Config(model="opus")

    said = settled(
        _config(config),
        HarnessKind.KIMI,
        CLI,  # pyright: ignore[reportArgumentType]
        Permission(
            online=PermissionKind.NONE,
            user=PermissionKind.NONE,
            system=PermissionKind.NONE,
        ),
        frozenset({HookKind.ASK_USER}),
        tellable=True,
        workdir="/w",
    )

    assert said == dataclasses.replace(
        config, permission=harnessing.ASKING, web_search=False
    )


def test_a_fence_the_cli_cannot_be_held_to_is_unrecoverable(
    coganchor: type[CLI], monkeypatch: pytest.MonkeyPatch
) -> None:
    def refuse(permission: Any, **_: Any) -> Any:
        raise ValueError("no such scope")

    monkeypatch.setattr(harnessing, "fenced", refuse)

    with pytest.raises(HarnessUnrecoverable, match="no such scope"):
        settled(
            _config(Config()),
            HarnessKind.CLAUDE,
            CLI,  # pyright: ignore[reportArgumentType]
            Permission(),
            frozenset(),
            tellable=False,
        )


# ----------------------------------------------------------------------------- outworlder


class Person:
    """coganchor's person-shaped agent, answering what it is asked."""

    def __init__(self, *, name: str) -> None:
        self.name = name
        self.ask: Callable[[Question], str | None] | None = None

    def asked(self, question: Question) -> str | None:
        return None if self.ask is None else self.ask(question)

    def new(self) -> Callable[..., Any]:
        def turn(
            prompt: str, *, suppress: bool, schema: type[pydantic.BaseModel]
        ) -> Any:
            return schema.model_validate(
                {"done": self.asked(Question(text=prompt)) == "yes"}
            )

        return turn


async def test_nobody_to_ask_is_away_and_answers_as_one(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    nobody = open_outworlder()

    assert nobody.away_for("reviewer")
    assert await nobody.run("ok?", None, "reviewer") == ""


async def test_a_person_is_asked_as_the_role_asking(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(coganchor_agents, "HumanAgent", Person)
    heard: list[Question] = []

    def ask(question: Question) -> str | None:
        heard.append(question)
        return "yes"

    person = open_outworlder(ask=ask)

    assert not person.away_for("reviewer")
    assert await person.run("ship it?", None, "reviewer") == "yes"
    assert await person.run("done?", Fix, "lead") == Fix(done=True)
    assert [(one.text, one.asker) for one in heard] == [
        ("ship it?", "reviewer"),
        ("done?", "lead"),
    ]


async def test_a_person_away_for_one_role_answers_as_away_for_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(coganchor_agents, "HumanAgent", Person)
    person = open_outworlder(
        ask=lambda question: "here", away=lambda role: role == "afk"
    )

    assert person.away_for("afk")
    assert await person.run("x", None, "afk") == ""
    assert await person.run("x", None, "desk") == "here"


async def test_a_person_who_answered_nothing_went_away(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(coganchor_agents, "HumanAgent", Person)

    with pytest.raises(OutworlderAway, match="nobody answered"):
        await open_outworlder(ask=lambda question: None).run("x", None, "r")


class Defaulted(pydantic.BaseModel):
    note: str = "none"


def test_an_away_answer_is_empty_text_or_the_schemas_defaults() -> None:
    assert away_answer(None) == ""
    assert away_answer(Defaulted) == Defaulted()
    with pytest.raises(OutworlderAway, match="no default"):
        away_answer(Fix)
