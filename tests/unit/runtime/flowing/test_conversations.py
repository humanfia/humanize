"""Sessions kept in a flow's state: carried on from where they stood, in this run or a later one."""

from __future__ import annotations

import shutil
from typing import TYPE_CHECKING, Any

import pytest

from hmz.coganchor import atomic
from hmz.flows import (
    Agent,
    AgentCollection,
    EnvCollection,
    FlowContext,
    FlowParams,
    FlowState,
    HarnessKind,
    Outworlder,
    Session,
    SessionError,
    StateNotSerializable,
    UnsupportedOperation,
    flow,
)
from hmz.runtime.flowing.fakes import FakeAgentDriver, FakeSession, run_fake

if TYPE_CHECKING:
    from collections.abc import Iterable
    from pathlib import Path


class Solo(AgentCollection):
    coder: Agent


class Asking(AgentCollection):
    coder: Agent
    person: Outworlder


class Step(FlowParams):
    step: str = "keep"


def _state(ctx: FlowContext) -> FlowState:
    state = ctx.state
    assert state is not None
    return state


@flow(agents=Solo, envs=EnvCollection, params=Step, resumable=True)
async def remembers(
    task: str, *, agents: Solo, envs: EnvCollection, params: Step, ctx: FlowContext
) -> Any:
    """Keeps a session at a boundary and goes on with it; carries what it kept on later."""
    del task, envs
    coder = agents["coder"]
    state = _state(ctx)
    if params.step == "keep":
        session = await coder.spawn()
        await coder.run("the codeword is papaya", session=session)
        state["boundary"] = {"round": 1, "sessions": [session]}
        await coder.run("forget the codeword", session=session)
        again = state["boundary"]["sessions"][0]
        return await coder.run("what was the codeword?", session=again)
    again = state["boundary"]["sessions"][0]
    return await coder.run(f"{params.step}: what was the codeword?", session=again)


def _last(coder: FakeAgentDriver) -> FakeSession:
    return coder.sessions[-1]


@pytest.fixture
def plain_writes(monkeypatch: pytest.MonkeyPatch) -> None:
    def writes(at: Path, said: Iterable[bytes]) -> None:
        at.write_bytes(b"".join(said))

    monkeypatch.setattr(atomic, "writes", writes)


async def test_a_session_read_back_carries_on_from_where_it_stood_when_written() -> (
    None
):
    coder = FakeAgentDriver(reply="ok")

    await run_fake(remembers, agents={"coder": coder})

    kept, carried = coder.sessions
    assert kept.prompts == ["the codeword is papaya", "forget the codeword"]
    assert carried.prompts == ["the codeword is papaya", "what was the codeword?"]
    assert carried.carried_on is not None
    assert carried.carried_on.id == kept.id
    assert not carried.carried_on.at.exists(), (
        "a run with no journal keeps nothing after"
    )


@pytest.mark.usefixtures("plain_writes")
async def test_a_later_run_carries_on_what_an_earlier_one_kept(tmp_path: Path) -> None:
    journal = tmp_path / "resume.jsonl"
    await run_fake(
        remembers, agents={"coder": FakeAgentDriver(reply="ok")}, journal=journal
    )
    coder = FakeAgentDriver(reply="ok")

    await run_fake(
        remembers,
        agents={"coder": coder},
        params={"step": "continue"},
        journal=journal,
        resume=True,
    )

    (carried,) = coder.sessions
    assert carried.prompts == [
        "the codeword is papaya",
        "continue: what was the codeword?",
    ]
    assert carried.carried_on is not None
    assert carried.carried_on.at.parent == tmp_path / "sessions" / "claude" / ".kept"


@pytest.mark.usefixtures("plain_writes")
async def test_one_kept_session_is_carried_on_by_every_run_picking_it_up(
    tmp_path: Path,
) -> None:
    journal = tmp_path / "resume.jsonl"
    await run_fake(
        remembers, agents={"coder": FakeAgentDriver(reply="ok")}, journal=journal
    )
    picked = tmp_path / "picked.jsonl"
    arms: list[list[str]] = []
    for arm in ("a", "b"):
        shutil.copyfile(journal, picked)
        coder = FakeAgentDriver(reply="ok")
        await run_fake(
            remembers,
            agents={"coder": coder},
            params={"step": arm},
            journal=picked,
            resume=True,
        )
        arms.append(_last(coder).prompts)

    assert arms == [
        ["the codeword is papaya", "a: what was the codeword?"],
        ["the codeword is papaya", "b: what was the codeword?"],
    ]


@pytest.mark.usefixtures("plain_writes")
async def test_a_kept_session_is_carried_on_only_by_the_harness_that_kept_it(
    tmp_path: Path,
) -> None:
    journal = tmp_path / "resume.jsonl"
    await run_fake(
        remembers, agents={"coder": FakeAgentDriver(reply="ok")}, journal=journal
    )
    coder = FakeAgentDriver(HarnessKind.CODEX, reply="ok")

    with pytest.raises(
        UnsupportedOperation, match="codex cannot carry on a conversation claude"
    ):
        await run_fake(
            remembers,
            agents={"coder": coder},
            params={"step": "continue"},
            journal=journal,
            resume=True,
        )
    assert coder.sessions == [], "refused before a session opened"


@pytest.mark.usefixtures("plain_writes")
async def test_a_kept_session_whose_copy_is_gone_cannot_be_carried_on(
    tmp_path: Path,
) -> None:
    journal = tmp_path / "resume.jsonl"
    await run_fake(
        remembers, agents={"coder": FakeAgentDriver(reply="ok")}, journal=journal
    )
    shutil.rmtree(tmp_path / "sessions" / "claude" / ".kept")

    with pytest.raises(SessionError, match="no conversation"):
        await run_fake(
            remembers,
            agents={"coder": FakeAgentDriver(reply="ok")},
            params={"step": "continue"},
            journal=journal,
            resume=True,
        )


# -- what is refused as it is written ---------------------------------------------------


class How(FlowParams):
    how: str


@flow(agents=Asking, envs=EnvCollection, params=How, resumable=True)
async def writes(
    task: str, *, agents: Asking, envs: EnvCollection, params: How, ctx: FlowContext
) -> None:
    """Writes a session down in its state that cannot be kept."""
    del task, envs
    coder = agents["coder"]
    state = _state(ctx)
    session: Session = await coder.spawn()
    if params.how == "unturned":
        state["s"] = session
    elif params.how == "outworlder":
        state["s"] = await agents["person"].spawn()
    elif params.how == "taken":
        await coder.run("go", session=session)
        state["s"] = session
    elif params.how == "unturned again":
        await coder.run("go", session=session)
        state["s"] = session
        again = state["s"]
        state["t"] = again
        assert state["t"] is not again, "every read is a session of its own"
        await coder.run("go on", session=state["t"])


@pytest.mark.parametrize(
    ("how", "harness", "why"),
    [
        ("unturned", HarnessKind.CLAUDE, "taken no turn"),
        ("outworlder", HarnessKind.CLAUDE, "an outworlder's session"),
        ("taken", HarnessKind.CURSOR_AGENT, "cannot fork a session"),
        ("taken", HarnessKind.OPENCODE, "in a database"),
    ],
    ids=["unturned", "outworlder", "unforked", "in-a-database"],
)
async def test_a_session_that_cannot_be_kept_is_refused_as_it_is_written(
    how: str, harness: HarnessKind, why: str
) -> None:
    with pytest.raises(StateNotSerializable, match=why):
        await run_fake(
            writes,
            agents={"coder": FakeAgentDriver(harness, reply="ok")},
            params={"how": how},
        )


async def test_a_session_read_back_and_written_again_keeps_what_it_carries_on() -> None:
    coder = FakeAgentDriver(reply="ok")

    await run_fake(writes, agents={"coder": coder}, params={"how": "unturned again"})

    kept, carried = coder.sessions
    assert carried.carried_on is not None
    assert carried.carried_on.id == kept.id
    assert carried.prompts == ["go", "go on"]


class Given(FlowParams):
    pass


#: The session a caller hands down to :func:`takes` to write down.
_HANDED: list[Session] = []


@flow(agents=Solo, envs=EnvCollection, params=Given, resumable=True)
async def takes(
    task: str, *, agents: Solo, envs: EnvCollection, params: Given, ctx: FlowContext
) -> None:
    del task, agents, envs, params
    _state(ctx)["s"] = _HANDED[0]


@flow(agents=Solo, envs=EnvCollection, params=Given, resumable=True)
async def hands_down(
    task: str, *, agents: Solo, envs: EnvCollection, params: Given, ctx: FlowContext
) -> None:
    """Hands a session of its own down to a flow it calls, to keep in that flow's state."""
    del task, envs, params, ctx
    session = await agents["coder"].spawn()
    await agents["coder"].run("go", session=session)
    _HANDED.append(session)
    await takes("", agents={"coder": agents["coder"]}, envs={}, params=Given())


async def test_a_session_is_kept_only_in_the_state_of_the_call_it_is_of() -> None:
    _HANDED.clear()

    with pytest.raises(
        StateNotSerializable, match="only in the state of the flow call"
    ):
        await run_fake(hands_down, agents={"coder": FakeAgentDriver(reply="ok")})
