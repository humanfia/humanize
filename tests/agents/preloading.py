"""An agent nobody is listening to, one somebody is, and the wait for what it says.

`tests/{integration,system}/agents/test_preload.py` are two halves of one subject: the layer
that patches a coding agent's own runtime from inside it and reports back what the turn did.
Which half a test is in comes down to what is on the far end -- a report written into the
socket by this process, or a real `node` loading the runtime and saying what it spawned -- and
neither half changes what a report is, how an agent is put where one can arrive, or what
waiting for one means.

Written down once here because the third of those is the one worth sharing: `waits` is a poll
with a ceiling on it, and a ceiling that drifts between two copies is a suite that is flaky in
one tier and not in the other, for no reason a reader of either file could see.

Here rather than in a conftest because these are imported by name, and a conftest is a pytest
plugin rather than a module to import from -- and because the two halves are no longer under
one directory to put a conftest in.
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

from hmz.coganchor.agents import AgentConfig, Moment
from tests.stubs import ShellAgent

if TYPE_CHECKING:
    from hmz.coganchor.agents import AgentBase, Occasion

#: What the stand-in agents are configured with, which neither half reads back.
_CONFIG = AgentConfig(model="m", effort="high")

#: How long a report is waited for. They arrive on a thread of their own, after the write that
#: carried them, so this is a ceiling on a scheduler rather than a duration anything means to
#: spend -- generous, because the system half is waiting on a whole Node process starting,
#: doing four things and exiting, and a loaded machine is the only other reason one is not
#: instant.
PATIENCE = 30.0


def agent(name: str = "worker") -> ShellAgent:
    """One agent with nothing hung on it, which is an agent nobody is listening to.

    Args:
      name: The codename it answers to, which is what a report is filed under.

    Returns:
      The agent, with no hook on it at all.
    """
    return ShellAgent(_CONFIG, name=name)


def seen(worker: AgentBase) -> list[Occasion]:
    """Has every `PreToolUse` of this agent written down, which is what turns the layer on.

    Named `worker` rather than `agent` because `agent` is the factory above: a parameter of
    that name would shadow it, and the first line written here that reached for one would get
    the other without saying so.

    Args:
      worker: The agent to listen to.

    Returns:
      Where the reports will be appended, by the thread they arrive on.
    """
    said: list[Occasion] = []
    worker.hooks.on(Moment.PRE_TOOL_USE, said.append)
    return said


def waits(said: list[Occasion], many: int) -> list[Occasion]:
    """Waits for that many reports to arrive, or for the patience to run out.

    Args:
      said: Where the hook is writing them down, which another thread is appending to.
      many: How many are expected.

    Returns:
      What arrived, which is what the test then reads -- short, where they did not.
    """
    ended = time.monotonic() + PATIENCE
    while len(said) < many and time.monotonic() < ended:
        time.sleep(0.05)
    return list(said)
