"""`hmz.coganchor.agents.base`: an agent is structure, a session the history it runs on.

Driven through `doubles_core.Scripted`, the smallest public subclass there is: what a turn goes
through on its way -- moments, budgets, watchers, meters, shapes, failures -- is the base
classes' own, whatever the backend.
"""

from __future__ import annotations

import gc
import json
import os
import stat
import time
from dataclasses import replace
from typing import TYPE_CHECKING, Any, ClassVar, NoReturn

import pytest
from pydantic import BaseModel

from hmz.coganchor.agents import AcpAgentConfig, ClaudeCodeAgentConfig
from hmz.coganchor.agents.allowance import Allowance, Ledger
from hmz.coganchor.agents.base import (
    KEEPING,
    KEPT,
    WINDOW,
    AgentBase,
    CommandSessionBase,
    Meter,
    SessionBase,
    StreamSessionBase,
    identifying,
)
from hmz.coganchor.agents.config import AgentConfig, Budget, Unserved
from hmz.coganchor.agents.event import (
    Event,
    Failed,
    Question,
    Stopped,
    Unrecoverable,
    Usage,
)
from hmz.coganchor.agents.hooks import Moment, Occasion, Verdict
from hmz.coganchor.agents.skills import Loaded
from hmz.coganchor.agents.tools import Tool
from hmz.runtime import telemetry
from tests.unit.coganchor.agents.doubles_core import (
    Scripted,
    Steered,
    Turns,
    answering,
    heard,
)

if TYPE_CHECKING:
    from collections.abc import Iterable
    from pathlib import Path


class _Verdict(BaseModel):
    done: bool
    why: str = ""


def _said(*events: Event, named: str = "") -> Any:
    """A script whose every turn says these events, naming the session once it lands."""

    def script(session: Turns, prompt: str) -> Iterable[Event]:
        del prompt
        if named:
            session.names(named)
        return events

    return script


def _failing(error: Exception) -> Any:
    def script(session: Turns, prompt: str) -> Iterable[Event]:
        del session, prompt
        raise error

    return script


def _kinds(events: list[Event]) -> list[tuple[str, str]]:
    return [(one.kind, one.text) for one in events]


# -- the meter -------------------------------------------------------------------------


def test_a_fresh_meter_has_spent_nothing() -> None:
    meter = Meter()
    assert dict(meter.spent()) == {"input": 0.0, "output": 0.0}
    assert meter.juice() == 0.0


def test_a_meter_adds_what_was_spent_and_ignores_nothing() -> None:
    meter = Meter()
    meter.spend(Usage())
    meter.spend(Usage(input=3, output=4))
    meter.spend(Usage(output=1, cache_read=2))
    assert dict(meter.spent()) == {"input": 3, "output": 5, "cache_read": 2}


def test_a_meters_rate_is_over_the_window() -> None:
    meter = Meter()
    now = time.monotonic() + 10 * WINDOW  # the run is older than any window asked about
    meter.spend(Usage(output=600), now=now - WINDOW - 1)  # outside the window
    meter.spend(Usage(input=30, output=60), now=now - 10)
    rate = meter.rate(over=60, now=now)
    assert (rate.input, rate.output) == (0.5, 1.0)
    assert meter.rate(over=0, now=now).output == 0.0


def test_a_young_meters_rate_is_over_its_whole_life() -> None:
    meter = Meter()
    began = time.monotonic()
    meter.spend(Usage(output=100), now=began)
    rate = meter.rate(over=WINDOW, now=began + 10)
    assert rate.output == pytest.approx(10, rel=0.1)


def test_juice_is_output_per_turn_of_the_model() -> None:
    meter = Meter()
    now = time.monotonic() + 10 * WINDOW
    meter.spend(Usage(output=100), now=now - 3)
    meter.spend(Usage(output=300), now=now - 2)
    meter.spend(Usage(output=200), now=now - 1, turn=False)  # a settling up
    assert meter.juice(now=now) == 300.0
    assert meter.juice(over=0.5, now=now) == 0.0


# -- a turn ----------------------------------------------------------------------------


def test_a_turn_answers_stripped_and_is_heard_whole() -> None:
    agent = Scripted(
        script=_said(
            Event(kind="text", text="looking"),
            Event(kind="tool", text="Read a.py"),
            Event(kind="result", text="  answer \n"),
            named="s-1",
        ),
        name="worker",
    )
    said = heard(agent)
    session = agent.new()
    with pytest.raises(RuntimeError, match="has not run a turn"):
        _ = session.id
    assert session.named is None
    assert session("go") == "answer"
    assert _kinds(said) == [
        ("begins", "go"),
        ("text", "looking"),
        ("tool", "Read a.py"),
        ("result", "  answer \n"),
        ("ends", ""),
    ]
    assert (session.id, session.named) == ("s-1", "s-1")
    assert agent.opened == ["s-1"]
    assert agent.id == "worker"


def test_a_watcher_is_told_which_session_said_it() -> None:
    agent = Scripted()
    told: list[tuple[AgentBase, SessionBase | None]] = []
    agent.watch(lambda who, where, _: told.append((who, where)))
    assert agent.watched
    session = agent.new()
    session("go")
    assert {where for _, where in told} == {session}
    assert {who for who, _ in told} == {agent}


def test_a_watcher_that_raises_is_reported_once_per_kind(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    snags: list[tuple[str, dict[str, Any]]] = []

    def snag(what: str, **why: Any) -> None:
        snags.append((what, why))

    monkeypatch.setattr(telemetry, "snag", snag)
    agent = Scripted()

    def broken(*_: object) -> NoReturn:
        raise KeyError("x")

    agent.watch(broken)
    assert agent("one") == "done"
    assert agent("two") == "done"
    assert [why["kind"] for _, why in snags] == ["begins", "result", "ends"]
    assert {what for what, _ in snags} == {"watcher-raised"}
    assert snags[0][1]["why"] == "KeyError"


def test_a_stream_yields_what_the_agent_said_ending_on_the_result() -> None:
    agent = Scripted(script=_said(Event("text", "a"), Event("result", "b")))
    assert _kinds(list(agent.new().stream("x"))) == [("text", "a"), ("result", "b")]


def test_a_turn_with_no_result_answers_nothing() -> None:
    agent = Scripted(script=_said(Event("text", "talking only")))
    assert agent("x") == ""


def test_spending_lands_on_the_session_and_the_agent() -> None:
    agent = Scripted(script=_said(Event("result", "a", spent=Usage(input=2, output=8))))
    first, second = agent.new(), agent.new()
    first("x")
    first("y")
    second("z")
    assert dict(first.spent()) == {"input": 4, "output": 16}
    assert dict(agent.spent()) == {"input": 6, "output": 24}
    assert first.juice() == 8.0
    assert agent.juice() == 8.0
    assert first.rate().output > 0
    assert agent.rate().output > 0


def test_words_waiting_for_the_agent_go_with_the_next_prompt() -> None:
    agent = Scripted()
    agent.waiting = lambda: ["also this", "and this"]
    session = agent.new()
    session("task")
    assert session.told == ["task\n\nalso this\n\nand this"]


# -- moments ---------------------------------------------------------------------------


def test_the_moments_of_a_conversation() -> None:
    agent = Scripted(
        script=_said(Event("tool", "Bash ls -la"), Event("result", "done"), named="s")
    )
    fired: list[Occasion] = []
    for moment in (
        Moment.SESSION_START,
        Moment.USER_PROMPT_SUBMIT,
        Moment.PRE_TOOL_USE,
        Moment.STOP,
        Moment.SESSION_END,
    ):
        agent.hooks.on(moment, fired.append)
    session = agent.new()
    session("one")
    session("two")
    session.close()
    session.close()
    assert [one.moment for one in fired] == [
        Moment.SESSION_START,
        Moment.USER_PROMPT_SUBMIT,
        Moment.PRE_TOOL_USE,
        Moment.STOP,
        Moment.USER_PROMPT_SUBMIT,
        Moment.PRE_TOOL_USE,
        Moment.STOP,
        Moment.SESSION_END,
    ]
    tool = fired[2]
    assert (tool.tool, tool.about, tool.agent) == ("Bash", "ls -la", agent.id)
    assert fired[3].said == "done"


def test_a_session_that_never_started_never_ends() -> None:
    agent = Scripted()
    ended: list[Occasion] = []
    agent.hooks.on(Moment.SESSION_END, ended.append)
    agent.new().close()
    assert ended == []


def test_a_refused_prompt_is_answered_without_a_turn() -> None:
    agent = Scripted()
    agent.hooks.on(
        Moment.USER_PROMPT_SUBMIT, lambda _: Verdict(refused=True, because="not now")
    )
    session = agent.new()
    assert session("go") == "not now"
    assert session.told == []


def test_what_a_hook_adds_goes_with_the_prompt() -> None:
    agent = Scripted()
    agent.hooks.on(Moment.USER_PROMPT_SUBMIT, lambda _: Verdict(adds="mind the tests"))
    session = agent.new()
    session("go")
    assert session.told == ["go\n\nmind the tests"]


def test_a_refused_stop_sends_the_agent_on() -> None:
    agent = Scripted()
    again: list[int] = []

    def keep_going(occasion: Occasion) -> Verdict | None:
        again.append(occasion.again)
        if occasion.again < 2:
            return Verdict(refused=True, because=f"go on {occasion.again}")
        return None

    agent.hooks.on(Moment.STOP, keep_going)
    session = agent.new()
    assert session("start") == "done"
    assert session.told == ["start", "go on 0", "go on 1"]
    assert again == [0, 1, 2]


def test_a_refused_stop_with_nothing_to_say_lets_it_stop() -> None:
    agent = Scripted()
    agent.hooks.on(Moment.STOP, lambda _: Verdict(refused=True))
    session = agent.new()
    session("start")
    assert session.told == ["start"]


def test_subagents_fire_their_moments() -> None:
    class Swarm(Scripted):
        moments: ClassVar[frozenset[Moment]] = frozenset(Moment)

    agent = Swarm(
        script=_said(
            Event("subagent", "helper look around", whose="h1"),
            Event("subagent-ends", "helper", whose="h1"),
            Event("result", "done"),
        )
    )
    fired: list[Occasion] = []
    agent.hooks.on(Moment.SUBAGENT_START, fired.append)
    agent.hooks.on(Moment.SUBAGENT_STOP, fired.append)
    agent("go")
    assert [(one.moment, one.tool, one.about, one.under) for one in fired] == [
        (Moment.SUBAGENT_START, "helper", "look around", "h1"),
        (Moment.SUBAGENT_STOP, "helper", "", "h1"),
    ]


# -- failures --------------------------------------------------------------------------


def test_a_failed_turn_raises() -> None:
    agent = Scripted(script=_failing(Failed(1, ["double"], "", "it broke")))
    said = heard(agent)
    with pytest.raises(Failed, match="it broke"):
        agent("go")
    assert said[-1].kind == "ends"


def test_a_failed_turn_is_suppressed_when_asked(
    capsys: pytest.CaptureFixture[str],
) -> None:
    agent = Scripted(script=_failing(Failed(1, ["double"], "", "it broke")))
    assert agent("go", suppress=True) == ""
    assert agent("go", suppress=True, schema=_Verdict) is None
    assert "it broke" in capsys.readouterr().err


def test_a_watched_agent_says_nothing_of_a_suppressed_failure(
    capsys: pytest.CaptureFixture[str],
) -> None:
    agent = Scripted(script=_failing(Failed(1, ["double"], "", "it broke")))
    heard(agent)
    assert agent("go", suppress=True) == ""
    assert capsys.readouterr().err == ""


def test_an_unrecoverable_turn_is_never_suppressed() -> None:
    agent = Scripted(script=_failing(Unrecoverable(1, ["double"], "", "too long")))
    with pytest.raises(Unrecoverable):
        agent("go", suppress=True)


def test_a_stopped_agent_takes_no_turn() -> None:
    agent = Scripted()
    session = agent.new()
    assert not agent.stopped
    agent.stop()
    assert agent.stopped
    with pytest.raises(Stopped, match="was stopped"):
        session("go", suppress=True)
    with pytest.raises(Stopped):
        agent.prompted()


# -- shapes ----------------------------------------------------------------------------


@pytest.mark.parametrize(
    "answer",
    [
        '{"done": true, "why": "tests pass"}',
        'Here:\n```json\n{"done": true, "why": "tests pass"}\n```',
        'I think {"done": true, "why": "tests pass"} is it.',
    ],
)
def test_a_shaped_turn_answers_with_the_model(answer: str) -> None:
    agent = Scripted(script=answering(answer))
    session = agent.new()
    assert session("done?", schema=_Verdict) == _Verdict(done=True, why="tests pass")
    assert session.told[0].startswith("done?\n\nAnswer with JSON")
    assert '"done"' in session.told[0]
    assert session.shaped == [_Verdict]


def test_a_backend_held_to_a_shape_is_not_asked_in_the_prompt() -> None:
    agent = Scripted(script=answering('{"done": false}'), session=Steered)
    session = agent.new()
    assert agent("x", schema=_Verdict) == _Verdict(done=False)
    session("done?", schema=_Verdict)
    assert session.told == ["done?"]


def test_an_answer_out_of_shape_fails_the_turn() -> None:
    agent = Scripted(script=answering("no idea"))
    with pytest.raises(ValueError, match="did not answer as a _Verdict"):
        agent("done?", schema=_Verdict)
    assert agent("done?", schema=_Verdict, suppress=True) is None


# -- effort and budget -----------------------------------------------------------------


def test_effort_follows_the_agent_unless_the_session_says_otherwise() -> None:
    agent = Scripted(AgentConfig(model="m", effort="high"), backend="claude")
    session = agent.new()
    assert (agent.effort, session.effort) == ("high", "high")
    agent.effort = "low"
    assert session.effort == "low"
    session.effort = "max"
    assert (agent.effort, session.effort) == ("low", "max")
    session.effort = ""
    agent.effort = ""
    assert session.effort == "high"


@pytest.mark.parametrize("effort", ["auto", ""])
def test_auto_effort_is_no_rung(effort: str) -> None:
    agent = Scripted(AgentConfig(model="m", effort=effort))
    assert agent.effort == ""
    assert agent.new().effort == ""


def test_a_rung_off_the_ladder_is_refused_wherever_it_arrives() -> None:
    with pytest.raises(Unserved, match="cannot be asked to think at 'bogus'"):
        Scripted(AgentConfig(model="m", effort="bogus"), backend="claude")
    agent = Scripted(backend="claude")
    with pytest.raises(Unserved):
        agent.effort = "bogus"
    with pytest.raises(Unserved):
        agent.new().effort = "bogus"
    assert agent.effort == ""


def test_the_budget_is_the_agents_unless_the_session_says_otherwise() -> None:
    capped = Budget(output=10)
    agent = Scripted(AgentConfig(model="m", effort="", budget=capped))
    session = agent.new()
    assert session.budget is capped
    session.budget = Budget()
    assert session.budget == Budget()
    session.budget = None
    assert session.budget is capped


def _overspends() -> Any:
    return _said(
        Event("text", "part one", spent=Usage(output=10)),
        Event("result", "the answer"),
    )


@pytest.mark.parametrize("when", ["next-response", "immediately"])
def test_a_spent_budget_cuts_the_turn_short(when: str) -> None:
    agent = Scripted(script=_overspends())
    said = heard(agent)
    session = agent.new()
    session.budget = Budget(output=5, when=when)
    assert session("go") == "the answer"
    notices = [one.text for one in said if one.kind == "notice"]
    assert notices == [
        "cutting the turn off: 5 output tokens spent",
        "turn cut off: 5 output tokens",
    ]


def test_a_spent_budget_that_fails_fails_for_good() -> None:
    agent = Scripted(script=_overspends())
    session = agent.new()
    session.budget = Budget(output=5, then="fail")
    with pytest.raises(Unrecoverable, match="turn cut off"):
        session("go", suppress=True)


def test_a_budget_not_reached_leaves_the_turn_alone() -> None:
    agent = Scripted(script=_overspends())
    said = heard(agent)
    session = agent.new()
    session.budget = Budget(output=100, seconds=600)
    assert session("go") == "the answer"
    assert [one for one in said if one.kind == "notice"] == []


def test_a_budget_is_per_turn() -> None:
    agent = Scripted(script=_said(Event("result", "a", spent=Usage(output=4))))
    said = heard(agent)
    session = agent.new()
    session.budget = Budget(output=5)
    session("one")
    session("two")
    assert [one for one in said if one.kind == "notice"] == []


def test_interrupting_a_session_with_no_turn_running_does_nothing() -> None:
    agent = Scripted()
    said = heard(agent)
    session = agent.new()
    session.interrupt(why="enough")
    session.cut(why="enough")
    assert said == []


def test_interrupting_a_turn_ends_it_on_what_was_said() -> None:
    def script(session: Turns, prompt: str) -> Iterable[Event]:
        del prompt
        yield Event("text", "half")
        session.interrupt(why="enough")
        session.interrupt(why="again")  # once is what is said
        yield Event("result", "never mind")

    agent = Scripted(script=script)
    said = heard(agent)
    assert agent("go") == "never mind"
    assert [one.text for one in said if one.kind == "notice"] == [
        "cutting the turn off: enough",
        "turn cut off: again",
    ]


def test_a_turn_cut_off_by_a_failure_answers_with_what_it_said() -> None:
    def script(session: Turns, prompt: str) -> Iterable[Event]:
        del prompt
        yield Event("text", "so far")
        session.interrupt(why="stop")
        raise Failed(-9, ["double"])

    agent = Scripted(script=script)
    assert agent("go") == "so far"


# -- words put in mid-turn -------------------------------------------------------------


def test_a_backend_that_cannot_be_talked_to_mid_turn_says_so() -> None:
    with pytest.raises(NotImplementedError, match="cannot be talked to mid-turn"):
        Scripted().new().interject("also")


def test_the_book_of_words_put_in() -> None:
    session = Scripted().new()
    ticket = session.steering("first")
    assert ticket
    assert session.steering("second", "t-2") == "t-2"
    assert session.took(ticket) == "first"
    assert session.took(ticket) is None
    session.unsteered("second")
    session.unsteered("never said")
    assert session.took("t-2") is None


# -- tools and skills ------------------------------------------------------------------


def test_tools_are_refused_by_a_backend_that_cannot_take_them() -> None:
    tool = Tool(name="t", about="a tool", call=lambda: None)
    session = Scripted().new()
    with pytest.raises(NotImplementedError, match="tool of a flow's own"):
        session.offers([tool])
    session.offers(None)
    session.offers([])
    assert session.tools == ()


def test_tools_offered_are_the_agents_until_the_session_closes() -> None:
    tool = Tool(name="t", about="a tool", call=lambda: None)
    agent = Scripted(session=Steered)
    session = agent.new()
    session.offers([tool])
    assert session.tools == (tool,)
    assert agent.toolbox.offered() == (tool,)
    session.offers(None)
    assert agent.toolbox.empty()
    session.offers([tool])
    session.close()
    assert session.tools == ()
    assert agent.toolbox.empty()


def test_a_session_carries_the_flows_skills_it_was_told(tmp_path: Path) -> None:
    agent = Scripted()
    agent.loads([Loaded("a", tmp_path), Loaded("b", tmp_path), Loaded("c", tmp_path)])
    assert [one.name for one in agent.loaded] == ["a", "b", "c"]
    session = agent.new()
    assert session.skills == ("a", "b", "c")
    session.loads(["c", "a", "nope", "a"])
    assert session.skills == ("a", "c")
    session.loads(None)
    assert session.skills == ("a", "b", "c")


def test_a_turn_mounts_the_skills_and_closing_takes_them_away(tmp_path: Path) -> None:
    skill = tmp_path / "flow" / "review"
    skill.mkdir(parents=True)
    (skill / "SKILL.md").write_text("---\nname: review\n---\n", encoding="utf-8")
    work = tmp_path / "work"
    work.mkdir()
    agent = Scripted(backend="claude")
    agent.loads([Loaded("review", skill)])
    session = agent.new(work)
    mounted = work / ".claude" / "skills" / "review" / "SKILL.md"
    assert not mounted.exists()
    session("go")
    assert mounted.exists()
    session.loads([])
    session("go")
    assert not mounted.exists()
    session.loads(None)
    session("go")
    assert mounted.exists()
    session.close()
    assert not mounted.exists()


# -- where a session works, and its forks ----------------------------------------------


def test_a_session_works_where_it_was_opened(tmp_path: Path) -> None:
    agent = Scripted()
    assert agent.new(tmp_path).cwd == str(tmp_path)
    assert agent.new().cwd == os.path.abspath(os.getcwd())  # noqa: PTH100, PTH109


def test_a_backend_with_no_fork_refuses_one() -> None:
    session = Scripted().new()
    assert not session.forks
    with pytest.raises(NotImplementedError, match="no way of carrying"):
        session.fork()


def _forking() -> Any:
    count = iter(range(1, 100))

    def script(session: Turns, prompt: str) -> Iterable[Event]:
        del prompt
        session.names(f"s-{next(count)}")
        return [Event("result", "done")]

    return script


def test_a_fork_needs_a_conversation_to_carry() -> None:
    session = Scripted(backend="claude", script=_forking()).new()
    assert session.forks
    with pytest.raises(RuntimeError, match="has not run a turn"):
        session.fork()


def test_a_fork_is_a_second_conversation_from_here(tmp_path: Path) -> None:
    agent = Scripted(backend="claude", script=_forking(), session=Steered)
    tool = Tool(name="t", about="a tool", call=lambda: None)
    parent = agent.new(tmp_path)
    parent("read the code")
    parent.effort = "max"
    parent.budget = Budget(output=99)
    parent.loads(["x"])
    parent.offers([tool])
    child = parent.fork()
    assert child is not parent
    assert (child.cwd, child.effort, child.budget, child.tools) == (
        str(tmp_path),
        "max",
        Budget(output=99),
        (tool,),
    )
    assert child.named is None
    child("try this way")
    assert child.id != parent.id
    assert agent.opened == [parent.id, child.id]


def test_a_fork_taken_after_the_parent_moved_on_is_refused() -> None:
    agent = Scripted(backend="claude", script=_forking())
    parent = agent.new()
    parent("one")
    child = parent.fork()
    parent("two")
    with pytest.raises(RuntimeError, match="taken a turn since"):
        child("too late")


def test_a_fork_that_landed_back_in_its_parent_is_refused() -> None:
    agent = Scripted(backend="claude", script=answering(named="same"))
    parent = agent.new()
    parent("one")
    with pytest.raises(RuntimeError, match="fork landed back"):
        parent.fork()("two")


def test_a_fork_into_another_backends_agent_is_refused() -> None:
    agent = Scripted(backend="claude", script=_forking())
    parent = agent.new()
    parent("one")
    with pytest.raises(ValueError, match="same backend"):
        parent.fork(into=Scripted(backend="codex"))
    other = Scripted(backend="claude", script=_forking())
    assert parent.fork(into=other).named is None


def test_a_fork_into_another_directory_needs_a_backend_that_can(tmp_path: Path) -> None:
    agent = Scripted(backend="claude", script=_forking())
    parent = agent.new()
    parent("one")
    with pytest.raises(NotImplementedError, match="another directory"):
        parent.fork(cwd=tmp_path)


# -- a conversation kept elsewhere, carried on -----------------------------------------


class _Run:
    """What a run is to an agent it drives: where it keeps sessions, and what it writes down."""

    def __init__(self, keeps: Path) -> None:
        self.at = keeps
        self.said: list[tuple[str, str]] = []

    @property
    def keeps(self) -> Path:
        return self.at

    def opened(self, agent: AgentBase, session: str, parent: str = "") -> None:
        del agent
        self.said.append((session, parent))


@pytest.fixture
def supervised(monkeypatch: pytest.MonkeyPatch) -> None:
    """A machine whose turns are supervised, so a run keeps its agents' sessions itself."""
    monkeypatch.setattr("hmz.coganchor.providers.redirect.supervises", lambda: True)
    monkeypatch.delenv(KEEPING, raising=False)


#: What the Claude conversation `_claude_kept` keeps was told.
TOLD = '{"said": "the codeword is papaya"}\n'


def _claude_kept(at: Path) -> Path:
    """A Claude conversation as a run kept it, beside one of somebody else's."""
    project = at / "projects" / "-where-it-was-had"
    (project / "told" / "subagents").mkdir(parents=True)
    (project / "told.jsonl").write_text(TOLD)
    (project / "told.jsonl").chmod(0o600)
    (project / "told" / "subagents" / "agent-1.jsonl").write_text("{}\n")
    (project / "somebody-else.jsonl").write_text("{}\n")
    return project


@pytest.mark.usefixtures("supervised")
def test_a_recalled_conversation_is_brought_in_as_a_fork_of_it_takes_its_first_turn(
    tmp_path: Path,
) -> None:
    """Copied where it sat, as the fork's first turn starts and not before, and left as it was.

    Not before: a run attaches itself to the agent after the session is made, and settles
    only then where the agent keeps its sessions.
    """
    project = _claude_kept(tmp_path / "snapshot")
    agent = Scripted(backend="claude", script=_forking())
    child = agent.recall("told", tmp_path / "snapshot", tmp_path).fork()
    run = _Run(tmp_path / "epic")
    agent.epic = run
    assert not run.at.exists()
    assert child.named is None

    child("what was the codeword?")

    assert agent.kept() == run.at / "claude"
    brought = run.at / "claude" / "projects" / "-where-it-was-had"
    assert (brought / "told.jsonl").read_text() == TOLD
    assert stat.S_IMODE((brought / "told.jsonl").stat().st_mode) == 0o600
    assert (brought / "told" / "subagents" / "agent-1.jsonl").is_file()
    assert not (brought / "somebody-else.jsonl").exists()
    assert (project / "told.jsonl").read_text() == TOLD
    assert child.id != "told"
    assert run.said == [(child.id, "told")]
    assert agent.opened == [child.id]


@pytest.mark.usefixtures("supervised")
def test_a_conversation_cut_from_another_is_recalled_with_its_whole_line(
    tmp_path: Path,
) -> None:
    """Codex reads a thread forked from another back only with that other beside it."""
    day = tmp_path / "snapshot" / "sessions" / "2026" / "10" / "03"
    day.mkdir(parents=True)

    def rollout(ident: str, parent: str = "") -> str:
        meta = {"id": ident, **({"forked_from_id": parent} if parent else {})}
        name = f"rollout-2026-10-03T00-00-00-{ident}.jsonl"
        (day / name).write_text(json.dumps({"type": "session_meta", "payload": meta}))
        return name

    line = {rollout("first"), rollout("second", "first"), rollout("third", "second")}
    rollout("somebody-else")
    agent = Scripted(backend="codex", script=_forking())
    child = agent.recall("third", tmp_path / "snapshot").fork()
    agent.epic = _Run(tmp_path / "epic")

    child("go on")

    brought = tmp_path / "epic" / "codex" / "sessions" / "2026" / "10" / "03"
    assert {path.name for path in brought.iterdir()} == line


@pytest.mark.usefixtures("supervised")
def test_a_first_turn_that_could_not_bring_the_conversation_in_tries_again(
    tmp_path: Path,
) -> None:
    _claude_kept(tmp_path / "snapshot")
    (tmp_path / "taken").write_text("a file, where the run's directory would be")
    agent = Scripted(backend="claude", script=_forking())
    child = agent.recall("told", tmp_path / "snapshot").fork()
    run = _Run(tmp_path / "taken" / "epic")
    agent.epic = run

    with pytest.raises(NotADirectoryError):
        child("one")
    run.at = tmp_path / "epic"
    child("two")

    brought = run.at / "claude" / "projects" / "-where-it-was-had"
    assert (brought / "told.jsonl").read_text() == TOLD
    assert run.said == [(child.id, "told")]


@pytest.mark.usefixtures("supervised")
def test_one_copy_is_brought_in_for_every_fork_carrying_it_on(tmp_path: Path) -> None:
    _claude_kept(tmp_path / "snapshot")
    agent = Scripted(backend="claude", script=_forking())
    run = _Run(tmp_path / "epic")
    agent.epic = run
    first = agent.recall("told", tmp_path / "snapshot").fork()
    second = agent.recall("told", tmp_path / "snapshot").fork()

    first("one way")
    second("another")

    brought = run.at / "claude" / "projects" / "-where-it-was-had"
    assert (brought / "told.jsonl").read_text() == TOLD
    assert run.said == [(first.id, "told"), (second.id, "told")]


#: What the conversation `_claude_kept` keeps went on to be told, after that copy was taken.
LATER = TOLD + '{"said": "forget the codeword"}\n'


@pytest.mark.parametrize("keeping", ["the run", "the CLI's own home"])
def test_a_conversation_kept_otherwise_where_it_is_brought_in_is_left_as_it_is(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, keeping: str
) -> None:
    """Another copy is the run's own, or the user's, and is refused before any is copied."""
    monkeypatch.setattr("hmz.coganchor.providers.redirect.supervises", lambda: True)
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path / "home"))
    if keeping == "the run":
        monkeypatch.delenv(KEEPING, raising=False)
        into = tmp_path / "epic" / "claude"
    else:
        monkeypatch.setenv(KEEPING, "off")
        into = tmp_path / "home"
    _claude_kept(tmp_path / "snapshot")
    held = into / "projects" / "-where-it-was-had" / "told.jsonl"
    held.parent.mkdir(parents=True)
    held.write_text(LATER)
    agent = Scripted(backend="claude", script=_forking())
    child = agent.recall("told", tmp_path / "snapshot").fork()
    run = _Run(tmp_path / "epic")
    agent.epic = run

    with pytest.raises(RuntimeError, match="another copy of conversation told is kept"):
        child("what was the codeword?")

    assert agent.kept() == into
    assert held.read_text() == LATER
    assert not (held.parent / "told").exists(), "nothing of it copied"
    assert run.said == []


@pytest.mark.usefixtures("supervised")
def test_a_conversation_kept_as_it_stands_is_recalled_from_there(
    tmp_path: Path,
) -> None:
    """Only its own files, laid out as they sat, and recalled as they were when kept."""
    agent = Scripted(backend="claude", script=_forking())
    agent.epic = _Run(tmp_path / "epic")
    session = agent.new(tmp_path)
    session("the codeword is papaya")
    home = agent.kept()
    assert home is not None
    project = home / "projects" / "-where-it-was-had"
    project.mkdir(parents=True)
    (project / f"{session.id}.jsonl").write_text(TOLD)
    (project / "somebody-else.jsonl").write_text("{}\n")

    session.keep(tmp_path / "snapshot")
    (project / f"{session.id}.jsonl").write_text(LATER)

    kept = tmp_path / "snapshot" / "projects" / "-where-it-was-had"
    assert sorted(one.name for one in kept.iterdir()) == [f"{session.id}.jsonl"]
    assert (kept / f"{session.id}.jsonl").read_text() == TOLD
    later = Scripted(backend="claude", script=_forking())
    later("a conversation of its own first, so that the fork is not named s-1 too")
    child = later.recall(session.id, tmp_path / "snapshot").fork()
    later.epic = _Run(tmp_path / "later")
    child("what was the codeword?")
    brought = later.kept()
    assert brought is not None
    assert (
        brought / "projects" / "-where-it-was-had" / f"{session.id}.jsonl"
    ).read_text() == TOLD


@pytest.mark.usefixtures("supervised")
def test_what_is_kept_beside_a_clis_sessions_is_no_conversation_of_them(
    tmp_path: Path,
) -> None:
    """A copy kept under `.kept` holds the id too, and is no file of the conversation."""
    agent = Scripted(backend="claude", script=_forking())
    agent.epic = _Run(tmp_path / "epic")
    session = agent.new(tmp_path)
    session("the codeword is papaya")
    home = agent.kept()
    assert home is not None
    project = home / "projects" / "-where-it-was-had"
    project.mkdir(parents=True)
    (project / f"{session.id}.jsonl").write_text(TOLD)
    session.keep(home / KEPT / "first")

    session.keep(tmp_path / "second")

    kept = sorted(
        one.relative_to(tmp_path / "second").as_posix()
        for one in (tmp_path / "second").rglob("*")
        if one.is_file()
    )
    assert kept == [f"projects/-where-it-was-had/{session.id}.jsonl"]


def test_a_conversation_is_kept_only_once_it_is_one(tmp_path: Path) -> None:
    with pytest.raises(RuntimeError, match="has not run a turn"):
        Scripted(backend="claude", script=_forking()).new().keep(tmp_path)
    session = Scripted(script=_forking()).new()
    session("hello")
    with pytest.raises(NotImplementedError, match="no way of carrying"):
        session.keep(tmp_path)


@pytest.mark.usefixtures("supervised")
def test_a_conversation_nothing_kept_is_not_kept(tmp_path: Path) -> None:
    agent = Scripted(backend="claude", script=_forking())
    agent.epic = _Run(tmp_path / "epic")
    session = agent.new(tmp_path)
    session("hello")
    with pytest.raises(RuntimeError, match=f"no conversation {session.id} under"):
        session.keep(tmp_path / "snapshot")
    assert not (tmp_path / "snapshot").exists()


def test_a_conversation_is_recalled_only_from_where_it_was_kept(tmp_path: Path) -> None:
    _claude_kept(tmp_path / "snapshot")

    with pytest.raises(RuntimeError, match="no conversation another under"):
        Scripted(backend="claude").recall("another", tmp_path / "snapshot")
    with pytest.raises(NotImplementedError, match="no way of carrying"):
        Scripted().recall("told", tmp_path / "snapshot")


# -- goals -----------------------------------------------------------------------------


def test_a_backend_with_no_goals_says_so() -> None:
    with pytest.raises(NotImplementedError, match="no goal feature"):
        Scripted().pursue("ship it")


def test_a_goal_is_pursued_where_the_backend_has_them() -> None:
    agent = Scripted(session=Steered)
    assert agent.goals_enabled
    assert agent.pursue("ship it") == "pursued ship it"
    agent.disable_goals()
    assert not agent.goals_enabled
    with pytest.raises(RuntimeError, match="goals are disabled"):
        agent.new().pursue("ship it", suppress=True)


def test_a_failed_goal_is_suppressed_when_asked() -> None:
    class Failing(Steered):
        def _pursue(self, objective: str) -> str:
            raise Failed(1, [objective])

    agent = Scripted(session=Failing)
    assert agent.pursue("x", suppress=True) == ""
    with pytest.raises(Failed):
        agent.pursue("x")


# -- the agent -------------------------------------------------------------------------


def test_an_unnamed_agent_gets_a_codename_and_may_be_renamed() -> None:
    first, second = Scripted(), Scripted()
    assert first.id != second.id
    first.rename("builder")
    assert first.id == "builder"
    assert first.hooks.agent == "builder"


def test_a_named_agent_keeps_its_name() -> None:
    agent = Scripted(name="mine")
    agent.rename("theirs")
    assert agent.id == "mine"


def test_the_backend_of_a_driver_in_no_table_is_its_class_name() -> None:
    class SomethingNewCLIAgent(AgentBase):
        def new(self, cwd: str | os.PathLike[str] | None = None) -> SessionBase:
            raise NotImplementedError

    assert (
        SomethingNewCLIAgent(AgentConfig(model="m", effort="")).backend
        == "somethingnew"
    )


def test_an_agent_says_where_it_runs() -> None:
    agent = Scripted(AgentConfig(model="m1", effort=""), backend="double")
    assert agent.spec == "double/m1"
    assert agent.provider is None
    assert agent.node().name == ""
    assert dict(agent.environment()) == {}
    assert agent.hushed() == frozenset()
    assert agent.anchor is None
    assert agent.stands_in() is None
    assert agent.fenced() is None


def test_a_fence_or_rung_or_tier_the_backend_cannot_carry_is_refused() -> None:
    class Narrow(Scripted):
        rungs: ClassVar[tuple[str, ...]] = ("read-only",)

    with pytest.raises(Unserved, match="cannot be held to 'bypass'"):
        Narrow(AgentConfig(model="m", effort="", permission="bypass"))
    assert Narrow(AgentConfig(model="m", effort="", permission="read-only"))
    with pytest.raises(Unserved, match="service tier 'fast'"):
        Scripted(AgentConfig(model="m", effort="", service_tier="fast"))
    with pytest.raises(Unserved, match="search the web"):
        Scripted(AgentConfig(model="m", effort="", web_search=False))


def test_reconfigure_keeps_what_it_had_when_refused() -> None:
    agent = Scripted()
    was = agent.config
    with pytest.raises(Unserved):
        agent.reconfigure(replace(was, service_tier="fast"))
    assert agent.config is was
    better = replace(was, model="m2")
    agent.reconfigure(better)
    assert agent.config is better


def test_runs_on_is_only_for_an_agent_that_has_opened_nothing() -> None:
    agent = Scripted(script=answering(named="s"))
    agent.runs_on(None)
    assert agent.config.machine is None
    agent("go")
    with pytest.raises(RuntimeError, match="already opened a session"):
        agent.runs_on(None)


def test_a_clone_is_another_agent_set_up_the_same(tmp_path: Path) -> None:
    agent = Scripted(AgentConfig(model="m", effort=""), name="a")
    agent.loads([Loaded("s", tmp_path)])
    agent.allowance = Ledger(Allowance(hours=1), [agent])
    agent("go")
    clone = agent.clone()
    assert type(clone) is Scripted
    assert clone.id != agent.id
    assert (clone.config, clone.loaded) == (agent.config, agent.loaded)
    assert dict(clone.spent()) == {"input": 0, "output": 0}
    assert clone.allowance is agent.allowance
    assert clone in agent.allowance.agents()
    other = agent.clone(config=replace(agent.config, model="m2"), name="b", skills=[])
    assert (other.id, other.config.model, other.loaded) == ("b", "m2", ())


def test_sessions_are_held_weakly() -> None:
    agent = Scripted()
    kept = agent.new()
    agent.new()
    gc.collect()
    assert agent.sessions == [kept]


def test_stopping_closes_every_session() -> None:
    agent = Scripted()
    ended: list[Occasion] = []
    agent.hooks.on(Moment.SESSION_END, ended.append)
    session = agent.new()
    session("go")
    agent.stop()
    assert [one.moment for one in ended] == [Moment.SESSION_END]


def test_where_an_agent_keeps_its_sessions(tmp_path: Path) -> None:
    agent = Scripted()
    assert agent.keeps is None
    assert agent.kept() is None
    agent.keeps = tmp_path
    assert agent.keeps == tmp_path
    assert agent.kept() == tmp_path / "double"
    agent.keeps = None
    assert agent.keeps is None
    assert KEEPING == "HUMANIZE_SESSIONS"


def test_a_journal_is_told_every_session_opened(tmp_path: Path) -> None:
    class Journal:
        def __init__(self) -> None:
            self.said: list[tuple[str, str]] = []

        @property
        def keeps(self) -> Path:
            return tmp_path

        def opened(self, agent: AgentBase, session: str, parent: str = "") -> None:
            del agent
            self.said.append((session, parent))

    journal = Journal()
    agent = Scripted(backend="claude", script=_forking())
    agent.epic = journal
    assert agent.keeps == tmp_path
    parent = agent.new()
    parent("one")
    parent.fork()("two")
    assert journal.said == [("s-1", ""), ("s-2", "s-1")]


# -- asking the person -----------------------------------------------------------------


def test_asking_with_nobody_there_answers_none() -> None:
    agent = Scripted()
    said = heard(agent)
    notified: list[Occasion] = []
    agent.hooks.on(Moment.NOTIFICATION, notified.append)
    assert agent.asked(Question("which one?")) is None
    assert _kinds(said) == [("asks", "which one?")]
    assert [one.said for one in notified] == ["which one?"]


def test_asking_puts_the_question_to_whoever_drives_the_agent() -> None:
    agent = Scripted()
    agent.ask = lambda question: f"{question.text} -- this one"
    assert agent.asked(Question("which?")) == "which? -- this one"


def test_an_ask_that_fails_is_nobody_answering() -> None:
    agent = Scripted()

    def broken(_: Question) -> NoReturn:
        raise RuntimeError

    agent.ask = broken
    assert agent.asked(Question("which?")) is None


def test_prompted_is_whatever_the_person_says_next() -> None:
    agent = Scripted()
    assert agent.prompted() is None
    agent.prompting = lambda: "next"
    assert agent.prompted() == "next"

    def broken() -> NoReturn:
        raise RuntimeError

    agent.prompting = broken
    assert agent.prompted() is None


# -- many turns at once ----------------------------------------------------------------


def _echo(session: Turns, prompt: str) -> Iterable[Event]:
    del session
    if prompt == "fail":
        raise Failed(1, ["double"])
    return [Event("result", prompt.upper())]


def test_batch_answers_in_the_order_asked() -> None:
    agent = Scripted(script=_echo)
    assert agent.batch([]) == []
    assert agent.batch(["a", "b", "c"], at_once=2) == ["A", "B", "C"]
    assert agent.batch(["a", "fail"], suppress=True) == ["A", ""]
    with pytest.raises(Failed):
        agent.batch(["a", "fail"])


def test_batch_with_a_shape() -> None:
    agent = Scripted(script=answering('{"done": true}'))
    assert agent.batch(["a"], schema=_Verdict) == [_Verdict(done=True)]


def test_batch_new_opens_as_many_as_asked(tmp_path: Path) -> None:
    agent = Scripted()
    opened = agent.batch_new(3, tmp_path)
    assert len(opened) == 3
    assert {one.cwd for one in opened} == {str(tmp_path)}
    assert agent.batch_new(-1) == []


async def test_awaited_turns() -> None:
    agent = Scripted(script=_echo)
    assert await agent.aturn("a") == "A"
    assert await agent.new().aturn("b") == "B"
    assert await agent.abatch([]) == []
    assert await agent.abatch(["c", "d"], at_once=1) == ["C", "D"]
    with pytest.raises(Failed):
        await agent.abatch(["fail"])
    shaped = Scripted(script=answering('{"done": true}'))
    assert await shaped.aturn("x", schema=_Verdict) == _Verdict(done=True)
    assert await shaped.new().aturn("x", schema=_Verdict) == _Verdict(done=True)
    assert await shaped.abatch(["x"], schema=_Verdict) == [_Verdict(done=True)]


async def test_awaited_goals() -> None:
    agent = Scripted(session=Steered)
    assert await agent.apursue("x") == "pursued x"
    assert await agent.new().apursue("y") == "pursued y"


# -- the run's allowance ---------------------------------------------------------------


def test_a_run_over_its_allowance_stops_every_agent() -> None:
    agent = Scripted(script=_said(Event("result", "a", spent=Usage(output=2_000_000))))
    other = Scripted()
    agent.allowance = Ledger(Allowance(tokens=1), [agent, other])
    other.allowance = agent.allowance
    agent("go")  # the turn that ran it out lands, and the run is stopped as it does
    assert agent.stopped
    assert other.stopped
    with pytest.raises(Stopped):
        other("go")


# -- the other two base classes, and what a config class is told -----------------------


def test_the_transport_base_classes_are_abstract() -> None:
    class Command(CommandSessionBase):
        pass

    class Stream(StreamSessionBase):
        pass

    agent = Scripted()
    assert not CommandSessionBase.protocol
    with pytest.raises(TypeError):
        Command(agent)  # pyright: ignore[reportAbstractUsage]
    with pytest.raises(TypeError):
        Stream(agent)  # pyright: ignore[reportAbstractUsage]


def test_identifying_names_the_cli_only_for_the_protocol_class() -> None:
    assert identifying(AcpAgentConfig, "mycli") == {"cli": "mycli"}
    assert identifying(ClaudeCodeAgentConfig, "claude") == {}
    assert identifying(AgentConfig, "x") == {}
