"""`hmz.sdk.fakes`: the in-memory drivers a flow is tested on, and running it on them.

The drivers are :mod:`hmz.runtime.flowing.fakes`'s, handed through as themselves. Running a
flow on them is not done here: :func:`run_fake` runs it as every epic is run, through a daemon
-- a private daemon of this program's own, in this process, which alone can hold the objects
given (Section 4.19 of python.md).
"""

from __future__ import annotations

import asyncio
import inspect
import math
from typing import TYPE_CHECKING, Any

from hmz.runtime.flowing.fakes import (
    Answer,
    Command,
    FakeAgentDriver,
    FakeEnvDriver,
    FakeOutworlder,
    FakeSession,
    Handler,
    Reply,
    filled,
)

if TYPE_CHECKING:
    from collections.abc import Mapping
    from pathlib import Path

    from hmz.flows import Budget, Flow, FlowParams
    from hmz.runtime.flowing import AgentDriver, EnvDriver, OutworlderDriver

__all__ = [
    "Answer",
    "Command",
    "FakeAgentDriver",
    "FakeEnvDriver",
    "FakeOutworlder",
    "FakeSession",
    "Handler",
    "Reply",
    "run_fake",
]


async def run_fake(
    flow: Flow | str,
    task: str = "",
    *,
    agents: Mapping[str, AgentDriver | OutworlderDriver | Reply] | None = None,
    envs: Mapping[str, EnvDriver | Mapping[str, bytes | str]] | None = None,
    params: FlowParams | Mapping[str, Any] | None = None,
    budget: Budget | None = None,
    outworlder: OutworlderDriver | None = None,
    local: EnvDriver | None = None,
    journal: Path | None = None,
    resume: bool = False,
) -> Any:
    """Runs a flow on fakes, through a private daemon, with a fake for every role left out.

    Args:
      flow: The flow, or a ref to load from where this is called.
      task: What to do.
      agents: By role: a driver, or what a :class:`FakeAgentDriver` for the role replies.
        A role left out gets a fake of the harness it asks for, or Claude Code -- which
        serves every mixin -- replying "ok". An `Outworlder` role given a reply is the
        epic's outworlder, answering it.
      envs: By role: a driver, or the files a :class:`FakeEnvDriver` for it starts with. A
        role left out gets an empty one, large enough for what it asks of its machine.
      params: The params, or a mapping of them; the defaults where None.
      budget: What the epic may spend; unlimited where None.
      outworlder: Whoever fills `Outworlder` roles; an away one where None.
      local: What fills `LocalEnv` roles; an empty fake where None.
      journal: Where a resumable flow's journal is written, or None for its epic's.
      resume: Whether to pick up the epic `journal` holds.

    Returns:
      What the flow returned, the object itself.

    Raises:
      RequirementError: If the drivers do not meet what the flow declares. Nothing has run.
      ParamsError: If the params do not validate.
      BaseException: What the flow raised, the exception itself.
    """
    from pathlib import Path

    from hmz.flows import Budget
    from hmz.runtime import Refused
    from hmz.runtime.flowing.engine import fits
    from hmz.sdk.private import Fakes
    from hmz.sdk.running import Run, checked

    caller: dict[str, Any] = {}
    if isinstance(flow, str):
        frame = inspect.currentframe()
        asking = frame.f_back if frame is not None else None
        caller = asking.f_globals if asking else {}
        del frame, asking
    loaded, drivers, environments, outworlder = await filled(
        flow, agents=agents, envs=envs, outworlder=outworlder, caller=caller
    )
    fakes = Fakes()
    fakes.local = FakeEnvDriver(workdir="/here") if local is None else local
    fakes.journal = None if journal is None else (journal, resume)

    held: list[Run] = []

    def runs() -> Any:
        runner = checked(
            str(Path.cwd()),
            loaded,
            agents=drivers,
            envs=environments,
            params=params,
            budget=Budget(cost=math.inf) if budget is None else budget,
            profile_flow=False,
            profile_environment=False,
            resume=False,
            backup=[],
            fakes=fakes,
        )
        held.append(Run(runner, task, outworlder=outworlder))
        return held[-1].run()

    try:
        return await asyncio.to_thread(runs)
    except Refused:
        # Refused before the flow was called, which a daemon says as a sentence: the flow
        # API's own exception for it is raised, by the check the engine makes of the same.
        fits(loaded, agents=drivers, envs=environments, params=params or {})
        raise
    except asyncio.CancelledError:
        # Given up on: the epic is forced and its daemon goes, rather than going on unread.
        for one in held:
            one.close()
        raise
    finally:
        fakes.close()
